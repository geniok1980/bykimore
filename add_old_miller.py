"""
Скрипт для добавления в базу блюда "Пиво Старый мельник" с ценой 200 руб. и курсом 5% через API.

Авторизация поддерживается:
- через готовый токен (параметр --token или переменная окружения ACCESS_TOKEN)
- через логин/пароль администратора (параметры --username и --password, либо из .env, либо интерактивный ввод)

Особенности:
- При отсутствии токена и логина/пароля скрипт загрузит .env и попробует использовать ADMIN_USERNAME/ADMIN_PASSWORD.
- Если пользователей еще нет, скрипт попытается зарегистрировать первого пользователя (superadmin) с логином admin и паролем admin123, затем залогинится.
- Если вход не удался, скрипт предложит ввести логин/пароль интерактивно.

Примеры запуска:
  python add_old_miller.py
  python add_old_miller.py --username admin --password <пароль>

Опционально можно изменить базовый URL API, название блюда, цену и курс:
  python add_old_miller.py --base-url http://127.0.0.1:8000/api/v1 --name "Пиво Старый мельник" --price 200 --rate 5 
"""

from __future__ import annotations

import argparse
import os
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
import time


# Один общий Session для повторного использования соединений
session = requests.Session()
# По умолчанию НЕ используем системные прокси (HTTP/HTTPS_PROXY),
# чтобы запросы к localhost/127.0.0.1 не уходили через корпоративный прокси и не давали 502.
# Можно переопределить поведением через переменную окружения USE_SYSTEM_PROXIES=1
USE_SYSTEM_PROXIES = os.environ.get("USE_SYSTEM_PROXIES", "0").strip().lower()
session.trust_env = USE_SYSTEM_PROXIES in ("1", "true", "yes")
if not session.trust_env:
    print("[INFO] Системные прокси отключены для HTTP-запросов (trust_env=False)")


