# IIKO Admin - Docker Deployment

Этот проект настроен для запуска в Docker на Ubuntu с использованием docker-compose.

## Предварительные требования

- Docker Engine 20.10+
- Docker Compose 2.0+
- Ubuntu 20.04+ (рекомендуется)

## Быстрый старт

1. **Клонируйте репозиторий:**
   ```bash
   git clone <repository-url>
   cd iikoadmin
   ```

2. **Настройте переменные окружения:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   
   Обязательно заполните следующие переменные:
   - `OPENAI_API_KEY` - ключ OpenAI API
   - `LIVEKIT_API_KEY` - ключ LiveKit API
   - `LIVEKIT_API_SECRET` - секрет LiveKit API
   - `LIVEKIT_URL` - URL LiveKit сервера
   - `SECRET_KEY` - секретный ключ для JWT (минимум 32 символа)

3. **Запустите проект:**
   ```bash
   docker-compose up -d
   ```

4. **Проверьте статус сервисов:**
   ```bash
   docker-compose ps
   ```

## Доступ к приложению

- **Frontend (Next.js):** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379
- **Qdrant:** http://localhost:6333

## Структура сервисов

### Frontend (Next.js 15)
- Порт: 3000
- Технологии: React 19, TypeScript, Tailwind CSS
- Зависимости: backend

### Backend (FastAPI)
- Порт: 8000
- Технологии: Python 3.13, FastAPI, LangChain
- Зависимости: postgres, redis, qdrant

### PostgreSQL
- Порт: 5432
- База данных: iiko_admin
- Пользователь: postgres
- Пароль: postgres

### Redis
- Порт: 6379
- Используется для кэширования

### Qdrant
- Порт: 6333 (HTTP), 6334 (gRPC)
- Векторная база данных для поиска

### Nginx (опционально)
- Порт: 80, 443
- Reverse proxy для frontend и backend

## Команды управления

### Запуск
```bash
# Запуск всех сервисов
docker-compose up -d

# Запуск конкретного сервиса
docker-compose up -d backend

# Запуск с пересборкой
docker-compose up -d --build
```

### Остановка
```bash
# Остановка всех сервисов
docker-compose down

# Остановка с удалением volumes
docker-compose down -v
```

### Логи
```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Просмотр логов конкретного сервиса
docker-compose logs -f backend
```

### Обновление
```bash
# Пересборка и перезапуск
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Мониторинг

### Проверка здоровья сервисов
```bash
# Статус всех контейнеров
docker-compose ps

# Проверка health checks
docker-compose exec backend curl -f http://localhost:8000/health
docker-compose exec frontend curl -f http://localhost:3000/api/health
```

### Подключение к базе данных
```bash
# Подключение к PostgreSQL
docker-compose exec postgres psql -U postgres -d iiko_admin

# Подключение к Redis
docker-compose exec redis redis-cli
```

## Разработка

### Локальная разработка с Docker
```bash
# Запуск только инфраструктуры
docker-compose up -d postgres redis qdrant

# Запуск backend локально
cd app
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Запуск frontend локально
cd admin-dashboard
npm run dev
```

### Отладка
```bash
# Подключение к контейнеру
docker-compose exec backend bash
docker-compose exec frontend sh

# Просмотр переменных окружения
docker-compose exec backend env
```

## Производственное развертывание

### Настройки безопасности
1. Измените пароли по умолчанию в `.env`
2. Настройте SSL сертификаты для Nginx
3. Ограничьте доступ к портам базы данных
4. Настройте firewall

### Резервное копирование
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U postgres iiko_admin > backup.sql

# Backup volumes
docker run --rm -v iikoadmin_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

### Мониторинг производства
- Настройте логирование в внешнюю систему
- Используйте health checks для автоматического перезапуска
- Мониторьте использование ресурсов

## Устранение неполадок

### Общие проблемы

1. **Порты заняты:**
   ```bash
   sudo netstat -tulpn | grep :3000
   sudo netstat -tulpn | grep :8000
   ```

2. **Недостаточно места на диске:**
   ```bash
   docker system prune -a
   docker volume prune
   ```

3. **Проблемы с разрешениями:**
   ```bash
   sudo chown -R $USER:$USER .
   ```

4. **Сервисы не запускаются:**
   ```bash
   docker-compose logs backend
   docker-compose logs frontend
   ```

### Сброс к начальному состоянию
```bash
docker-compose down -v
docker system prune -a
docker-compose up -d --build
```

## Поддержка

Для получения помощи:
1. Проверьте логи сервисов
2. Убедитесь, что все переменные окружения настроены
3. Проверьте доступность внешних API (OpenAI, LiveKit)

## Лицензия

[Укажите лицензию проекта]