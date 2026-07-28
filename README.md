# Бык и Море — ресторанная админ-панель

Админ-панель для управления рестораном с интеграцией IIKO. FastAPI backend + Next.js frontend, запуск через Docker.

## Возможности

- **Интеграция с IIKO** — синхронизация меню, заказов, цен
- **Beer Exchange** — витрина сортов пива с ценами
- **Bull and Sea (Стейки и Море)** — категория стейков
- **Кухонное видеонаблюдение** — страница kitchen-live с HLS-потоками
- **AI-агент** — чат с LangGraph агентом (опрос меню, рекомендации)
- **Стриминг аудио с кухни** — WebSocket аудиопоток
- **Управление ценами** — автоматический пересчёт наценок
- **Dashboard** — графики выручки, статистика продаж
- **Администрирование пользователей**

## Быстрый старт

```bash
git clone https://github.com/geniok1980/bykimore.git
cd bykimore
cp .env.example .env
# Заполнить SECRET_KEY и CORS
docker compose up -d
```

| Сервис | Порт |
|--------|------|
| Frontend | 3100 |
| Backend API | 8001 |
| Swagger docs | 8001/docs |

## Структура

```
bykimore/
├── app/                    # FastAPI backend
│   ├── api/endpoints/      # Эндпоинты (auth, iiko, dishes, chat, etc.)
│   ├── core/               # Конфиг, security
│   ├── models/             # SQLAlchemy модели
│   ├── services/           # Бизнес-логика (iiko, streaming, etc.)
│   ├── agent/              # LangGraph AI агент
│   └── main.py
├── admin-dashboard/        # Next.js frontend
├── docker-compose.yml      # Backend + Frontend
├── Dockerfile.backend
└── Dockerfile.fetcher
```

## Настройка .env

```ini
SECRET_KEY=your-strong-secret-key
BACKEND_CORS_ORIGINS=["http://your-domain:3100"]
NEXT_PUBLIC_API_URL=http://your-server:8001/api/v1
```
