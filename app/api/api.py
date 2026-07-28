from fastapi import APIRouter
from app.api.endpoints import auth, users, chat_history, dishes, prices, rates, beer_exchange, beer_exchange_settings, iiko, stream_settings, iiko_settings, iiko_webhook, bull_and_sea

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(chat_history.router, prefix="/history", tags=["chat_history"])
api_router.include_router(dishes.router, prefix="/dishes", tags=["dishes"])
api_router.include_router(prices.router, prefix="/prices", tags=["prices"])
api_router.include_router(rates.router, prefix="/rates", tags=["rates"])
api_router.include_router(beer_exchange.router, prefix="/beer-exchange", tags=["beer_exchange"])
api_router.include_router(beer_exchange_settings.router, prefix="/beer-exchange/settings", tags=["beer_exchange_settings"])
api_router.include_router(iiko.router, prefix="/iiko", tags=["iiko"])
api_router.include_router(iiko_webhook.router, prefix="/iiko", tags=["iiko_webhook"])
api_router.include_router(iiko_settings.router, prefix="/iiko/settings", tags=["iiko_settings"])
api_router.include_router(stream_settings.router, prefix="/stream-settings", tags=["stream_settings"])
api_router.include_router(bull_and_sea.router, prefix="/bull-and-sea", tags=["bull_and_sea"])
