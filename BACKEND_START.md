# Запуск Backend (FastAPI)

## Способ 1: Через app.py (Самый простой) ✅

```bash
# Из корневой директории проекта
python app.py
```

Это запустит сервер на `http://127.0.0.1:8000` с автоперезагрузкой.

## Способ 2: Через uvicorn напрямую

```bash
# Из корневой директории проекта
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Способ 3: Через uvicorn с полным путем

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Проверка что работает

После запуска откройте в браузере:
- **API документация (Swagger):** http://127.0.0.1:8000/docs
- **OpenAPI схема:** http://127.0.0.1:8000/api/v1/openapi.json

Вы должны увидеть документацию FastAPI.

## Переменные окружения

Убедитесь что есть `.env` файл в корне проекта с необходимыми переменными (см. README.md)

## Важные порты

- **Backend (FastAPI):** `127.0.0.1:8000`
- **Frontend (Next.js):** `localhost:3000`

## Устранение проблем

### Ошибка "Module not found"
```bash
# Установите зависимости
pip install -r requirements.txt
```

### Ошибка "Port already in use"
```bash
# На Windows найти процесс на порту 8000
netstat -ano | findstr :8000
# Завершить процесс по PID
taskkill /PID <PID> /F
```

### Ошибка импорта модулей
```bash
# Убедитесь что вы в корневой директории проекта
cd c:\dev\iikopivbirja
python app.py
```

