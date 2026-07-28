import os
import time
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.api import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import async_engine
from app.utils.logger import setup_logger
from sqlalchemy import text
from app.services.iiko_auth import get_iiko_server_auth_manager
from app.core.config import settings as app_settings

logger = setup_logger(__name__)

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Легковесная миграция: добавляем новые колонки если их нет
        try:
            if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
                result = await conn.exec_driver_sql("PRAGMA table_info('dish_settings');")
                rows = result.fetchall()
                existing_cols = [row[1] for row in rows]

                if 'base_price' not in existing_cols:
                    await conn.exec_driver_sql("ALTER TABLE dish_settings ADD COLUMN base_price REAL;")
                if 'sales_quantity' not in existing_cols:
                    await conn.exec_driver_sql("ALTER TABLE dish_settings ADD COLUMN sales_quantity INTEGER;")
                if 'weight_grams' not in existing_cols:
                    await conn.exec_driver_sql("ALTER TABLE dish_settings ADD COLUMN weight_grams INTEGER DEFAULT 0;")

                # Добавление product_id в таблицу dishes для идентификации по iiko productId
                result_dishes = await conn.exec_driver_sql("PRAGMA table_info('dishes');")
                dish_cols = [row[1] for row in result_dishes.fetchall()]
                if 'product_id' not in dish_cols:
                    await conn.exec_driver_sql("ALTER TABLE dishes ADD COLUMN product_id TEXT;")
                    # Создаём уникальный индекс на product_id (NULL допускается, дубликаты NULL разрешены)
                    await conn.exec_driver_sql(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dishes_product_id ON dishes(product_id);"
                    )
        except Exception as e:
            # Логируем, но не падаем при ошибке миграции, чтобы сервер всё равно стартовал
            logger.error(f"Failed to run lightweight migration: {e}")

    # Диагностика настроек на старте: режим IIKO и публичный URL вебхука
    try:
        logger.info(
            "Startup config: IIKO_MODE=%s, IIKO_WEBHOOK_PUBLIC_URL=%s, STOPLIST_REFRESH_INTERVAL_MINUTES=%s",
            (app_settings.IIKO_MODE or ""),
            (app_settings.IIKO_WEBHOOK_PUBLIC_URL or ""),
            str(app_settings.IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES)
        )
    except Exception:
        pass

    # Initialize iikoServer authentication once at startup (persist session key/cookie)
    try:
        if (app_settings.IIKO_MODE or "cloud").lower() == "server":
            base = (app_settings.IIKO_SERVER_HOST or "").rstrip("/")
            login = app_settings.IIKO_SERVER_LOGIN
            password = app_settings.IIKO_SERVER_PASSWORD
            if base and login and password:
                mgr = get_iiko_server_auth_manager()
                mgr.configure(base, login, password)
                await mgr.ensure_authenticated()
                logger.info("iikoServer startup authentication completed successfully")
            else:
                logger.warning("iikoServer startup auth skipped: missing host/login/password in settings")
    except Exception as e:
        # Do not stop application; log error for diagnostics
        logger.error(f"iikoServer startup authentication failed: {e}")

    yield

    # Close persistent iikoServer client on shutdown
    try:
        mgr = get_iiko_server_auth_manager()
        await mgr.close()
    except Exception:
        pass
    await async_engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

# Simple health check endpoint for container orchestration
@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="warning",
        access_log=False,
    )
