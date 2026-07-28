# Бык и Море — Docker Deployment

Ресторанная админ-панель с интеграцией IIKO. Backend: FastAPI + SQLite, Frontend: Next.js.

## Требования

- Docker Engine 20.10+
- Docker Compose 2.0+

## Быстрый старт

```bash
# Клонировать
git clone https://github.com/geniok1980/bykimore.git
cd bykimore

# Настроить .env
cp .env.example .env
nano .env

# Запустить
docker compose up -d

# Проверить
docker compose ps
```

## Доступ

| Сервис | URL |
|--------|-----|
| Frontend | http://your-server:3100 |
| Backend API | http://your-server:8001 |
| API docs | http://your-server:8001/docs |

## Настройка .env

```ini
# Обязательно изменить!
SECRET_KEY=my-strong-secret-key

# CORS — разрешённые домены для фронтенда
BACKEND_CORS_ORIGINS=["http://your-domain.com:3100","http://your-ip:3100"]

# URL, который браузер использует для запросов к API
NEXT_PUBLIC_API_URL=http://your-server-ip:8001/api/v1
```

## Команды

```bash
# Логи
docker compose logs -f
docker compose logs -f backend

# Пересборка
docker compose down
docker compose up -d --build

# Остановка
docker compose down
```

## Развёртывание на новом сервере

1. Установить Docker и Docker Compose
2. `git clone https://github.com/geniok1980/bykimore.git`
3. `cp .env.example .env` — заполнить SECRET_KEY, CORS, NEXT_PUBLIC_API_URL
4. `docker compose up -d`
5. Настроить Nginx/Caddy для SSL (опционально)
