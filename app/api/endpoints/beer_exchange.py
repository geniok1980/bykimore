from typing import Annotated

from fastapi import APIRouter, Depends
import re
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.utils.logger import setup_logger
from app.db.session import get_db
from app.models.dish import Dish
from app.models.price import Price
from app.models.rate import Rate
from app.schemas.beer_exchange import BeerExchangeItem
from app.services.iiko_service import IikoService

router = APIRouter()
logger = setup_logger(__name__)


@router.get("/", response_model=list[BeerExchangeItem])
async def get_beer_exchange_items(
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BeerExchangeItem]:
    # Диагностика: какой запрос приводит к показу "РАСПРОДАНО"
    # Фронт показывает метку, если backend возвращает stoplisted=True ИЛИ если price/rate == None.
    # Здесь формируем ответ: для блюд в стоп-листе выставляем stoplisted=True и скрываем price/rate (None).
    try:
        logger.info("GET /beer-exchange invoked: SOLD OUT shown when stoplisted=True or price/rate is null")
    except Exception:
        pass
    # Получаем все блюда
    result = await db.execute(select(Dish))
    dishes = result.scalars().all()

    # Попробуем получить список product_id из стоп-листа (только для iikoCloud)
    stoplisted_ids: set[str] = set()
    try:
        svc = IikoService()
        # Диагностика наличия конфигурации iikoCloud (секреты не выводим)
        try:
            logger.info(
                f"beer_exchange: iikoCloud config base_url='{svc.base_url}' api_key_set={bool(svc.api_key)} org_id_set={bool(svc.organization_id)}"
            )
        except Exception:
            pass
        # В серверном режиме стоп-лист из клауда не запрашиваем без сигнала вебхука,
        # поэтому здесь используем только кэш (from_webhook=False)
        ids = await svc.fetch_stoplist_ids(from_webhook=False)
        stoplisted_ids = {str(pid).strip() for pid in ids if isinstance(pid, (str, int)) and str(pid).strip()}
        logger.info(f"beer_exchange: stoplist loaded {len(stoplisted_ids)} productIds")
    except Exception:
        # Не блокируем выдачу, просто игнорируем стоп-лист при ошибке
        stoplisted_ids = set()

    items: list[BeerExchangeItem] = []
    for dish in dishes:
        # Последняя цена
        price_res = await db.execute(
            select(Price).where(Price.dish_id == dish.id).order_by(desc(Price.created_at)).limit(1)
        )
        latest_price = price_res.scalars().first()

        # Последний курс
        rate_res = await db.execute(
            select(Rate).where(Rate.dish_id == dish.id).order_by(desc(Rate.created_at)).limit(1)
        )
        latest_rate = rate_res.scalars().first()

        # Проверяем, находится ли блюдо в стоп-листе по product_id
        pid = (dish.product_id or "").strip() if isinstance(dish.product_id, str) else (str(dish.product_id).strip() if dish.product_id is not None else "")
        is_stoplisted = bool(pid) and pid in stoplisted_ids
        if is_stoplisted:
            logger.info(f"beer_exchange: stoplisted matched dish='{dish.name}' pid='{pid}'")

        items.append(BeerExchangeItem(
            id=dish.id,
            name=dish.name,
            price=(None if is_stoplisted else (latest_price.value if latest_price else None)),
            rate=(None if is_stoplisted else (latest_rate.value if latest_rate else None)),
            stoplisted=is_stoplisted,
        ))

    return items