def request_with_retry(method: str, url: str, *, max_attempts: int = 5, backoff_base: float = 0.5, retry_statuses = (502, 503, 504), **kwargs) -> requests.Response:
    """Вспомогательная функция: выполняет HTTP-запрос с повторными попытками при временных ошибках (502/503/504) и сетевых сбоях.

    - max_attempts: число попыток
    - backoff_base: базовый коэффициент экспоненциальной задержки (0.5, 1.0, 2.0, 4.0 ...)
    - retry_statuses: перечень кодов ответов, при которых повторяем запрос
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.request(method, url, timeout=15, **kwargs)
            if resp.status_code in retry_statuses:
                # временная ошибка — повторим
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"[WARN] {method} {url} -> {resp.status_code}. Повтор через {wait:.1f}s (попытка {attempt}/{max_attempts})")
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            wait = backoff_base * (2 ** (attempt - 1))
            print(f"[WARN] Сетевая ошибка при {method} {url}: {e}. Повтор через {wait:.1f}s (попытка {attempt}/{max_attempts})")
            time.sleep(wait)
            continue
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось выполнить запрос после повторных попыток")


def wait_for_api(base_url: str, timeout: float = 30.0) -> None:
    """Ожидаем готовность API, чтобы избежать 502 во время перезапуска сервера.

    Пытаемся обратиться к нескольким публичным/полу-публичным путям:
    - <root>/openapi.json
    - <root>/docs
    - <base>/beer-exchange (ожидаем 200 или 401)
    """
    deadline = time.time() + timeout
    # Вычислим root URL (без /api/vX)
    root_url = base_url
    # Пробуем найти сегмент '/api/' и отбросить его и всё, что справа
    api_idx = root_url.find("/api/")
    if api_idx != -1:
        root_url = root_url[:api_idx]

    def is_ready() -> bool:
        # 1) /openapi.json
        try:
            r = session.get(f"{root_url}/openapi.json", timeout=5)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        # 2) /docs
        try:
            r = session.get(f"{root_url}/docs", timeout=5)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        # 3) /beer-exchange на base_url (ожидаем 200 или 401)
        try:
            r = session.get(f"{base_url}/beer-exchange", timeout=5)
            if r.status_code in (200, 401):
                return True
        except requests.RequestException:
            pass
        return False

    while time.time() < deadline:
        if is_ready():
            print("[INFO] API готов к работе.")
            return
        print("[INFO] Ожидание готовности API...")
        time.sleep(1.0)
    print("[WARN] Не удалось подтвердить готовность API, продолжаю попытку работы.")


def login(base_url: str, username: str, password: str) -> str:
    """Логин по логину/паролю администратора. Возвращает access_token."""
    # Эндпоинт принимает JSON с полями username и password
    data = {
        "username": username,
        "password": password,
    }
    last_error = None
    for path in ("/auth/login", "/login"):
        url = f"{base_url}{path}"
        resp = request_with_retry("POST", url, json=data)
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if not token:
                raise RuntimeError("В ответе не найден access_token")
            return token
        else:
            last_error = f"{resp.status_code} {resp.text}"
    raise RuntimeError(f"Не удалось авторизоваться: {last_error}")


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_dishes(base_url: str, token: str) -> List[Dict[str, Any]]:
    url = f"{base_url}/dishes"
    resp = request_with_retry("GET", url, headers=auth_headers(token))
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось получить список блюд: {resp.status_code} {resp.text}")
    return resp.json()


def find_dish_by_name(dishes: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for d in dishes:
        if d.get("name") == name:
            return d
    return None


def create_dish_with_initials(base_url: str, token: str, name: str, initial_price: Optional[float], initial_rate: Optional[float]) -> Dict[str, Any]:
    """Создать блюдо через новый эндпоинт /dishes с начальными значениями цены и курса.

    Если блюдо уже существует (400), функция бросает исключение, чтобы вызывающий код мог решить, добавлять ли цену/курс отдельно.
    """
    url = f"{base_url}/dishes"
    payload: Dict[str, Any] = {"name": name}
    if initial_price is not None:
        payload["initial_price"] = initial_price
    if initial_rate is not None:
        payload["initial_rate"] = initial_rate
    resp = request_with_retry("POST", url, json=payload, headers=auth_headers(token))
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось создать блюдо: {resp.status_code} {resp.text}")
    return resp.json()


def add_price(base_url: str, token: str, dish_id: int, value: float) -> Dict[str, Any]:
    url = f"{base_url}/prices"
    payload = {"dish_id": dish_id, "value": value}
    resp = request_with_retry("POST", url, json=payload, headers=auth_headers(token))
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось добавить цену: {resp.status_code} {resp.text}")
    return resp.json()


def add_rate(base_url: str, token: str, dish_id: int, value: float) -> Dict[str, Any]:
    url = f"{base_url}/rates"
    payload = {"dish_id": dish_id, "value": value}
    resp = request_with_retry("POST", url, json=payload, headers=auth_headers(token))
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось добавить курс: {resp.status_code} {resp.text}")
    return resp.json()


def get_beer_exchange(base_url: str, token: str) -> List[Dict[str, Any]]:
    url = f"{base_url}/beer-exchange"
    resp = request_with_retry("GET", url, headers=auth_headers(token))
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось получить Beer Exchange: {resp.status_code} {resp.text}")
    return resp.json()


def try_register_superadmin(base_url: str, username: str, password: str) -> bool:
    """Попытка зарегистрировать первого пользователя (superadmin). Возвращает True при успехе."""
    payload = {"username": username, "password": password}
    for path in ("/auth/register", "/register"):
        url = f"{base_url}{path}"
        resp = request_with_retry("POST", url, json=payload)
        if resp.status_code in (200, 201):
            return True
        # 403 означает, что регистрация закрыта (уже есть пользователи) — это не ошибка для нашего сценария
        if resp.status_code == 403:
            return False
    return False


def main():
    # Загружаем .env (если есть)
    load_dotenv()

    parser = argparse.ArgumentParser(description="Добавить 'Пиво Старый мельник' c ценой и курсом через API")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="Базовый URL API (по умолчанию http://127.0.0.1:8000/api/v1)",
    )
    parser.add_argument("--token", default=os.environ.get("ACCESS_TOKEN"), help="Готовый access token")
    parser.add_argument("--username", default=os.environ.get("ADMIN_USERNAME"), help="Логин администратора")
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"), help="Пароль администратора")
    parser.add_argument("--name", default="Пиво Старый мельник", help="Название блюда")
    parser.add_argument("--price", type=float, default=200.0, help="Цена в рублях")
    parser.add_argument("--rate", type=float, default=5.0, help="Курс/процент (например 5 означает 5%)")
    # Совместимость со старой версией CLI: воспринимаем прежние названия аргументов как алиасы
    parser.add_argument("--dish-name", dest="name", help="Алиас для --name (устаревший)" )
    parser.add_argument("--initial-price", dest="price", type=float, help="Алиас для --price (устаревший)")
    parser.add_argument("--initial-rate", dest="rate", type=float, help="Алиас для --rate (устаревший)")
    # На бэкенде тип блюда не поддерживается, добавляем аргумент для совместимости и игнорируем его
    parser.add_argument("--dish-type", dest="dish_type", help="Тип блюда (на бэкенде не используется, будет проигнорирован)")

    args = parser.parse_args()

    base_url: str = args.base_url.rstrip("/")
    token: Optional[str] = args.token

    # Предупреждение, если был передан dish_type, но бэкенд его не принимает
    if getattr(args, "dish_type", None):
        print("[WARN] Аргумент --dish-type получен, но бэкенд не поддерживает категории блюд. Значение будет проигнорировано.")

    if not token:
        # Перед началом авторизации подождём готовность API
        wait_for_api(base_url)
        # Пытаемся использовать логин/пароль из .env или дефолтные
        username = args.username or os.environ.get("ADMIN_USERNAME") or "admin"
        password = args.password or os.environ.get("ADMIN_PASSWORD") or "admin123"

        # Попытка зарегистрировать первого пользователя (если база пустая)
        print("[INFO] Проверка инициализации пользователей..." )
        try:
            try_register_superadmin(base_url, username, password)
        except Exception as e:
            print(f"[WARN] Регистрация супер-админа пропущена из-за ошибки: {e}")

        print(f"[INFO] Авторизация: username='{username}'")
        try:
            token = login(base_url, username, password)
        except Exception as e:
            print(f"[WARN] Вход не удался: {e}")
            # Интерактивный ввод — чтобы скрипт можно было запустить без аргументов
            print("[INPUT] Введите учетные данные администратора")
            username = input("Username: ").strip()
            password = input("Password: ").strip()
            token = login(base_url, username, password)
    else:
        print("[INFO] Используется переданный токен авторизации.")

    # 1) Попробовать создать блюдо через новый эндпоинт с начальными значениями
    print(f"[INFO] Создаю блюдо '{args.name}' с ценой {args.price} и курсом {args.rate} через /dishes")
    try:
        dish = create_dish_with_initials(base_url, token, args.name, args.price, args.rate)
        print(f"[OK] Создано блюдо: id={dish.get('id')}, name={dish.get('name')}")
    except Exception as e:
        msg = str(e)
        if "уже существует" in msg or "already exists" in msg or "400" in msg:
            print(f"[WARN] Блюдо уже существует, добавлю цену и курс отдельными запросами.")
            # Найти блюдо
            dishes = get_dishes(base_url, token)
            dish = find_dish_by_name(dishes, args.name)
            if not dish:
                raise RuntimeError("Не удалось найти существующее блюдо после ошибки создания")
            dish_id = int(dish["id"])  # защита от строкового id
            # Добавить цену и курс
            print(f"[INFO] Добавляю цену {args.price} руб. для блюда id={dish_id}")
            price_obj = add_price(base_url, token, dish_id, args.price)
            print(f"[OK] Цена добавлена: {price_obj}")
            print(f"[INFO] Добавляю курс {args.rate}% для блюда id={dish_id}")
            rate_obj = add_rate(base_url, token, dish_id, args.rate)
            print(f"[OK] Курс добавлен: {rate_obj}")
        else:
            raise

    # 4) Проверить агрегированный эндпоинт
    print("[INFO] Проверяю агрегированный список Beer Exchange...")
    items = get_beer_exchange(base_url, token)
    target = next((i for i in items if i.get("name") == args.name), None)
    if target:
        print("[OK] Найдено в Beer Exchange:")
        print(target)
    else:
        print("[WARN] Блюдо не найдено в Beer Exchange. Полный ответ:")
        print(items)
        print("[HINT] Если на дашборде список пуст, убедитесь, что вы вошли в систему (Beer Exchange требует токен пользователя). На фронтенде откройте страницу входа и авторизуйтесь тем же пользователем, которым выполнялся этот скрипт.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        raise