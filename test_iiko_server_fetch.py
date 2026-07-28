"""
Тестовый скрипт для получения номенклатуры (всех блюд/товаров) из iikoServer.

Запуск без параметров:
  python test_iiko_server_fetch.py

Логика конфигурации:
  - Сначала пробует прочитать значения из .env:
      IIKO_SERVER_HOST, IIKO_SERVER_LOGIN, IIKO_SERVER_PASSWORD,
      IIKO_INSECURE ("1"/"true" для отключения проверки SSL), IIKO_SAVE_JSON
  - Если .env не задан, используются встроенные значения по умолчанию:
      host=https://403-115-825.iiko.it, login=admin, password=123564
  - При желании можно переопределить любые значения параметрами командной строки.

Скрипт:
  1) Авторизуется на iikoServer через /resto/api/auth
  2) Запрашивает номенклатуру через /resto/api/v2/nomenclature (с фолбэком на /resto/api/nomenclature)
  3) Печатает краткую сводку и первые элементы (имя, цена)
  4) Опционально сохраняет полный ответ в JSON-файл

Внимание: эндпоинты могут отличаться в зависимости от версии и конфигурации iikoServer.
Если ваш сервер использует другие пути, их нужно скорректировать.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List, Tuple, Optional
import os
import hashlib
import random
try:
    from dotenv import load_dotenv
except Exception:
    # Если python-dotenv не установлен, просто продолжим без .env
    def load_dotenv(*args: Any, **kwargs: Any) -> None:
        return None

import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ====== iikoCloud Stoplist helpers ======
async def iiko_cloud_get_access_token(api_key: str, verify_ssl: bool = True) -> Optional[str]:
    """Obtain iikoCloud access token using API key."""
    try:
        # Диагностика запроса токена (вариант apiLogin — чаще используется в iikoCloud)
        try:
            print("➡️ [iikoCloud] POST https://api-ru.iiko.services/api/1/access_token")
            print("   payload:")
            print(json.dumps({"apiLogin": "***" if api_key else None}, ensure_ascii=False, indent=2))
        except Exception:
            pass

        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
            # Попытка 1: используем поле apiLogin
            resp = await client.post(
                "https://api-ru.iiko.services/api/1/access_token",
                json={"apiLogin": api_key},
            )
            try:
                print(f"⬅️ [iikoCloud] access_token (apiLogin) status={resp.status_code}")
                if resp.status_code != 200:
                    txt = resp.text
                    print("   body (TEXT):")
                    print(txt if isinstance(txt, str) else str(txt))
            except Exception:
                pass
            if resp.status_code == 200:
                data = resp.json() or {}
                token = data.get("token") or data.get("access_token")
                if isinstance(token, str) and token:
                    try:
                        print(f"✅ [iikoCloud] access_token received: {token[:6]}…")
                    except Exception:
                        pass
                    return token

            # Попытка 2: некоторые инсталляции ожидают поле apiKey
            try:
                print("➡️ [iikoCloud] повторная попытка: payload с apiKey")
                print(json.dumps({"apiKey": "***" if api_key else None}, ensure_ascii=False, indent=2))
            except Exception:
                pass
            resp2 = await client.post(
                "https://api-ru.iiko.services/api/1/access_token",
                json={"apiKey": api_key},
            )
            try:
                print(f"⬅️ [iikoCloud] access_token (apiKey) status={resp2.status_code}")
                if resp2.status_code != 200:
                    txt = resp2.text
                    print("   body (TEXT):")
                    print(txt if isinstance(txt, str) else str(txt))
            except Exception:
                pass
            if resp2.status_code == 200:
                data = resp2.json() or {}
                token = data.get("token") or data.get("access_token")
                if isinstance(token, str) and token:
                    try:
                        print(f"✅ [iikoCloud] access_token received: {token[:6]}…")
                    except Exception:
                        pass
                    return token
    except Exception:
        pass
    return None


async def iiko_cloud_get_terminal_groups(token: str, organization_id: str, verify_ssl: bool = True) -> List[str]:
    """Fetch terminal group IDs for an organization."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Диагностика запроса терминальных групп
        try:
            print("➡️ [iikoCloud] POST https://api-ru.iiko.services/api/1/terminal_groups")
            print("   payload:")
            print(json.dumps({"organizationIds": [organization_id], "includeDisabled": True}, ensure_ascii=False, indent=2))
        except Exception:
            pass

        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
            # В iikoCloud ожидается список organizationIds (множественное число)
            resp = await client.post(
                "https://api-ru.iiko.services/api/1/terminal_groups",
                headers=headers,
                json={"organizationIds": [organization_id], "includeDisabled": True},
            )
            try:
                print(f"⬅️ [iikoCloud] terminal_groups status={resp.status_code}")
                body = None
                try:
                    body = resp.json()
                    print("   body (JSON):")
                    print(json.dumps(body, ensure_ascii=False, indent=2))
                except Exception:
                    txt = resp.text
                    print("   body (TEXT):")
                    print(txt if isinstance(txt, str) else str(txt))
            except Exception:
                pass
            if resp.status_code == 200:
                data = resp.json() or {}
                ids: List[str] = []
                # Возможные формы ответа:
                # 1) {"terminalGroups":[{"organizationId":"...","terminalGroups":[{"id":"..."}, ...]}]}
                # 2) {"terminalGroups":[{"items":[{"organizationId":"...","terminalGroupId":"..."}, ...]}]}
                # 3) {"groups":[{"id":"..."}, ...]}
                root = data.get("terminalGroups") or data.get("groups") or data.get("items") or []
                for entry in root:
                    sub = None
                    try:
                        sub = entry.get("terminalGroups") or entry.get("items") or entry.get("groups")
                    except Exception:
                        sub = None
                    if isinstance(sub, list):
                        for g in sub:
                            tg = None
                            try:
                                tg = (
                                    g.get("id")
                                    or g.get("terminalGroupId")
                                    or (g.get("terminalGroup") or {}).get("id")
                                )
                            except Exception:
                                tg = None
                            if tg:
                                ids.append(str(tg))
                    else:
                        # Плоская форма: сам entry является группой
                        try:
                            tg = entry.get("id") or entry.get("terminalGroupId")
                        except Exception:
                            tg = None
                        if tg:
                            ids.append(str(tg))
                return ids
    except Exception:
        pass
    return []


async def iiko_cloud_get_stop_lists(token: str, organization_id: str, terminal_group_ids: List[str], verify_ssl: bool = True) -> Dict[str, Any]:
    """Call stop_lists endpoint and return raw JSON."""
    headers = {"Authorization": f"Bearer {token}"}
    # Согласно спецификации iikoCloud, поле должно называться organizationIds (массив GUIDов)
    payload = {
        "organizationIds": [organization_id],
        "terminalGroupIds": terminal_group_ids,
    }
    try:
        # Расширенный лог запроса стоп-листа: покажем URL и полезную нагрузку
        try:
            print("➡️ [iikoCloud] POST https://api-ru.iiko.services/api/1/stop_lists")
            print("   payload:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            pass

        async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as client:
            resp = await client.post(
                "https://api-ru.iiko.services/api/1/stop_lists",
                headers=headers,
                json=payload,
            )

            # Расширенный лог ответа стоп-листа: статус и тело ответа (JSON либо текст)
            try:
                print(f"⬅️ [iikoCloud] stop_lists status={resp.status_code}")
                try:
                    body = resp.json()
                    print("   body (JSON):")
                    print(json.dumps(body, ensure_ascii=False, indent=2))
                except Exception:
                    txt = resp.text
                    print("   body (TEXT):")
                    print(txt if isinstance(txt, str) else str(txt))
            except Exception:
                pass

            if resp.status_code == 200:
                return resp.json() or {}
    except Exception:
        pass
    return {}


async def iiko_cloud_fetch_stoplist_names(api_key: str, organization_id: str, verify_ssl: bool = True) -> List[str]:
    """High-level helper: returns unique dish names present in the stoplist across terminal groups.

    The payload/shape may vary depending on iikoCloud configuration; we try multiple common shapes.
    """
    token = await iiko_cloud_get_access_token(api_key, verify_ssl=verify_ssl)
    if not token:
        try:
            print("⚠️ [iikoCloud] Не удалось получить access_token — пропускаем запрос стоп-листа")
        except Exception:
            pass
        return []
    tgroups = await iiko_cloud_get_terminal_groups(token, organization_id, verify_ssl=verify_ssl)
    if not tgroups:
        try:
            print("⚠️ [iikoCloud] Список терминальных групп пуст — пропускаем запрос стоп-листа")
        except Exception:
            pass
        return []
    raw = await iiko_cloud_get_stop_lists(token, organization_id, tgroups, verify_ssl=verify_ssl)
    names: set[str] = set()
    product_ids: set[str] = set()
    # Common shapes
    try:
        # e.g., {"items":[{"product":{"name":"..."}}]}
        items = raw.get("items") or raw.get("stopLists") or []
        for it in items:
            name = None
            try:
                prod = it.get("product") or {}
                name = prod.get("name") or it.get("name")
                pid = prod.get("id") or it.get("productId")
            except Exception:
                name = None
                pid = None
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
            if isinstance(pid, str) and pid.strip():
                product_ids.add(pid.strip())
    except Exception:
        pass
    # Alternative nested shapes per terminal groups
    try:
        tg_lists = raw.get("terminalGroupStopLists") or raw.get("groups") or []
        for entry in tg_lists:
            lst = entry.get("items") or entry.get("products") or []
            for it in lst:
                name = None
                try:
                    prod = it.get("product") or {}
                    name = prod.get("name") or it.get("name")
                    pid = prod.get("id") or it.get("productId")
                except Exception:
                    name = None
                    pid = None
                if isinstance(name, str) and name.strip():
                    names.add(name.strip())
                if isinstance(pid, str) and pid.strip():
                    product_ids.add(pid.strip())
    except Exception:
        pass
    # Если имена не удалось получить, но есть productId — попробуем запросить номенклатуру по организации и сопоставить ids→names
    if not names and product_ids:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(verify=verify_ssl, timeout=20.0) as client:
                resp = await client.post(
                    "https://api-ru.iiko.services/api/1/nomenclature",
                    headers=headers,
                    json={"organizationId": organization_id, "startRevision": 0},
                )
                if resp.status_code == 200:
                    nd = resp.json() or {}
                    prods = nd.get("items") or nd.get("products") or []
                    by_id: dict[str, str] = {}
                    for p in prods:
                        try:
                            pid = p.get("id") or p.get("productId")
                            nm = p.get("name") or p.get("productName")
                        except Exception:
                            pid = None
                            nm = None
                        if isinstance(pid, str) and pid.strip() and isinstance(nm, str) and nm.strip():
                            by_id[pid.strip()] = nm.strip()
                    for pid in product_ids:
                        nm = by_id.get(pid)
                        if isinstance(nm, str) and nm.strip():
                            names.add(nm.strip())
        except Exception:
            pass
    return sorted(names)

# ====== TTL persistence helpers (to persist per-dish decision window across restarts) ======
def _ttl_state_path() -> str:
    """Return the path for storing TTL decision state.
    Stored in storage/ttl_state.json next to the project.
    """
    try:
        base_dir = os.path.dirname(__file__)
    except Exception:
        base_dir = os.getcwd()
    storage_dir = os.path.join(base_dir, "storage")
    return os.path.join(storage_dir, "ttl_state.json")


def _load_next_change_allowed() -> Dict[str, datetime]:
    """Load {dish_name: datetime} from storage/ttl_state.json.
    If file is missing or invalid, return an empty dict.
    """
    path = _ttl_state_path()
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out: Dict[str, datetime] = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                try:
                    if isinstance(v, str) and v:
                        out[k] = datetime.fromisoformat(v)
                except Exception:
                    continue
        return out
    except Exception:
        return {}


def _save_next_change_allowed(mapping: Dict[str, datetime]) -> None:
    """Save {dish_name: datetime} to storage/ttl_state.json in ISO format.
    Create the storage directory if needed.
    """
    path = _ttl_state_path()
    try:
        storage_dir = os.path.dirname(path)
        os.makedirs(storage_dir, exist_ok=True)
        serializable: Dict[str, str] = {}
        for k, dt in (mapping or {}).items():
            try:
                if isinstance(dt, datetime):
                    serializable[k] = dt.isoformat()
            except Exception:
                continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception:
        # Silently ignore write errors to avoid breaking main loop
        pass


# ====== XML parsing helpers (поднимаем выше, чтобы не было NameError) ======
def parse_nomenclature_xml(xml_text: str) -> List[Dict[str, Any]]:
    """Пытаемся извлечь список продуктов из XML-ответа iikoServer.

    Встречаются разные форматы. Делаем best-effort:
    - Ищем элементы Product/ProductItem/Item/Dish/Position/ProductDto
    - Внутри пытаемся взять name/productName/title/Name (или атрибут name)
    - Цена: price/currentPrice/salePrice/basePrice/Price, а также поиск внутри sizePrices/prices
    """
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        raise RuntimeError(f"XML parse error: {e}")

    # Собираем кандидаты узлов товара по нескольким тегам
    product_nodes = []
    for tag in [
        "Product", "ProductItem", "Item", "Dish", "Position",
        "ProductDto", "product", "item",
    ]:
        product_nodes.extend(root.findall(f".//{tag}"))

    items: List[Dict[str, Any]] = []
    for node in product_nodes:
        # Имя товара: пробуем несколько вариантов и атрибуты
        name = (
            node.findtext("name")
            or node.findtext("productName")
            or node.findtext("title")
            or node.findtext("Name")
        )
        if not name:
            name = node.attrib.get("name") or node.attrib.get("Name") or ""

        # Цена: пробуем несколько вариантов
        price_text = (
            node.findtext("price")
            or node.findtext("currentPrice")
            or node.findtext("salePrice")
            or node.findtext("basePrice")
            or node.findtext("Price")
        )

        # Если цены нет напрямую, ищем в дочерних коллекциях sizePrices/prices
        if not price_text:
            for coll_tag in ("sizePrices", "prices", "Sizes", "SizePrices"):
                coll = node.find(coll_tag)
                if coll is not None:
                    # Ищем первый подходящий узел, содержащий price/currentPrice
                    for sub in list(coll):
                        price_text = (
                            (sub.findtext("price") or sub.findtext("Price") or sub.findtext("currentPrice"))
                        )
                        if price_text:
                            break
                if price_text:
                    break

        price_value = 0.0
        if price_text:
            try:
                price_value = float(price_text)
            except Exception:
                price_value = 0.0

        if name or price_text:
            items.append({"name": name, "price": price_value})

    # Если ничего не нашли, возможно корневой формат иной — попробуем общий поиск тегов, содержащих name+price
    if not items:
        for elem in root.iter():
            nm = elem.findtext("name") or elem.attrib.get("name")
            pr = elem.findtext("price") or elem.findtext("Price")
            if nm and pr:
                try:
                    items.append({"name": nm, "price": float(pr)})
                except Exception:
                    items.append({"name": nm, "price": 0.0})

    return items


async def fetch_nomenclature(host: str, login: str, password: str, verify_ssl: bool = True) -> Dict[str, Any]:
    """Авторизация и получение номенклатуры с iikoServer."""
    base = host.rstrip("/")
    auth_url = f"{base}/resto/api/auth"
    version_url = f"{base}/resto/api/version"
    # Кандидаты эндпоинтов номенклатуры (зависят от версии/сборки iikoServer)
    nomenclature_candidates = [
        f"{base}/resto/api/v2/nomenclature",
        f"{base}/resto/api/nomenclature",
        # Часто встречаются варианты "menu" / "dishes" / "products"
        f"{base}/resto/api/v2/menu",
        f"{base}/resto/api/menu",
        f"{base}/resto/api/v2/dishes",
        f"{base}/resto/api/dishes",
        f"{base}/resto/api/v2/products",
        f"{base}/resto/api/products",
        # Иногда встречаются каталоги
        f"{base}/resto/api/v2/catalog",
        f"{base}/resto/api/catalog",
    ]

    # Отключаем HTTP/2 для совместимости со старыми/нестандартными конфигурациями iikoServer
    async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0), http2=False, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "*/*",
    }) as client:
        # Оставляем единственный вариант авторизации, который подтвердил себя в журналах:
        # GET /resto/api/auth с параметрами login=<login>, pass=sha1(<password>)
        print(f"➡️ Авторизация: {auth_url} (login={login})")
        auth_ok = False
        last_auth_error: str = ""
        sha1_lower = hashlib.sha1(password.encode('utf-8')).hexdigest()
        auth_resp = await client.get(auth_url, params={"login": login, "pass": sha1_lower})

        try:
            auth_resp.raise_for_status()
            auth_ok = True
            print(f"✅ Авторизация успешна, статус {auth_resp.status_code}. Использован хеш sha1. Cookies: {auth_resp.cookies}")
        except httpx.HTTPStatusError as e:
            last_auth_error = f"Auth failed: {e} | Status={auth_resp.status_code} | Response: {auth_resp.text}"
            print(f"❌ Ошибка авторизации: {last_auth_error}")

        if not auth_ok:
            raise RuntimeError(last_auth_error)

        # Извлекаем session key (токен), который требуется для большинства вызовов iikoServer API
        session_key: str | None = None
        try:
            ctype = auth_resp.headers.get("Content-Type", "").lower()
            if "application/json" in ctype:
                auth_data = auth_resp.json()
                # возможные поля: key, token, session, access_token
                for k in ("key", "token", "session", "access_token"):
                    if isinstance(auth_data, dict) and auth_data.get(k):
                        session_key = str(auth_data.get(k)).strip()
                        break
            else:
                # Часто сервер отдаёт просто строку-токен
                txt = auth_resp.text.strip()
                if txt and len(txt) >= 16:  # минимальная длина для правдоподобного ключа
                    session_key = txt
        except Exception:
            pass

        if not session_key:
            # Иногда токен кладут и в cookie, но стандартный способ — параметр key
            print("ℹ️ Не удалось извлечь ключ сессии из ответа авторизации. Попробуем работать по cookies, но рекомендовано передавать ?key=TOKEN.")
        else:
            print(f"🔑 Получен session key: {session_key[:8]}…")

        print(f"✅ Авторизация подтверждена, статус {auth_resp.status_code}. Cookies: {auth_resp.cookies}")

        # Попробуем получить версию сервера — это поможет диагностике
        try:
            ver_params = {"key": session_key} if session_key else None
            ver_resp = await client.get(version_url, params=ver_params)
            if ver_resp.status_code == 200:
                print(f"ℹ️ Версия iikoServer: {ver_resp.text.strip()[:120]}")
            else:
                print(f"ℹ️ /version вернул {ver_resp.status_code}")
        except Exception as e:
            print(f"⚠️ Ошибка запроса версии сервера: {e!r}")

        # Единственный рабочий вариант: POST form-urlencoded на /resto/api/v2/entities/products/list
        # Убираем все остальные попытки, чтобы не засорять логи и не делать некорректные запросы.
        post_url = f"{base}/resto/api/v2/entities/products/list"
        print(f"➡️ [POST] Запрос номенклатуры (form-urlencoded): {post_url}")
        post_params = {"key": session_key} if session_key else None
        form_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
        }
        form_data = {
            "includeDeleted": "false",
            "revisionFrom": "-1",
        }
        try:
            nom_resp = await client.post(post_url, params=post_params, headers=form_headers, data=form_data, timeout=60.0)
            if nom_resp.status_code == 200:
                # Сперва пробуем JSON
                try:
                    data = nom_resp.json()
                    print(f"✅ Номенклатура получена с POST form-urlencoded {post_url}")
                    return data
                except json.JSONDecodeError:
                    ctype = nom_resp.headers.get('Content-Type', '').lower()
                    if 'xml' in ctype or nom_resp.text.strip().startswith('<'):
                        items = parse_nomenclature_xml(nom_resp.text)
                        if items:
                            print(f"✅ Номенклатура (XML) получена с POST form-urlencoded {post_url}, элементов: {len(items)}")
                            return {"items": items}
                        else:
                            raise RuntimeError("Ответ XML получен, но не удалось извлечь элементы номенклатуры")
                    else:
                        raise RuntimeError(f"Неизвестный формат ответа: {nom_resp.headers.get('Content-Type', '')}")
            else:
                raise RuntimeError(f"POST form-urlencoded {post_url} вернул статус {nom_resp.status_code}. Тело: {nom_resp.text[:200]}")
        except Exception as e:
            raise RuntimeError(f"Ошибка POST form-urlencoded {post_url}: {e!r}")


async def fetch_nomenclature_with_key(host: str, session_key: str | None, verify_ssl: bool = True) -> Dict[str, Any]:
    """Получение номенклатуры, используя уже имеющийся ключ сессии (без повторной авторизации).

    Это снижает нагрузку на лицензии: мы не вызываем /resto/api/auth каждый цикл,
    а переиспользуем действующий токен. При необходимости выполняйте повторную авторизацию отдельно.
    """
    base = host.rstrip("/")
    post_url = f"{base}/resto/api/v2/entities/products/list"
    form_headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
    }
    post_params = {"key": session_key} if session_key else None
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0), http2=False, follow_redirects=True) as client:
            nom_resp = await client.post(post_url, params=post_params, headers=form_headers, data={"includeDeleted": "false", "revisionFrom": "-1"}, timeout=60.0)
            if nom_resp.status_code == 200:
                try:
                    return nom_resp.json()
                except json.JSONDecodeError:
                    ctype = nom_resp.headers.get('Content-Type', '').lower()
                    if 'xml' in ctype or nom_resp.text.strip().startswith('<'):
                        items = parse_nomenclature_xml(nom_resp.text)
                        if items:
                            return {"items": items}
                        else:
                            raise RuntimeError("Ответ XML получен, но не удалось извлечь элементы номенклатуры")
                    else:
                        raise RuntimeError(f"Неизвестный формат ответа: {nom_resp.headers.get('Content-Type', '')}")
            else:
                raise RuntimeError(f"POST form-urlencoded {post_url} вернул статус {nom_resp.status_code}. Тело: {nom_resp.text[:200]}")
    except Exception as e:
        raise RuntimeError(f"Ошибка POST form-urlencoded {post_url}: {e!r}")


def extract_products_server(nomenclature: Any) -> List[Dict[str, Any]]:
    """Best-effort извлечение продуктов из ответа iikoServer (v6.4).
    Поддерживает:
    - JSON-массив продуктов;
    - JSON-объект с ключами items/products/result/data;
    - XML-строку (делегирует parse_nomenclature_xml).
    """
    # Определяем список элементов
    if isinstance(nomenclature, list):
        items = nomenclature
    elif isinstance(nomenclature, dict):
        items = (
            nomenclature.get("items")
            or nomenclature.get("products")
            or nomenclature.get("result")
            or nomenclature.get("data")
            or []
        )
    elif isinstance(nomenclature, str) and nomenclature.strip().startswith("<"):
        try:
            return parse_nomenclature_xml(nomenclature)
        except Exception:
            return []
    else:
        return []

    result: List[Dict[str, Any]] = []
    for p in items:
        if not isinstance(p, dict):
            if isinstance(p, (list, tuple)) and p and isinstance(p[0], dict):
                p = p[0]
            else:
                continue
        if "product" in p and isinstance(p["product"], dict):
            p = p["product"]

        name = p.get("name") or p.get("productName") or ""
        # Не всегда цена присутствует в этом эндпоинте — пытаемся найти в разных структурах, включая sizePrices
        price_value = None
        # 1) Простые ключи (включая вложенные объекты цены)
        for k in ("currentPrice", "salePrice", "defaultSalePrice", "price"):
            v = p.get(k)
            if isinstance(v, (int, float, str)):
                price_value = v
                if v not in (None, 0, "0", "0.0"):
                    break
            elif isinstance(v, dict):
                # Возможные варианты: {value}, {amount}, {currentPrice}, {fixedPrice}
                for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                    vv = v.get(kk)
                    if isinstance(vv, (int, float, str)):
                        price_value = vv
                        break
                if price_value is not None:
                    break
        # 2) sizePrices — часто встречается в меню/товарах
        if (price_value is None or float(str(price_value).replace(',', '.')) == 0.0) and isinstance(p.get("sizePrices"), list):
            candidates = []
            for sp in p["sizePrices"]:
                if isinstance(sp, dict):
                    v = sp.get("price") or sp.get("value") or sp.get("amount")
                    if isinstance(v, (int, float, str)):
                        try:
                            f = float(str(v).replace(',', '.'))
                            candidates.append(f)
                        except Exception:
                            pass
                    elif isinstance(v, dict):
                        for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                            vv = v.get(kk)
                            if isinstance(vv, (int, float, str)):
                                try:
                                    f = float(str(vv).replace(',', '.'))
                                    candidates.append(f)
                                    break
                                except Exception:
                                    pass
            if candidates:
                # Берём максимальную цену по размерам
                price_value = max(candidates)
        # 3) prices/priceList — альтернативные коллекции цен
        if (price_value is None or float(str(price_value).replace(',', '.')) == 0.0):
            for coll_key in ("prices", "priceList"):
                coll = p.get(coll_key)
                if isinstance(coll, list) and coll:
                    # Попробуем найти положительную цену среди элементов
                    candidates = []
                    for el in coll:
                        if isinstance(el, dict):
                            v = el.get("price") or el.get("value") or el.get("amount")
                            if isinstance(v, (int, float, str)):
                                try:
                                    f = float(str(v).replace(',', '.'))
                                    candidates.append(f)
                                except Exception:
                                    pass
                            elif isinstance(v, dict):
                                for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                                    vv = v.get(kk)
                                    if isinstance(vv, (int, float, str)):
                                        try:
                                            f = float(str(vv).replace(',', '.'))
                                            candidates.append(f)
                                            break
                                        except Exception:
                                            pass
                    if candidates:
                        price_value = max(candidates)
                        break
        try:
            price_value = float(price_value) if price_value is not None else 0.0
        except Exception:
            price_value = 0.0

        result.append({
            "id": p.get("id") or p.get("guid") or p.get("uuid"),
            "name": name,
            "code": p.get("code") or p.get("num") or p.get("sku"),
            "type": p.get("type") or p.get("productType"),
            "categoryId": p.get("categoryId") or p.get("parentId") or p.get("groupId"),
            "price": price_value,
        })

    if result:
        print(f"ℹ️ Извлечено продуктов: {len(result)}. Пример: {result[0]}")
    else:
        print("ℹ️ Не удалось извлечь продукты из ответа сервера")
    return result


async def auth_get_session_key(host: str, login: str, password: str, verify_ssl: bool = True) -> str | None:
    """Авторизуется на iikoServer и возвращает session key (TOKEN) или None.
    Повторяет логику авторизации из fetch_nomenclature.
    """
    base = host.rstrip("/")
    auth_url = f"{base}/resto/api/auth"

    async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0), http2=False, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "*/*",
    }) as client:
        # Единственный подтвержденный вариант: GET с sha1(password) в параметре 'pass'
        sha1_lower = hashlib.sha1(password.encode('utf-8')).hexdigest()
        auth_resp = await client.get(auth_url, params={"login": login, "pass": sha1_lower})

        try:
            auth_resp.raise_for_status()
        except httpx.HTTPStatusError:
            print(f"❌ Не удалось авторизоваться для обновления цен (sha1): {auth_resp.status_code} | {auth_resp.text[:200]}")
            return None

        session_key: str | None = None
        try:
            ctype = auth_resp.headers.get("Content-Type", "").lower()
            if "application/json" in ctype:
                auth_data = auth_resp.json()
                for k in ("key", "token", "session", "access_token"):
                    if isinstance(auth_data, dict) and auth_data.get(k):
                        session_key = str(auth_data.get(k)).strip()
                        break
            else:
                txt = auth_resp.text.strip()
                if txt and len(txt) >= 16:
                    session_key = txt
        except Exception:
            pass

        if not session_key:
            print("ℹ️ Не удалось извлечь ключ сессии для обновления цен")
        else:
            print(f"🔑 Ключ сессии для обновления цен: {session_key[:8]}…")
        return session_key


async def iiko_logout(host: str, session_key: Optional[str], verify_ssl: bool = True) -> bool:
    """Выполняет logout на iikoServer для освобождения слота лицензии.

    Согласно документации, выход выполняется POST-запросом:
      /resto/api/logout?key=<token>
    Также ключ может передаваться как cookie 'key'. Мы отправим и параметр, и cookie.
    Возвращает True при статусе 200, иначе False. Логи содержат краткую информацию.
    """
    try:
        base = host.rstrip("/")
        url = f"{base}/resto/api/logout"
        # Некоторые версии iikoServer ожидают ключ как @FormParam с контент-тайпом application/x-www-form-urlencoded,
        # иначе сервер отвечает 500 с сообщением про @FormParam. Поэтому отправляем form-data.
        form_data = {"key": session_key} if session_key else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        # Дополнительно передадим cookie 'key' для совместимости со старыми реализациями
        if session_key:
            headers["Cookie"] = f"key={session_key}"
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(15.0), http2=False) as client:
            resp = await client.post(url, data=form_data, headers=headers)
            ok = resp.status_code == 200
            if ok:
                txt = (resp.text or "").strip()
                print(f"👋 Logout выполнен (status=200). Ответ: {txt[:80]}")
            else:
                print(f"⚠️ Logout вернул статус {resp.status_code}. Тело: {resp.text[:200]}")
            return ok
    except Exception as e:
        print(f"⚠️ Ошибка logout: {e!r}")
        return False


def _is_unauth_error(exc: Exception) -> bool:
    """Возвращает True, если ошибка похожа на 401/403 (требуется переавторизация).

    Проверяем как явные httpx.HTTPStatusError, так и текст RuntimeError из fetch_nomenclature_with_key.
    """
    try:
        if isinstance(exc, httpx.HTTPStatusError):
            resp = getattr(exc, "response", None)
            return bool(resp and resp.status_code in (401, 403))
        txt = f"{exc!r} {exc}".lower()
        return (" 401" in txt) or ("status 401" in txt) or (" 403" in txt) or ("status 403" in txt)
    except Exception:
        return False


async def get_dishes_sales_report(
    iiko_server_url: str,
    iiko_session_token: str,
    start_date: datetime,
    end_date: datetime,
    verify_ssl: bool = True,
) -> List[Dict[str, Any]]:
    """Отчет по продажам блюд за период (пример реализован по образцу example/api.py).

    Выполняет запрос к iikoServer OLAP-отчету SALES и группирует строки по:
      - DishName (название блюда)
      - DeletedWithWriteoff (статус удаления: NOT_DELETED/DELETED_WITH_WRITEOFF/DELETED_WITHOUT_WRITEOFF)
      - DeletionComment (комментарий к удалению)

    Агрегаты (agr):
      - DishDiscountSumInt (выручка по блюду с учетом скидок)
      - DishAmountInt (количество проданных блюд)

    Возвращает список словарей-строк из XML-ответа, каждый словарь содержит значения тегов строки r.
    Формат дат для параметров from/to: ДД.ММ.ГГГГ
    """
    # Приводим базовый URL к нормальному виду
    base = iiko_server_url.rstrip('/')
    # В большинстве установок iikoServer OLAP доступен по префиксу /resto/api
    # Без префикса /resto сервер часто возвращает 404 (маршрут не найден)
    report_url = f"{base}/resto/api/reports/olap"

    headers = {
        "Cookie": f"key={iiko_session_token}",
        # Некоторые сборки iiko ожидают Accept заголовок;
        # оставим дефолт, httpx укажет приемлемый
    }
    params: List[Tuple[str, str]] = [
        ("report", "SALES"),
        ("from", start_date.strftime("%d.%m.%Y")),
        ("to", end_date.strftime("%d.%m.%Y")),
        ("groupRow", "DishName"),
        ("groupRow", "DeletedWithWriteoff"),
        ("groupRow", "DeletionComment"),
        ("agr", "DishDiscountSumInt"),
        ("agr", "DishAmountInt"),
        ("summary", "false"),
        ("key", iiko_session_token),
    ]

    rows: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(report_url, headers=headers, params=params)
            resp.raise_for_status()
            xml_text = resp.text
            root = ET.fromstring(xml_text)
            for r_elem in root.findall('r'):
                row: Dict[str, Any] = {child.tag: child.text for child in r_elem}
                rows.append(row)
    except Exception as e:
        # Возвращаем пустой список, логируем краткую ошибку в stdout
        try:
            snippet = None
            if 'resp' in locals():
                snippet = resp.text[:300] if resp.text else None
            print(f"⚠️ Ошибка отчёта по продажам блюд: {e!r}. Ответ: {snippet}")
        except Exception:
            print(f"⚠️ Ошибка отчёта по продажам блюд: {e!r}")
    return rows


def _raw_items_from_nomenclature(nomenclature: Any) -> List[Dict[str, Any]]:
    """Возвращает список исходных элементов из ответа номенклатуры (без упрощения).
    Поддерживает массив, а также объекты с ключами items/products/result/data.
    """
    if isinstance(nomenclature, list):
        return [p for p in nomenclature if isinstance(p, dict)]
    if isinstance(nomenclature, dict):
        for key in ("items", "products", "result", "data"):
            val = nomenclature.get(key)
            if isinstance(val, list):
                return [p for p in val if isinstance(p, dict)]
    return []


def _compute_price_from_product(p: Dict[str, Any]) -> float:
    """Пытается вычислить текущую цену продукта по различным полям."""
    price_value = None
    for k in ("currentPrice", "salePrice", "defaultSalePrice", "price"):
        v = p.get(k)
        if isinstance(v, (int, float, str)):
            price_value = v
            if v not in (None, 0, "0", "0.0"):
                break
    if (price_value is None or float(str(price_value).replace(',', '.')) == 0.0) and isinstance(p.get("sizePrices"), list):
        candidates = []
        for sp in p["sizePrices"]:
            if isinstance(sp, dict):
                v = sp.get("price") or sp.get("value") or sp.get("amount")
                if isinstance(v, (int, float, str)):
                    try:
                        f = float(str(v).replace(',', '.'))
                        candidates.append(f)
                    except Exception:
                        pass
        if candidates:
            price_value = max(candidates)
    if (price_value is None or float(str(price_value).replace(',', '.')) == 0.0):
        for coll_key in ("prices", "priceList"):
            coll = p.get(coll_key)
            if isinstance(coll, list) and coll:
                candidates = []
                for el in coll:
                    if isinstance(el, dict):
                        v = el.get("price") or el.get("value") or el.get("amount")
                        if isinstance(v, (int, float, str)):
                            try:
                                f = float(str(v).replace(',', '.'))
                                candidates.append(f)
                            except Exception:
                                pass
                if candidates:
                    price_value = max(candidates)
                    break
    try:
        return float(price_value) if price_value is not None else 0.0
    except Exception:
        return 0.0


async def fetch_products_by_ids_with_session(host: str, session_key: str, ids: List[str], verify_ssl: bool = True) -> List[Dict[str, Any]]:
    """Возвращает детальные продукты по их ID через /resto/api/v2/entities/products/list.
    Использует form-urlencoded с повторяющимся параметром ids, чтобы вытащить sizePrices/prices/priceList.
    """
    base_local = host.rstrip("/")
    list_urls = [
        f"{base_local}/resto/api/v2/entities/products/list",
        f"{base_local}/resto/api/v2/products/list",
    ]
    form_headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
    }
    form_data = [("includeDeleted", "false"), ("revisionFrom", "-1")]
    for i in ids:
        form_data.append(("ids", str(i)))
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0), http2=False, follow_redirects=True) as c2:
            # 1) POST form-urlencoded с повторяющимися ids
            for list_url in list_urls:
                try:
                    r = await c2.post(list_url, params={"key": session_key}, headers=form_headers, data=form_data)
                    if r.status_code == 200:
                        try:
                            data = r.json()
                        except Exception:
                            data = None
                        if isinstance(data, dict):
                            try:
                                items = extract_products_server(data)
                                if isinstance(items, list) and items:
                                    print(f"✅ Детальные продукты получены POST form-urlencoded {list_url} (ids) : {len(items)}")
                                    return items
                            except Exception:
                                pass
                            for k in ("items", "products", "dishes"):
                                arr = data.get(k)
                                if isinstance(arr, list) and arr:
                                    print(f"✅ Детальные продукты получены POST form-urlencoded {list_url} (ids) raw : {len(arr)}")
                                    return arr
                except Exception:
                    pass

            # 2) GET с ids в query
            for list_url in list_urls:
                try:
                    params = {"key": session_key, "includeDeleted": "false", "revisionFrom": "-1"}
                    # Добавляем повторяющиеся ids
                    # httpx не поддерживает повторяющиеся ключи через dict, используем список кортежей
                    params_list: List[Tuple[str, str]] = list(params.items())
                    for i in ids:
                        params_list.append(("ids", str(i)))
                    r = await c2.get(list_url, params=params_list)
                    if r.status_code == 200:
                        try:
                            data = r.json()
                        except Exception:
                            data = None
                        if isinstance(data, dict):
                            try:
                                items = extract_products_server(data)
                                if isinstance(items, list) and items:
                                    print(f"✅ Детальные продукты получены GET {list_url} (ids) : {len(items)}")
                                    return items
                            except Exception:
                                pass
                            for k in ("items", "products", "dishes"):
                                arr = data.get(k)
                                if isinstance(arr, list) and arr:
                                    print(f"✅ Детальные продукты получены GET {list_url} (ids) raw : {len(arr)}")
                                    return arr
                except Exception:
                    pass
            # Если ни один вариант не сработал — вернём пустой список
    except Exception:
        pass
    return []


async def fetch_price_categories(host: str, session_key: str, verify_ssl: bool = True) -> List[Dict[str, Any]]:
    """Пробует получить список категорий цен (price categories) из iikoServer.
    Разные сборки используют разные пути, попробуем несколько вариантов и разные форматы (POST form-urlencoded и GET).

    Возвращает список словарей с как минимум полем id (или guid/uuid), name.
    """
    base = host.rstrip("/")
    urls = [
        f"{base}/resto/api/v2/entities/priceCategories/list",
        f"{base}/resto/api/v2/priceCategories/list",
        f"{base}/resto/api/v2/entities/price-categories/list",
        f"{base}/resto/api/v2/price-categories/list",
    ]
    form_headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
    }
    form_data = [
        ("includeDeleted", "false"),
        ("revisionFrom", "-1"),
    ]
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(20.0), http2=False, follow_redirects=True) as client:
            # 1) POST form-urlencoded
            for url in urls:
                try:
                    r = await client.post(url, params={"key": session_key}, headers=form_headers, data=form_data)
                    if r.status_code == 200:
                        try:
                            data = r.json()
                        except Exception:
                            data = None
                        if isinstance(data, dict):
                            for k in ("items", "categories", "priceCategories", "list"):
                                arr = data.get(k)
                                if isinstance(arr, list) and arr:
                                    print(f"✅ Категории цен получены POST {url}: {len(arr)}")
                                    return arr
                        if isinstance(data, list) and data:
                            print(f"✅ Категории цен получены POST {url} (list): {len(data)}")
                            return data
                except Exception:
                    pass
            # 2) GET
            for url in urls:
                try:
                    r = await client.get(url, params={"key": session_key, "includeDeleted": "false", "revisionFrom": "-1"})
                    if r.status_code == 200:
                        try:
                            data = r.json()
                        except Exception:
                            data = None
                        if isinstance(data, dict):
                            for k in ("items", "categories", "priceCategories", "list"):
                                arr = data.get(k)
                                if isinstance(arr, list) and arr:
                                    print(f"✅ Категории цен получены GET {url}: {len(arr)}")
                                    return arr
                        if isinstance(data, list) and data:
                            print(f"✅ Категории цен получены GET {url} (list): {len(data)}")
                            return data
                except Exception:
                    pass
    except Exception:
        pass
    return []


async def update_product_price(host: str, session_key: str, product: Dict[str, Any], new_price: float, verify_ssl: bool = True) -> Dict[str, Any]:
    """Выполняет POST /resto/api/v2/entities/products/update для изменения цены продукта.
    По iikoServer 6.1 тело запроса — один объект с id редактируемого элемента и изменяемыми полями.
    Мы формируем тело на основе уже полученного элемента номенклатуры (product), чтобы удовлетворить валидацию
    и, при наличии sizePrices/prices, обновляем их тоже.

    Возвращает словарь с полями success (bool), status_code, body.
    """
    base = host.rstrip("/")
    update_urls = [
        f"{base}/resto/api/v2/entities/products/update",
        f"{base}/resto/api/v2/products/update",
    ]
    params = {
        "key": session_key,
        # Валидация сервера требует наличия fast code (num). Если его нет,
        # нужно разрешить автогенерацию, иначе изменение не применяется,
        # несмотря на HTTP 200 (результат будет ERROR, NUM_IS_NOT_SPECIFIED).
        "overrideFastCode": "true",
        "overrideNomenclatureCode": "false",
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Базовое тело: id + поля, которые обычно пропускают валидацию.
    pid = str(product.get("id") or product.get("guid") or product.get("uuid") or "")
    ptype = (product.get("type") or product.get("productType") or "").upper() or None
    pname = product.get("name") or product.get("productName") or None
    defaultIncludedInMenu = product.get("defaultIncludedInMenu")
    mainUnit = product.get("mainUnit")
    placeType = product.get("placeType")

    body_base: Dict[str, Any] = {"id": pid}
    if ptype:
        body_base["type"] = ptype
    if pname:
        body_base["name"] = pname
    if isinstance(defaultIncludedInMenu, bool):
        body_base["defaultIncludedInMenu"] = defaultIncludedInMenu
    if isinstance(mainUnit, str) and mainUnit:
        body_base["mainUnit"] = mainUnit
    if isinstance(placeType, str) and placeType:
        body_base["placeType"] = placeType

    # Проставляем fast code (num) если отсутствует, чтобы пройти валидацию
    num_raw = product.get("num")
    code_raw = product.get("code")
    num_val = None
    if isinstance(num_raw, int):
        num_val = num_raw
    elif isinstance(num_raw, str) and num_raw.isdigit():
        try:
            num_val = int(num_raw)
        except Exception:
            num_val = None
    elif isinstance(code_raw, str) and code_raw.isdigit():
        try:
            num_val = int(code_raw)
        except Exception:
            num_val = None
    if num_val is None and pid:
        try:
            seed = int(hashlib.sha1(pid.encode("utf-8")).hexdigest()[:8], 16)
            num_val = 10000 + (seed % 90000)
        except Exception:
            num_val = random.randint(10000, 99999)
    if isinstance(num_val, int):
        body_base["num"] = num_val

    # Всегда пытаемся обновить defaultSalePrice
    body_default_number = {**body_base, "defaultSalePrice": float(new_price)}
    body_default_object = {**body_base, "defaultSalePrice": {"value": float(new_price)}}

    # Если есть sizePrices, попробуем обновить их цены. Ищем sizeId.
    size_prices_payload: Dict[str, Any] | None = None
    # Если нужных полей нет, попробуем получить детальную информацию по товару по его id

    sps = product.get("sizePrices")
    if isinstance(sps, list) and sps:
        new_sps = []
        for sp in sps:
            if isinstance(sp, dict):
                size_id = sp.get("sizeId") or sp.get("size") or sp.get("id")
                if size_id:
                    new_sps.append({"sizeId": size_id, "price": float(new_price)})
        if new_sps:
            size_prices_payload = {**body_base, "sizePrices": new_sps}

    # Если есть prices/priceList с категориями цен, попробуем обновить их.
    price_list_payload: Dict[str, Any] | None = None
    for coll_key in ("prices", "priceList"):
        coll = product.get(coll_key)
        if isinstance(coll, list) and coll:
            new_prices = []
            for el in coll:
                if isinstance(el, dict):
                    cat_id = el.get("priceCategoryId") or el.get("category") or el.get("id")
                    if cat_id:
                        new_prices.append({"priceCategoryId": cat_id, "price": float(new_price)})
            if new_prices:
                price_list_payload = {**body_base, coll_key: new_prices}
                break

    # Если ни sizePrices, ни prices не обнаружены, попробуем получить детальные данные по товару и повторить попытку
    if not size_prices_payload and not price_list_payload and pid:
        detailed = await fetch_products_by_ids_with_session(host, session_key, [pid], verify_ssl=verify_ssl)
        if detailed:
            dp = None
            for it in detailed:
                _id = it.get("id") or it.get("guid") or it.get("uuid")
                if str(_id) == pid:
                    dp = it
                    break
            if isinstance(dp, dict):
                sps2 = dp.get("sizePrices")
                if isinstance(sps2, list) and sps2:
                    new_sps = []
                    new_sps_obj = []
                    for sp in sps2:
                        if isinstance(sp, dict):
                            size_id = sp.get("sizeId") or sp.get("size") or sp.get("id")
                            if size_id:
                                new_sps.append({"sizeId": size_id, "price": float(new_price)})
                                new_sps_obj.append({"sizeId": size_id, "price": {"currentPrice": float(new_price)}})
                    if new_sps:
                        size_prices_payload = {**body_base, "sizePrices": new_sps}
                    if new_sps_obj:
                        size_prices_payload_obj = {**body_base, "sizePrices": new_sps_obj}
                for coll_key in ("prices", "priceList"):
                    coll2 = dp.get(coll_key)
                    if isinstance(coll2, list) and coll2:
                        new_prices = []
                        new_prices_obj = []
                        for el in coll2:
                            if isinstance(el, dict):
                                cat_id = el.get("priceCategoryId") or el.get("category") or el.get("id")
                                if cat_id:
                                    new_prices.append({"priceCategoryId": cat_id, "price": float(new_price)})
                                    new_prices_obj.append({"priceCategoryId": cat_id, "price": {"value": float(new_price)}})
                        if new_prices:
                            price_list_payload = {**body_base, coll_key: new_prices}
                        if new_prices_obj and not price_list_payload:
                            price_list_payload = {**body_base, coll_key: new_prices_obj}
                        break

    # Если всё ещё нет price_list_payload, попробуем получить список категорий цен
    if not price_list_payload:
        cats = await fetch_price_categories(host, session_key, verify_ssl=verify_ssl)
        cat_ids: List[str] = []
        for c in cats:
            if isinstance(c, dict):
                cid = c.get("id") or c.get("guid") or c.get("uuid")
                if cid:
                    cat_ids.append(str(cid))
        if cat_ids:
            # Обновим цену для всех найденных категорий
            price_list_payload = {**body_base, "prices": [{"priceCategoryId": cid, "price": float(new_price)} for cid in cat_ids]}

    async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0), http2=False, follow_redirects=True) as client:
        result: Dict[str, Any] = {"success": False, "status_code": None, "body": None}

        def pack_success(r: httpx.Response) -> Dict[str, Any]:
            # Успех только если валидация прошла (result == 'SUCCESS' и нет ошибок).
            out: Dict[str, Any] = {"success": False, "status_code": r.status_code, "body": None}
            body: Any = None
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text}
            out["body"] = body
            if isinstance(body, dict):
                result_val = body.get("result")
                errors = body.get("errors")
                if (result_val == "SUCCESS") or (isinstance(errors, list) and len(errors) == 0):
                    out["success"] = True
            else:
                # Если тело не JSON-объект, считаем, что сервис вернул непредвиденный ответ;
                # не признаём это за успех, чтобы не вводить в заблуждение.
                out["success"] = False
            return out

        def pack_fail(r: httpx.Response) -> Dict[str, Any]:
            out = {"success": False, "status_code": r.status_code, "body": None}
            try:
                out["body"] = r.json()
            except Exception:
                out["body"] = {"raw": r.text}
            return out

        # Последовательно пробуем несколько вариантов тел, встречающихся в разных сборках iiko,
        # но все с ОДНИМ объектом (как в документации 6.1).
        payloads: List[Dict[str, Any]] = []
        # Начнём с обновления defaultSalePrice
        payloads.append(body_default_number)
        payloads.append(body_default_object)
        # Если есть sizePrices — отдаём варианты с обновлением sizePrices
        if size_prices_payload:
            payloads.append(size_prices_payload)
        # Альтернативный вариант: вложенный объект цены (currentPrice)
        try:
            if 'sizePrices' in size_prices_payload and isinstance(size_prices_payload['sizePrices'], list):
                alt = {**body_base, 'sizePrices': []}
                for sp in size_prices_payload['sizePrices']:
                    if isinstance(sp, dict):
                        sid = sp.get('sizeId') or sp.get('size') or sp.get('id')
                        if sid:
                            alt['sizePrices'].append({'sizeId': sid, 'price': {'currentPrice': float(new_price)}})
                if alt['sizePrices']:
                    payloads.append(alt)
        except Exception:
            pass
        # Если есть prices/priceList — отдаём варианты с обновлением прайс-листа
        if price_list_payload:
            payloads.append(price_list_payload)
            # Альтернативный вариант: вложенный объект цены (value)
            try:
                for coll_key in ("prices", "priceList"):
                    if coll_key in price_list_payload and isinstance(price_list_payload[coll_key], list):
                        alt = {**body_base, coll_key: []}
                        for el in price_list_payload[coll_key]:
                            if isinstance(el, dict):
                                cid = el.get('priceCategoryId') or el.get('category') or el.get('id')
                                if cid:
                                    alt[coll_key].append({'priceCategoryId': cid, 'price': {'value': float(new_price)}})
                        if alt[coll_key]:
                            payloads.append(alt)
            except Exception:
                pass
        # Также попробуем с альтернативными названиями полей цены (на случай нестандартных сборок)
        payloads.append({**body_base, "salePrice": float(new_price)})
        payloads.append({**body_base, "salePrice": {"value": float(new_price)}})
        payloads.append({**body_base, "price": float(new_price)})
        payloads.append({**body_base, "price": {"value": float(new_price)}})

        last_response: httpx.Response | None = None
        # Перебираем варианты URL и формы тела (один объект и массив из одного объекта)
        for url in update_urls:
            for idx, payload in enumerate(payloads, start=1):
                # 1) Как один объект
                try:
                    # Диагностика: показываем, что именно отправляем
                    try:
                        body_preview = {k: payload.get(k) for k in ("id", "num", "defaultSalePrice") if k in payload}
                        print(f"   • попытка {idx}: URL={url} params={params} body_preview={body_preview}")
                    except Exception:
                        pass
                    resp = await client.post(url, params=params, headers=headers, json=payload)
                    last_response = resp
                    if resp.status_code == 200:
                        return pack_success(resp)
                    # На ошибках 400/409 продолжаем пробовать следующие варианты
                    if resp.status_code not in (400, 409):
                        # Если статус неожиданный — попробуем следующий URL/форму
                        continue
                except Exception:
                    pass
                # 2) Как массив из одного объекта (некоторые сборки iiko ожидают список)
                try:
                    resp2 = await client.post(url, params=params, headers=headers, json=[payload])
                    last_response = resp2
                    if resp2.status_code == 200:
                        return pack_success(resp2)
                    if resp2.status_code not in (400, 409):
                        continue
                except Exception:
                    pass

        # Если дошли сюда — либо исчерпали варианты, либо получили иную ошибку
        if last_response is not None:
            return pack_fail(last_response)
        return {"success": False, "status_code": 0, "body": {"error": "no response"}}


async def increase_all_dishes_prices(
    host: str,
    login: str,
    password: str,
    nomenclature: Any,
    delta_rub: float,
    verify_ssl: bool = True,
    limit: int | None = None,
    api_base: Optional[str] = None,
    api_username: Optional[str] = None,
    api_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Увеличивает цену каждого блюда (type == 'DISH') на delta_rub.
    Использует products/update с defaultSalePrice.
    Возвращает статистику: processed, succeeded, failed.
    """
    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
    if not session_key:
        return {"processed": 0, "succeeded": 0, "failed": 0, "error": "auth_failed"}

    items = _raw_items_from_nomenclature(nomenclature)
    processed = 0
    succeeded = 0
    failed = 0
    details: List[Dict[str, Any]] = []

    # Внутренний API авторизация (если задано)
    api_token: Optional[str] = None
    if api_base and api_username and api_password:
        api_token = await api_login_and_get_token(api_base, api_username, api_password, verify_ssl=verify_ssl)
        if not api_token:
            print("⚠️ Внутренний API: не удалось авторизоваться. Синхронизация с БД будет пропущена для этой операции.")

    for p in items:
        p_type = (p.get("type") or p.get("productType") or "").upper()
        if p_type != "DISH":
            continue
        pid = p.get("id") or p.get("guid") or p.get("uuid")
        if not pid:
            continue
        old_price = _compute_price_from_product(p)
        new_price = float(old_price) + float(delta_rub)

        processed += 1
        upd = await update_product_price(host, session_key, p, new_price, verify_ssl=verify_ssl)
        if upd.get("success"):
            succeeded += 1
            # Синхронизация: добавление блюда (если нет) и запись цены/курса в нашу БД
            if api_token and api_base:
                name = p.get("name") or p.get("productName") or ""
                if not name:
                    # Фолбэк: используем id, чтобы имя не было пустым
                    name = f"BLD-{pid}"
                baseline = float(old_price)
                dish_id = await api_ensure_dish_id(api_base, api_token, name, initial_price=baseline, initial_rate=0.0, verify_ssl=verify_ssl)
                if dish_id:
                    rate_pct = _compute_rate_percent(baseline=baseline, new_value=float(new_price))
                    sync_res = await api_add_price_and_rate(api_base, api_token, dish_id, price_value=float(new_price), rate_value=float(rate_pct), verify_ssl=verify_ssl)
                    # Для диагностики
                    print(f"   ↳ БД: dish_id={dish_id} price={new_price} rate={rate_pct:.2f}% price_status={sync_res.get('price_status')} rate_status={sync_res.get('rate_status')}")
        else:
            failed += 1
        # Извлечём краткое сообщение об ошибке, если есть
        err_msg = None
        body = upd.get("body")
        if isinstance(body, dict):
            err_msg = body.get("message") or body.get("error")
            if not err_msg:
                vr = body.get("validationResults")
                if isinstance(vr, list) and vr:
                    # Возьмём первое сообщение валидации
                    first = vr[0]
                    if isinstance(first, dict):
                        err_msg = first.get("message") or first.get("error") or first.get("code")
            if not err_msg:
                raw = body.get("raw")
                if isinstance(raw, str) and raw:
                    err_msg = raw[:200]
        # Сохраним кусок ответа для диагностики
        resp_snippet = None
        try:
            if isinstance(body, dict):
                txt = json.dumps(body, ensure_ascii=False)[:300]
                resp_snippet = txt
        except Exception:
            pass
        details.append({
            "id": pid,
            "name": p.get("name") or p.get("productName"),
            "type": p_type,
            "old_price": old_price,
            "new_price": new_price,
            "status_code": upd.get("status_code"),
            "success": upd.get("success"),
            "error": err_msg,
            "update_response": resp_snippet,
        })

        if limit is not None and processed >= limit:
            break

    return {"processed": processed, "succeeded": succeeded, "failed": failed, "details": details}


# ===== Интеграция с внутренним API для синхронизации блюд/цен/курса =====
async def api_login_and_get_token(api_base: str, username: str, password: str, verify_ssl: bool = True) -> Optional[str]:
    """Авторизация во внутреннем API и получение JWT токена."""
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
            url = f"{api_base}/auth/login"
            resp = await client.post(url, json={"username": username, "password": password})
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                try:
                    # Небольшая диагностика: проверим роль текущего пользователя
                    me_url = f"{api_base}/users/me"
                    me_resp = await client.get(me_url, headers={"Authorization": f"Bearer {token}"})
                    if me_resp.status_code == 200:
                        me = me_resp.json() or {}
                        print(f"✅ Внутренний API: авторизация успешна → user={me.get('username')} role={me.get('role')}")
                    else:
                        print(f"ℹ️ Внутренний API: авторизация прошла, но /users/me вернул status={me_resp.status_code}")
                except Exception:
                    pass
                return token
            else:
                # Выведем кусок ответа, чтобы легче было диагностировать (например, неверные учётные данные)
                snippet = None
                try:
                    txt = resp.text
                    snippet = (txt[:300] + ("…" if len(txt) > 300 else "")) if txt else None
                except Exception:
                    pass
                print(f"⚠️ Внутренний API: не удалось авторизоваться (status={resp.status_code}) ответ={snippet}")
    except Exception as e:
        print(f"⚠️ Внутренний API: ошибка авторизации: {e!r}")
    return None


async def api_list_dishes(api_base: str, token: str, verify_ssl: bool = True) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
            url = f"{api_base}/dishes/"
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                return resp.json() or []
    except Exception:
        pass
    return []


async def api_ensure_dish_id(api_base: str, token: str, name: str, initial_price: Optional[float] = None, initial_rate: Optional[float] = None, verify_ssl: bool = True) -> Optional[int]:
    """Создать блюдо через внутренний API, если оно отсутствует. Возвращает dish_id."""
    # Сначала попробуем создать
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
            url = f"{api_base}/dishes/"
            payload: Dict[str, Any] = {"name": name}
            if initial_price is not None:
                payload["initial_price"] = float(initial_price)
            if initial_rate is not None:
                payload["initial_rate"] = float(initial_rate)
            resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 201:
                data = resp.json()
                dish_id = int(data.get("id")) if data and data.get("id") is not None else None
                # После создания блюда — зафиксируем базовую цену в настройках (если есть initial_price)
                try:
                    if dish_id and initial_price is not None:
                        settings_url = f"{api_base}/beer-exchange/settings/"
                        settings_payload = {
                            "dish_id": dish_id,
                            "base_price": float(initial_price),
                            # Остальные поля оставим None, чтобы создать только базовую цену
                            "min_price": None,
                            "max_price": None,
                            "step": None,
                            "sales_quantity": None,
                            "ttl_minutes": None,
                            "active": True,
                        }
                        s_resp = await client.post(settings_url, json=settings_payload, headers={"Authorization": f"Bearer {token}"})
                        # Не падаем на ошибках: если уже существует — базовая цена могла быть задана ранее
                        if s_resp.status_code not in (200, 201):
                            pass
                except Exception:
                    pass
                return dish_id
            elif resp.status_code == 400:
                # Уже существует — найдём по имени
                pass
            else:
                # Диагностика причин отказа (например, недостаточно прав 403)
                reason = None
                try:
                    body = resp.json()
                    reason = body.get("detail") or body
                except Exception:
                    try:
                        reason = resp.text[:300]
                    except Exception:
                        reason = None
                print(f"⚠️ Внутренний API: создание блюда '{name}' отклонено (status={resp.status_code}) reason={reason}")
    except Exception:
        pass
    # Получим список и найдём по имени
    dishes = await api_list_dishes(api_base, token, verify_ssl=verify_ssl)
    for d in dishes:
        if (d.get("name") or "") == name:
            try:
                dish_id = int(d.get("id"))
                # Зафиксируем базовую цену, если initial_price передан и настроек ещё нет
                try:
                    if initial_price is not None:
                        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
                            settings_url = f"{api_base}/beer-exchange/settings/"
                            settings_payload = {
                                "dish_id": dish_id,
                                "base_price": float(initial_price),
                                "min_price": None,
                                "max_price": None,
                                "step": None,
                                "sales_quantity": None,
                                "ttl_minutes": None,
                                "active": True,
                            }
                            s_resp = await client.post(settings_url, json=settings_payload, headers={"Authorization": f"Bearer {token}"})
                            # Если настройки уже существуют — сервер вернёт 200 и не должен менять base_price
                            if s_resp.status_code not in (200, 201):
                                pass
                except Exception:
                    pass
                return dish_id
            except Exception:
                return None
    return None


async def api_add_price_and_rate(api_base: str, token: str, dish_id: int, price_value: float, rate_value: float, verify_ssl: bool = True) -> Dict[str, Any]:
    """Записывает новую цену и курс через внутренний API."""
    result: Dict[str, Any] = {"price_status": None, "rate_status": None}
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
            p_resp = await client.post(f"{api_base}/prices/", json={"dish_id": dish_id, "value": float(price_value)}, headers={"Authorization": f"Bearer {token}"})
            result["price_status"] = p_resp.status_code
            if p_resp.status_code != 201:
                # Выведем краткую причину
                try:
                    body = p_resp.json()
                    print(f"⚠️ Внутренний API: запись цены отклонена (dish_id={dish_id}, status={p_resp.status_code}) reason={body}")
                except Exception:
                    try:
                        print(f"⚠️ Внутренний API: запись цены отклонена (dish_id={dish_id}, status={p_resp.status_code}) body={p_resp.text[:200]}")
                    except Exception:
                        pass
            r_resp = await client.post(f"{api_base}/rates/", json={"dish_id": dish_id, "value": float(rate_value)}, headers={"Authorization": f"Bearer {token}"})
            result["rate_status"] = r_resp.status_code
            if r_resp.status_code != 201:
                try:
                    body = r_resp.json()
                    print(f"⚠️ Внутренний API: запись курса отклонена (dish_id={dish_id}, status={r_resp.status_code}) reason={body}")
                except Exception:
                    try:
                        print(f"⚠️ Внутренний API: запись курса отклонена (dish_id={dish_id}, status={r_resp.status_code}) body={r_resp.text[:200]}")
                    except Exception:
                        pass
    except Exception as e:
        result["error"] = repr(e)
    return result


async def api_list_dish_settings(api_base: str, token: str, verify_ssl: bool = True) -> List[Dict[str, Any]]:
    """Получает список настроек динамического ценообразования блюд.

    Маршрут: /beer-exchange/settings/
    Возвращает список объектов DishSettingsRead.
    """
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
            url = f"{api_base}/beer-exchange/settings/"
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                data = resp.json() or []
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []


async def api_get_iiko_settings(api_base: str, token: str, verify_ssl: bool = True) -> Optional[Dict[str, Any]]:
    """Получить настройки интеграции iikoServer из внутреннего API.

    Маршрут: /iiko/settings/
    Возвращает объект с полями server_host, server_login, server_password, active.
    Требует авторизации (админ).
    """
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0, follow_redirects=True) as client:
            url = f"{api_base}/iiko/settings/"
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) or data is None:
                    return data
    except Exception:
        pass
    return None


async def get_dish_sales_count_v2(
    iiko_server_url: str,
    iiko_session_token: str,
    dish_name: str,
    start_dt: datetime,
    end_dt: datetime,
    verify_ssl: bool = True,
) -> float:
    """Получает количество продаж блюда за указанный интервал с точностью до времени (API v2 JSON OLAP).

    Строим payload как в example/api.py (get_unpopular_dishes_report), но фильтруем период по времени.
    Данные берём из поля 'data', затем ищем строку с DishName == dish_name и возвращаем DishAmountInt.
    Если строки нет — возвращаем 0.0.
    """
    base = iiko_server_url.rstrip('/')
    # v2 JSON OLAP также требуется вызывать через /resto/api/v2/reports/olap
    report_url = f"{base}/resto/api/v2/reports/olap"
    headers = {
        'Content-Type': 'application/json',
        'Cookie': f'key={iiko_session_token}',
    }
    payload = {
        "reportType": "SALES",
        "groupByRowFields": ["DishName"],
        "aggregateFields": ["DishAmountInt"],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "periodType": "CUSTOM",
                "from": start_dt.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "to": end_dt.strftime("%Y-%m-%dT%H:%M:%S.000"),
            },
            "DeletedWithWriteoff": {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"],
            },
            "OrderDeleted": {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"],
            },
        },
    }

    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(report_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get('data') if isinstance(data, dict) else None
            if isinstance(rows, list):
                # Ищем строку по названию блюда
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    nm = (row.get('DishName') or '').strip()
                    if nm == dish_name:
                        val = row.get('DishAmountInt')
                        try:
                            return float(val) if val is not None else 0.0
                        except Exception:
                            return 0.0
    except Exception as e:
        try:
            snippet = None
            if 'resp' in locals():
                text = resp.text
                snippet = (text[:300] + ("…" if len(text) > 300 else "")) if text else None
            print(f"⚠️ Ошибка получения продаж блюда '{dish_name}': {e!r}. Ответ: {snippet}")
        except Exception:
            print(f"⚠️ Ошибка получения продаж блюда '{dish_name}': {e!r}")
    return 0.0


async def get_dish_sales_count_by_preset(
    iiko_server_url: str,
    iiko_session_token: str,
    preset_id: str,
    dish_name: str,
    start_dt: datetime,
    end_dt: datetime,
    verify_ssl: bool = True,
) -> float:
    """Получить количество продаж блюда из OLAP-отчёта по сохранённой конфигурации (byPresetId).

    Используем только предоставленный пресет отчёта (тип SALES) с агрегатом DishAmountInt,
    группировкой по строкам DishCategory/DishName и столбцам CloseTime.

    Эндпоинт: /resto/api/v2/reports/olap/byPresetId/{presetId}
    Параметры: key, dateFrom, dateTo, summary (опционально)

    Возвращает суммарное значение DishAmountInt для указанного блюда за период [dateFrom, dateTo).
    """
    base = iiko_server_url.rstrip('/')
    report_url = f"{base}/resto/api/v2/reports/olap/byPresetId/{preset_id}"

    # В данном пресете фильтр по полю SessionID.OperDay имеет тип DATE.
    # Поэтому время указывать НЕЛЬЗЯ — иначе сервер вернёт 409 Conflict.
    # Передаём только даты в формате YYYY-MM-DD.
    # Требование: начальная дата — предыдущий день, конечная — текущий день.
    today_date = end_dt.date()
    df_date = today_date - timedelta(days=1)
    dt_date = today_date
    df = df_date.isoformat()
    dt = dt_date.isoformat()

    params = {
        "key": iiko_session_token,
        "dateFrom": df,
        "dateTo": dt,
        "summary": "false",
    }

    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(report_url, params=params)
            resp.raise_for_status()
            payload = resp.json()

            # Нам нужен подсчёт по времени: пресет группирует столбцы по CloseTime (DATETIME).
            # Хотя фильтр периода DATE, из ответа берём конкретные CloseTime и выбираем те,
            # что попадают в [start_dt, end_dt) с точностью до минут/секунд.

            total = 0.0

            def try_add(val: Any) -> None:
                nonlocal total
                try:
                    if val is not None:
                        total += float(val)
                except Exception:
                    pass

            def parse_close_time(s: Any) -> Optional[datetime]:
                if s is None:
                    return None
                if isinstance(s, datetime):
                    return s
                if not isinstance(s, str):
                    try:
                        s = str(s)
                    except Exception:
                        return None
                txt = s.strip().replace('\u00a0', ' ').replace('\xa0', ' ')
                # Возможные форматы: ISO, "dd.MM.yy HH:MM", "dd.MM.yyyy HH:MM"
                fmts = [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%d.%m.%y %H:%M",
                    "%d.%m.%Y %H:%M",
                ]
                for fmt in fmts:
                    try:
                        return datetime.strptime(txt, fmt)
                    except Exception:
                        pass
                # Попробуем отрезать секунды, если есть
                try:
                    if ':' in txt:
                        parts = txt.split(':')
                        if len(parts) >= 2:
                            candidate = ':'.join(parts[:2])
                            for fmt in ("%Y-%m-%dT%H:%M", "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
                                try:
                                    return datetime.strptime(candidate, fmt)
                                except Exception:
                                    pass
                except Exception:
                    pass
                return None

            def in_range(dt: Optional[datetime]) -> bool:
                return dt is not None and (start_dt <= dt < end_dt)

            if isinstance(payload, dict):
                # 1) Наиболее простой случай: список строк data, в каждой есть CloseTime
                rows = payload.get("data")
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        nm = (row.get("DishName") or "").strip()
                        if nm != dish_name:
                            continue
                        ct = parse_close_time(row.get("CloseTime"))
                        if in_range(ct):
                            try_add(row.get("DishAmountInt"))
                    return total

                # 2) Пивот-структура: rows/columns/values
                rows2 = payload.get("rows")
                cols2 = payload.get("columns")
                vals2 = payload.get("values") or payload.get("cells") or payload.get("table")
                row_idx_matches: List[int] = []
                col_idx_matches: List[int] = []

                # Выберем подходящие строки по DishName
                if isinstance(rows2, list):
                    for i, r in enumerate(rows2):
                        if isinstance(r, dict):
                            nm = (r.get("DishName") or r.get("name") or "").strip()
                            if nm == dish_name:
                                row_idx_matches.append(i)
                        else:
                            # иногда элементы могут быть просто названиями строк
                            try:
                                nm = str(r).strip()
                                if nm == dish_name:
                                    row_idx_matches.append(i)
                            except Exception:
                                pass

                # Выберем подходящие столбцы по CloseTime и нужному интервалу
                if isinstance(cols2, list):
                    for j, c in enumerate(cols2):
                        ct_val = None
                        if isinstance(c, dict):
                            # где-то значение может быть в c["CloseTime"] или c["name"]
                            ct_val = c.get("CloseTime") or c.get("name") or c.get("value")
                        else:
                            ct_val = c
                        ct = parse_close_time(ct_val)
                        if in_range(ct):
                            col_idx_matches.append(j)

                # Если есть совпадения, суммируем значения
                if row_idx_matches and col_idx_matches and isinstance(vals2, list):
                    # ожидаем двумерный массив: values[row][col]
                    for i in row_idx_matches:
                        if i < 0 or i >= len(vals2):
                            continue
                        row_vals = vals2[i]
                        if not isinstance(row_vals, list):
                            continue
                        for j in col_idx_matches:
                            if j < 0 or j >= len(row_vals):
                                continue
                            cell = row_vals[j]
                            if isinstance(cell, (int, float)):
                                try_add(cell)
                            elif isinstance(cell, dict):
                                # если ячейка — объект с несколькими агрегатами
                                try_add(cell.get("DishAmountInt"))
                    return total

                # 3) Фолбэк: cells плоским списком
                cells = payload.get("cells")
                if isinstance(cells, list):
                    for c in cells:
                        if not isinstance(c, dict):
                            continue
                        nm = (c.get("DishName") or "").strip()
                        if nm != dish_name:
                            continue
                        ct = parse_close_time(c.get("CloseTime") or c.get("name") or c.get("column"))
                        if in_range(ct):
                            try_add(c.get("DishAmountInt") or c.get("value"))
                    return total

            elif isinstance(payload, list):
                # Иногда data может быть верхнеуровневым списком строк
                for row in payload:
                    if not isinstance(row, dict):
                        continue
                    nm = (row.get("DishName") or "").strip()
                    if nm != dish_name:
                        continue
                    ct = parse_close_time(row.get("CloseTime") or row.get("name"))
                    if in_range(ct):
                        try_add(row.get("DishAmountInt") or row.get("value"))

            return total
    except httpx.HTTPStatusError as e:
        # Явно пробрасываем 401/403, чтобы вызывающий код мог переавторизоваться
        try:
            st = e.response.status_code if e.response is not None else None
        except Exception:
            st = None
        if st in (401, 403):
            raise
        # Прочие HTTP-ошибки: печатаем и возвращаем 0.0
        try:
            snippet = None
            if 'resp' in locals():
                text = resp.text
                snippet = (text[:300] + ("…" if len(text) > 300 else "")) if text else None
            print(f"⚠️ HTTP ошибка получения продаж по пресету для блюда '{dish_name}': {e!r}. Ответ: {snippet}")
        except Exception:
            print(f"⚠️ HTTP ошибка получения продаж по пресету для блюда '{dish_name}': {e!r}")
    except Exception as e:
        try:
            snippet = None
            if 'resp' in locals():
                text = resp.text
                snippet = (text[:300] + ("…" if len(text) > 300 else "")) if text else None
            print(f"⚠️ Ошибка получения продаж по пресету для блюда '{dish_name}': {e!r}. Ответ: {snippet}")
        except Exception:
            print(f"⚠️ Ошибка получения продаж по пресету для блюда '{dish_name}': {e!r}")
    return 0.0


async def adjust_prices_by_sales(
    host: str,
    login: str,
    password: str,
    verify_ssl: bool,
    api_base: Optional[str] = None,
    api_username: Optional[str] = None,
    api_password: Optional[str] = None,
    loop_interval_seconds: int = 60,
) -> None:
    """Периодически регулирует цены блюд на основе продаж за последние ttl_minutes.

    Алгоритм:
      - для каждого блюда из нашей БД, у которого есть активные настройки (min/max/step/sales_quantity/ttl_minutes),
        запрашиваем продажи за период [now - ttl_minutes, now].
      - если продажи >= sales_quantity — увеличиваем цену на step, иначе уменьшаем на step
      - контролируем, чтобы цена оставалась в диапазоне [min_price, max_price]
      - изменения отправляем в iiko через update_product_price
      - синхронизируем в нашу БД новую цену (и курс относительно base_price)
    """
    print("🚀 Запуск динамического ценообразования на основе продаж (по настройкам блюд из БД)")

    # Включаем поддержку iikoCloud стоп-листа по умолчанию при наличии ключей в .env.
    # Поддерживаем IIKO_API_KEY (основной) и API_CLOUD (как алиас) + IIKO_ORGANIZATION_ID.
    cloud_api_key: Optional[str] = os.getenv("IIKO_API_KEY") or os.getenv("API_CLOUD")
    cloud_org_id: Optional[str] = os.getenv("IIKO_ORGANIZATION_ID")
    # Кэш имён блюд в стоп-листе и периодический TTL-обновления, чтобы не бомбить iikoCloud на каждом цикле.
    stoplist_names: set[str] = set()
    _stoplist_last_fetch: Optional[datetime] = None
    STOPLIST_REFRESH_MINUTES = 1

    # Авторизация внутреннего API
    api_token: Optional[str] = None
    if api_base and api_username and api_password:
        api_token = await api_login_and_get_token(api_base, api_username, api_password, verify_ssl=verify_ssl)
        if not api_token:
            print("⚠️ Внутренний API: не удалось авторизоваться. Доступ к списку блюд/настроек будет недоступен.")

    if not api_token:
        print("⚠️ Для работы алгоритма требуются настройки блюд из нашей БД. Укажите --api-base/--api-username/--api-password")
        return

    # Загрузим настройки iikoServer с бэкенда, если доступны
    try:
        s = await api_get_iiko_settings(api_base, api_token, verify_ssl=verify_ssl)
        if s and s.get("active") and s.get("server_host") and s.get("server_login") and s.get("server_password"):
            host = s.get("server_host")
            login = s.get("server_login")
            password = s.get("server_password")
            print(f"🔑 iikoServer настройки получены из бэкенда: host={host} login={login}")
    except Exception:
        pass

    # Авторизация iiko
    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
    if not session_key:
        print("❌ Не удалось авторизоваться в iikoServer")
        return

    # Словарь базовых цен для расчёта курса, используем settings.base_price если задано
    baseline_by_name: Dict[str, float] = {}
    # Ограничитель частоты изменений: для каждого блюда запоминаем момент,
    # когда можно выполнять следующий пересмотр цены ("время жизни" TTL).
    # Пока текущий момент раньше следующего разрешённого пересмотра — не трогаем цену.
    # Состояние восстанавливаем из файла, чтобы переживало перезапуск.
    next_change_allowed_at: Dict[str, datetime] = _load_next_change_allowed()
    # Храним предыдущее значение TTL для каждого блюда, чтобы при изменении TTL
    # немедленно сбросить окно next_change_allowed и применить новые настройки без удаления файла.
    last_ttl_by_name: Dict[str, int] = {}
    # Аналогично храним предыдущие значения шага и порога продаж, чтобы при их изменении
    # также сбрасывать окно пересмотра и сразу применять новые параметры.
    last_step_by_name: Dict[str, float] = {}
    last_sales_threshold_by_name: Dict[str, int] = {}
    # Храним предыдущие значения границ допусков цены, чтобы при их изменении
    # также сбрасывать окно пересмотра и применять новые границы немедленно.
    last_min_price_by_name: Dict[str, Optional[float]] = {}
    last_max_price_by_name: Dict[str, Optional[float]] = {}

    while True:
        try:
            # 1) Получаем список блюд и их настройки
            dishes = await api_list_dishes(api_base, api_token, verify_ssl=verify_ssl)
            settings_list = await api_list_dish_settings(api_base, api_token, verify_ssl=verify_ssl)
            # Построим индекс настроек по dish_id
            settings_by_dish_id: Dict[int, Dict[str, Any]] = {}
            for s in settings_list:
                try:
                    if not isinstance(s, dict):
                        continue
                    did = int(s.get('dish_id'))
                    settings_by_dish_id[did] = s
                except Exception:
                    continue

            # 2) Получаем актуальную номенклатуру (для поиска текущих цен и product объектов)
            # Используем уже полученный session_key, чтобы не занимать лишний слот лицензии
            try:
                nomenclature = await fetch_nomenclature_with_key(host, session_key, verify_ssl=verify_ssl)
            except Exception as e:
                if _is_unauth_error(e):
                    # Ключ мог истечь — переавторизуемся и повторим один раз
                    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
                    if not session_key:
                        print("❌ Не удалось переавторизоваться для получения номенклатуры")
                        raise
                    nomenclature = await fetch_nomenclature_with_key(host, session_key, verify_ssl=verify_ssl)
                else:
                    raise
            raw_items = _raw_items_from_nomenclature(nomenclature)
            # Построим индекс продуктов по имени
            products_by_name: Dict[str, Dict[str, Any]] = {}
            for p in raw_items:
                nm = (p.get('name') or p.get('productName') or '').strip()
                if nm:
                    products_by_name[nm] = p

            # 2.1) Периодически обновляем стоп-лист из iikoCloud, если настроены ключи.
            if cloud_api_key and cloud_org_id:
                try:
                    if _stoplist_last_fetch is None or (datetime.now() - _stoplist_last_fetch) > timedelta(minutes=STOPLIST_REFRESH_MINUTES):
                        names = await iiko_cloud_fetch_stoplist_names(cloud_api_key, cloud_org_id, verify_ssl=verify_ssl)
                        stoplist_names = {n.strip().lower() for n in names if isinstance(n, str) and n.strip()}
                        _stoplist_last_fetch = datetime.now()
                        print(f"🛑 Обновлён стоп-лист iikoCloud: {len(stoplist_names)} позиций (TTL {STOPLIST_REFRESH_MINUTES} мин)")
                except Exception as e:
                    print(f"⚠️ Ошибка получения стоп-листа iikoCloud: {e!r}")
            else:
                # Сообщение выводим только один раз при первом цикле, чтобы не засорять лог.
                if _stoplist_last_fetch is None:
                    print("ℹ️ iikoCloud ключ/организация не настроены в .env (IIKO_API_KEY или API_CLOUD, и IIKO_ORGANIZATION_ID). Стоп-лист отключён.")
                    _stoplist_last_fetch = datetime.now()  # помечаем, чтобы больше не повторять сообщение

            # 3) Перебираем блюда из нашей БД
            processed = 0
            succeeded = 0
            failed = 0
            for d in dishes:
                if not isinstance(d, dict):
                    continue
                did = d.get('id')
                name = (d.get('name') or '').strip()
                if not did or not name:
                    continue
                # Если блюдо в стоп-листе — пропускаем изменение цены
                try:
                    if stoplist_names and name.lower() in stoplist_names:
                        print(f"⛔ [{name}] находится в стоп-листе — пропускаю изменение цены.")
                        continue
                except Exception:
                    # Любые проблемы соответствия/сравнения не должны останавливать цикл
                    pass
                s = settings_by_dish_id.get(int(did))
                if not s or not s.get('active', True):
                    continue

                # Извлечём параметры
                try:
                    min_price = float(s.get('min_price')) if s.get('min_price') is not None else None
                    max_price = float(s.get('max_price')) if s.get('max_price') is not None else None
                    step = float(s.get('step')) if s.get('step') is not None else None
                    sales_qty_threshold = int(s.get('sales_quantity')) if s.get('sales_quantity') is not None else None
                    ttl_minutes = int(s.get('ttl_minutes')) if s.get('ttl_minutes') is not None else None
                    base_price = s.get('base_price')
                    base_price = float(base_price) if base_price is not None else None
                except Exception:
                    # Некорректные значения — пропустим блюдо
                    continue

                if step is None or ttl_minutes is None or sales_qty_threshold is None:
                    # Недостаточно данных для алгоритма
                    continue

                # Найдём продукт из номенклатуры по имени
                product = products_by_name.get(name)
                if not product:
                    # Попробуем регистронезависимое совпадение
                    for nm, p in products_by_name.items():
                        if nm.lower() == name.lower():
                            product = p
                            break
                if not product:
                    print(f"ℹ️ Продукт '{name}' не найден в номенклатуре — пропускаем")
                    continue

                # Текущая цена блюда
                current_price = _compute_price_from_product(product)
                # Базовая цена для расчёта курса
                baseline = baseline_by_name.get(name)
                if baseline is None:
                    baseline = base_price if base_price is not None else current_price
                    baseline_by_name[name] = baseline

                # Если TTL для блюда изменился по сравнению с прошлым циклом —
                # сбрасываем окно пересмотра, чтобы новые настройки применились сразу.
                try:
                    prev_ttl = last_ttl_by_name.get(name)
                    if prev_ttl is not None and prev_ttl != ttl_minutes:
                        if name in next_change_allowed_at:
                            try:
                                del next_change_allowed_at[name]
                            except Exception:
                                pass
                            _save_next_change_allowed(next_change_allowed_at)
                            print(f"🔄 TTL изменился для '{name}': {prev_ttl} → {ttl_minutes}. Сбрасываем окно пересмотра цены.")
                except Exception:
                    # Не мешаем основному потоку алгоритма при любых ошибках сравнения/сброса
                    pass
                # Запоминаем текущий TTL для следующего сравнения
                try:
                    last_ttl_by_name[name] = ttl_minutes
                except Exception:
                    pass

                # Если шаг (step) или порог продаж (sales_qty_threshold) изменились —
                # также сбрасываем окно пересмотра, чтобы применить новые правила немедленно.
                try:
                    prev_step = last_step_by_name.get(name)
                    prev_threshold = last_sales_threshold_by_name.get(name)
                    step_changed = (prev_step is not None and float(prev_step) != float(step))
                    threshold_changed = (prev_threshold is not None and int(prev_threshold) != int(sales_qty_threshold))
                    if step_changed or threshold_changed:
                        if name in next_change_allowed_at:
                            try:
                                del next_change_allowed_at[name]
                            except Exception:
                                pass
                            _save_next_change_allowed(next_change_allowed_at)
                        changes = []
                        if step_changed:
                            changes.append(f"step: {prev_step} → {step}")
                        if threshold_changed:
                            changes.append(f"sales_quantity: {prev_threshold} → {sales_qty_threshold}")
                        if changes:
                            print(f"🔄 Параметры изменились для '{name}': {', '.join(changes)}. Сбрасываем окно пересмотра цены.")
                except Exception:
                    pass
                # Запоминаем текущие значения для следующего сравнения
                try:
                    last_step_by_name[name] = step
                    last_sales_threshold_by_name[name] = sales_qty_threshold
                except Exception:
                    pass

                # Если изменились границы цены (min_price/max_price) —
                # сбрасываем окно пересмотра, чтобы новые пределы действовали сразу.
                try:
                    prev_min = last_min_price_by_name.get(name)
                    prev_max = last_max_price_by_name.get(name)
                    min_changed = (
                        (prev_min is None) != (min_price is None)
                        or (prev_min is not None and min_price is not None and float(prev_min) != float(min_price))
                    )
                    max_changed = (
                        (prev_max is None) != (max_price is None)
                        or (prev_max is not None and max_price is not None and float(prev_max) != float(max_price))
                    )
                    if min_changed or max_changed:
                        if name in next_change_allowed_at:
                            try:
                                del next_change_allowed_at[name]
                            except Exception:
                                pass
                            _save_next_change_allowed(next_change_allowed_at)
                        changes = []
                        if min_changed:
                            changes.append(f"min_price: {prev_min} → {min_price}")
                        if max_changed:
                            changes.append(f"max_price: {prev_max} → {max_price}")
                        if changes:
                            print(f"🔄 Границы цены изменились для '{name}': {', '.join(changes)}. Сбрасываем окно пересмотра цены.")
                except Exception:
                    pass
                # Запоминаем текущие границы для следующего сравнения
                try:
                    last_min_price_by_name[name] = min_price
                    last_max_price_by_name[name] = max_price
                except Exception:
                    pass

                # Проверка "времени жизни" (TTL): меняем цену только один раз в период ttl_minutes.
                # Важно: продажи считаем в каждом цикле (каждую минуту), а ограничение TTL применяем
                # только в момент попытки изменить цену.
                now = datetime.now()
                next_allowed = next_change_allowed_at.get(name)

                # Период продаж: последние ttl_minutes (оценку делаем только при наступлении окна изменения)
                start_dt = now - timedelta(minutes=ttl_minutes)
                end_dt = now
                # Используем ТОЛЬКО сохранённый пресет OLAP-отчёта, предоставленный пользователем
                try:
                    sold_qty = await get_dish_sales_count_by_preset(
                        host,
                        session_key,
                        preset_id="5f79dc65-958a-4960-ae37-a7a199a29917",
                        dish_name=name,
                        start_dt=start_dt,
                        end_dt=end_dt,
                        verify_ssl=verify_ssl,
                    )
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code in (401, 403):
                        # Переавторизация и повтор
                        session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
                        sold_qty = await get_dish_sales_count_by_preset(
                            host,
                            session_key,
                            preset_id="5f79dc65-958a-4960-ae37-a7a199a29917",
                            dish_name=name,
                            start_dt=start_dt,
                            end_dt=end_dt,
                            verify_ssl=verify_ssl,
                        )
                    else:
                        raise

                # Отключаем правило «нет продаж за час → вернуть базовую цену» полностью.
                # Решение по цене зависит только от сравнения sold_qty с порогом sales_quantity:
                # ниже порога — уменьшаем на шаг; выше/равно порогу — увеличиваем на шаг.
                target = current_price
                if sold_qty >= float(sales_qty_threshold):
                    target = current_price + abs(step)
                else:
                    target = current_price - abs(step)

                # Применим ограничения
                if min_price is not None and target < min_price:
                    target = min_price
                if max_price is not None and target > max_price:
                    target = max_price

                # Если целевая цена совпадает с текущей — не изменяем цену и НЕ обновляем TTL,
                # чтобы не блокировать повторную проверку продаж в следующем минутном цикле.
                processed += 1
                if float(target) == float(current_price):
                    # print(f"   ↳ [{name}] target==current ({target}), оставляем без изменений; проверим снова через минуту")
                    continue

                # Если окно TTL ещё не истекло — учитываем продажи, но переносим изменение цены
                # на момент истечения окна (и НЕ обновляем TTL, чтобы не продлевать его без изменения).
                if next_allowed is not None and now < next_allowed:
                    # print(f"   ↳ [{name}] qty={sold_qty} порог={sales_qty_threshold}, но TTL до {next_allowed} — изменение будет выполнено при наступлении окна")
                    continue

                upd = await update_product_price(host, session_key, product, float(target), verify_ssl=verify_ssl)
                # Если ключ истёк: переавторизуемся и попробуем один раз повторить обновление
                if int(upd.get('status_code') or 0) in (401, 403):
                    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
                    upd = await update_product_price(host, session_key, product, float(target), verify_ssl=verify_ssl)
                # В любом случае, после попытки изменения — устанавливаем следующее время пересмотра (одно действие на TTL)
                next_change_allowed_at[name] = now + timedelta(minutes=ttl_minutes)
                _save_next_change_allowed(next_change_allowed_at)
                if upd.get('success'):
                    succeeded += 1
                    # Синхронизация цены и курса в нашу БД
                    rate_pct = _compute_rate_percent(baseline=float(baseline), new_value=float(target))
                    sync_res = await api_add_price_and_rate(api_base, api_token, int(did), price_value=float(target), rate_value=float(rate_pct), verify_ssl=verify_ssl)
                    print(f"   ↳ [{name}] qty={sold_qty} step={step} → price={target} (baseline={baseline} rate={rate_pct:.2f}%) status={sync_res.get('price_status')}/{sync_res.get('rate_status')}")
                else:
                    failed += 1
                    body = upd.get('body')
                    reason = None
                    if isinstance(body, dict):
                        reason = body.get('message') or body.get('error') or body.get('raw')
                    print(f"⚠️ Не удалось обновить цену для '{name}': status={upd.get('status_code')} reason={reason}")

            print(f"✅ Цикл регулировки по продажам завершён: обработано={processed}, успешных={succeeded}, ошибок={failed}")
            # Пауза
            await asyncio.sleep(loop_interval_seconds)
        except asyncio.CancelledError:
            # При отмене задачи освобождаем лицензию
            await iiko_logout(host, session_key, verify_ssl=verify_ssl)
            raise
        except KeyboardInterrupt:
            print("🛑 Остановлено пользователем.")
            # Освобождаем лицензию перед выходом
            await iiko_logout(host, session_key, verify_ssl=verify_ssl)
            return
        except Exception as e:
            print(f"⚠️ Ошибка цикла регулировки: {e!r}")
            await asyncio.sleep(loop_interval_seconds)


def _compute_rate_percent(baseline: float, new_value: float) -> float:
    """Возвращает процент изменения цены относительно базовой цены.
    Если baseline <= 0, возвращает 0, чтобы избежать деления на ноль.
    Формула: ((new - baseline) / baseline) * 100
    """
    try:
        b = float(baseline)
        n = float(new_value)
        if b <= 0:
            return 0.0
        return ((n - b) / b) * 100.0
    except Exception:
        return 0.0


async def oscillate_prices(
    host: str,
    login: str,
    password: str,
    verify_ssl: bool,
    delta_rub: float,
    upper_bound: float,
    lower_bound: float,
    interval_seconds: int,
    product_type: str = "DISH",
    api_base: Optional[str] = None,
    api_username: Optional[str] = None,
    api_password: Optional[str] = None,
) -> None:
    """Каждую минуту изменяет цены блюд на +delta_rub, пока максимальная цена не достигнет upper_bound,
    затем меняет направление и уменьшает цены на delta_rub, пока минимальная цена не достигнет lower_bound.
    Поведение повторяется бесконечно.

    Примечание: обновляется поле defaultSalePrice. Если реальные цены заданы в sizePrices/prices, может потребоваться
    адаптация логики обновления.
    """
    direction_up = True  # начинаем с увеличения
    product_type = (product_type or "DISH").upper()
    print(f"🔁 Запуск осцилляции цен: type={product_type}, delta={delta_rub}, upper={upper_bound}, lower={lower_bound}, interval={interval_seconds}s")

    # Авторизуемся один раз для операций обновления
    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
    if not session_key:
        print("❌ Не удалось авторизоваться для обновления цен (нет session key)")
        return

    # Авторизация во внутреннем API (если указаны параметры)
    api_token: Optional[str] = None
    if api_base and api_username and api_password:
        api_token = await api_login_and_get_token(api_base, api_username, api_password, verify_ssl=verify_ssl)
        if not api_token:
            print("⚠️ Внутренний API: не удалось авторизоваться. Синхронизация с БД отключена для этого запуска.")

    # Кэш базовых цен для расчёта курса (процент изменения относительно базовой цены)
    base_prices: Dict[str, float] = {}

    while True:
        try:
            # Получаем актуальную номенклатуру
            # Используем уже полученный session_key, чтобы не занимать лишний слот лицензии
            try:
                data = await fetch_nomenclature_with_key(host, session_key, verify_ssl=verify_ssl)
            except Exception as e:
                if _is_unauth_error(e):
                    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
                    data = await fetch_nomenclature_with_key(host, session_key, verify_ssl=verify_ssl)
                else:
                    raise
            raw_items = _raw_items_from_nomenclature(data)
            dishes = [p for p in raw_items if (p.get("type") or p.get("productType") or "").upper() == product_type]

            if not dishes:
                print("⚠️ Не найдено элементов указанного типа для обновления цен")
                await asyncio.sleep(interval_seconds)
                continue

            # Вычисляем цены
            prices = []
            for p in dishes:
                prices.append(_compute_price_from_product(p))
            max_price = max(prices) if prices else 0.0
            min_price = min(prices) if prices else 0.0

            # Проверяем, нужно ли поменять направление
            if direction_up and max_price >= upper_bound:
                direction_up = False
                print(f"⬇️ Достигнут верхний предел ({max_price} ≥ {upper_bound}). Меняем направление на уменьшение.")
            elif not direction_up and min_price <= lower_bound:
                direction_up = True
                print(f"⬆️ Достигнут нижний предел ({min_price} ≤ {lower_bound}). Меняем направление на увеличение.")

            # Вычисляем дельту текущего шага
            step = abs(delta_rub) if direction_up else -abs(delta_rub)
            print(f"🧮 Шаг изменения цен: {step} руб (элементов: {len(dishes)})")

            processed = 0
            succeeded = 0
            failed = 0

            for p in dishes:
                pid = p.get("id") or p.get("guid") or p.get("uuid")
                if not pid:
                    continue
                old_price = _compute_price_from_product(p)
                name = p.get("name") or p.get("productName") or ""
                if not name:
                    name = f"BLD-{pid}"
                # Базовая цена: первая увиденная цена для блюда в этом запуске
                baseline = base_prices.get(name)
                if baseline is None:
                    baseline = float(old_price)
                    base_prices[name] = baseline
                target = old_price + step
                # Ограничиваем диапазоном
                if target > upper_bound:
                    target = upper_bound
                if target < lower_bound:
                    target = lower_bound

                processed += 1
                upd = await update_product_price(host, session_key, p, float(target), verify_ssl=verify_ssl)
                if int(upd.get('status_code') or 0) in (401, 403):
                    session_key = await auth_get_session_key(host, login, password, verify_ssl=verify_ssl)
                    upd = await update_product_price(host, session_key, p, float(target), verify_ssl=verify_ssl)
                if upd.get("success"):
                    succeeded += 1
                    # Синхронизация во внутренний API: блюдо, цена и курс
                    if api_token and api_base:
                        # Создаём блюдо при необходимости с базовой ценой = baseline и начальным курсом 0%
                        dish_id = await api_ensure_dish_id(api_base, api_token, name, initial_price=float(baseline), initial_rate=0.0, verify_ssl=verify_ssl)
                        if dish_id:
                            rate_pct = _compute_rate_percent(baseline=float(baseline), new_value=float(target))
                            sync_res = await api_add_price_and_rate(api_base, api_token, dish_id, price_value=float(target), rate_value=float(rate_pct), verify_ssl=verify_ssl)
                            print(f"   ↳ БД: dish_id={dish_id} price={target} rate={rate_pct:.2f}% price_status={sync_res.get('price_status')} rate_status={sync_res.get('rate_status')}")
                else:
                    failed += 1

            print(f"✅ Цены обновлены: обработано={processed} | успешных={succeeded} | ошибок={failed}. Направление={'вверх' if direction_up else 'вниз'}. Макс/мин до шага: {max_price}/{min_price}")

            # Пауза до следующего шага
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            # При отмене задачи освобождаем лицензию
            await iiko_logout(host, session_key, verify_ssl=verify_ssl)
            raise
        except KeyboardInterrupt:
            print("🛑 Остановлено пользователем.")
            # Освобождаем лицензию перед выходом
            await iiko_logout(host, session_key, verify_ssl=verify_ssl)
            return
        except Exception as e:
            print(f"⚠️ Ошибка в цикле осцилляции: {e!r}")
            await asyncio.sleep(interval_seconds)

def main(argv: List[str]) -> int:
    # Загружаем .env, если доступен
    load_dotenv()

    parser = argparse.ArgumentParser(description="Fetch iikoServer nomenclature (dishes/products)")
    parser.add_argument("--host", required=False, default=None, help="Базовый URL iikoServer, например https://403-115-825.iiko.it")
    parser.add_argument("--login", required=False, default=None, help="Логин iikoServer")
    parser.add_argument("--password", required=False, default=None, help="Пароль iikoServer")
    parser.add_argument("--save", required=False, default=None, help="Путь для сохранения полного ответа номенклатуры в JSON")
    parser.add_argument("--insecure", action="store_true", help="Отключить проверку SSL-сертификата (verify=False)")
    parser.add_argument("--increase-rub", required=False, default=None, type=float, help="Увеличить цену каждого блюда (type=DISH) на указанную сумму, руб")
    parser.add_argument("--update-limit", required=False, default=None, type=int, help="Ограничить количество обновляемых блюд (для теста)")
    parser.add_argument("--oscillate", action="store_true", help="Запустить бесконечный цикл осцилляции цен (каждую минуту +/− delta)")
    parser.add_argument("--sales-dynamic", action="store_true", help="Запустить регулировку цен по продажам (на основе настроек блюд из БД)")
    parser.add_argument("--upper", required=False, default=300.0, type=float, help="Верхний предел цены (по достижении меняем направление на уменьшение)")
    parser.add_argument("--lower", required=False, default=100.0, type=float, help="Нижний предел цены (по достижении меняем направление на увеличение)")
    parser.add_argument("--interval-seconds", required=False, default=60, type=int, help="Интервал между изменениями цен, в секундах")
    # Новые параметры по запросу: шаг, диапазон, частота в минутах
    parser.add_argument("--step-rub", required=False, default=None, type=float, help="Шаг изменения цены, руб (используется в осцилляции)")
    parser.add_argument("--range", required=False, default=None, help="Диапазон изменения цены в формате MIN-MAX, например 100-300")
    parser.add_argument("--frequency-minutes", required=False, default=None, type=int, help="Частота изменения цены, в минутах")
    # Параметры интеграции с внутренним API
    parser.add_argument("--api-base", required=False, default=None, help="Базовый URL внутреннего API, например http://127.0.0.1:8000/api/v1")
    parser.add_argument("--api-username", required=False, default=None, help="Имя пользователя для внутреннего API (должен быть admin/superadmin)")
    parser.add_argument("--api-password", required=False, default=None, help="Пароль для внутреннего API")
    parser.add_argument("--product-type", required=False, default="DISH", help="Тип продукта для изменения цен (DISH или GOODS)")
    # Демонстрация iikoCloud стоп-листа
    parser.add_argument("--cloud-stoplist-demo", action="store_true", help="Показать стоп-лист из iikoCloud (требуются IIKO_API_KEY и IIKO_ORGANIZATION_ID)")
    parser.add_argument("--iiko-api-key", required=False, default=os.getenv("IIKO_API_KEY"), help="iikoCloud API key (по умолчанию из переменной окружения IIKO_API_KEY)")
    parser.add_argument("--iiko-organization-id", required=False, default=os.getenv("IIKO_ORGANIZATION_ID"), help="iikoCloud Organization ID (по умолчанию из переменной окружения IIKO_ORGANIZATION_ID)")
    args = parser.parse_args(argv)

    # Обработка нового параметра диапазона MIN-MAX
    if getattr(args, "range", None):
        rng = str(args.range)
        try:
            import re
            m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*$", rng)
            if m:
                lo_s, hi_s = m.group(1), m.group(2)
                lo = float(lo_s.replace(",", "."))
                hi = float(hi_s.replace(",", "."))
                if lo > hi:
                    lo, hi = hi, lo
                setattr(args, "lower", lo)
                setattr(args, "upper", hi)
                print(f"📐 Диапазон цен установлен: {lo}–{hi} руб")
            else:
                print(f"⚠️ Не удалось распознать диапазон '{rng}'. Ожидаемый формат: MIN-MAX (например, 100-300)")
        except Exception as e:
            print(f"⚠️ Ошибка обработки диапазона '{rng}': {e}")

    # Обработка нового параметра частоты в минутах
    if getattr(args, "frequency_minutes", None) is not None:
        try:
            minutes = int(args.frequency_minutes)
            if minutes > 0:
                setattr(args, "interval_seconds", minutes * 60)
                print(f"⏱️ Частота изменения цен установлена: каждые {minutes} мин")
            else:
                print("⚠️ Значение --frequency-minutes должно быть больше 0")
        except Exception as e:
            print(f"⚠️ Ошибка обработки частоты в минутах: {e}")

    # Автозапуск без параметров: включаем режим регулировки цен по продажам
    if not argv:
        print("🔧 Запуск без параметров: включаю режим регулировки цен по продажам (sales-dynamic).")
        setattr(args, "sales_dynamic", True)
        # Интервал цикла по умолчанию — 60 секунд (уже установлен выше), оставим как есть

    # Читаем значения из аргументов, .env или используем дефолты
    host = args.host or os.getenv("IIKO_SERVER_HOST") or "https://403-115-825.iiko.it"
    login = args.login or os.getenv("IIKO_SERVER_LOGIN") or "admin"
    password = args.password or os.getenv("IIKO_SERVER_PASSWORD") or "123564"
    save_path = args.save or os.getenv("IIKO_SAVE_JSON") or None
    insecure_env = os.getenv("IIKO_INSECURE", "").lower() in ("1", "true", "yes")
    insecure = args.insecure or insecure_env

    # Параметры внутреннего API (с дефолтами и поддержкой популярных имён переменных окружения)
    # Поддерживаем следующие варианты имён:
    #  - API_BASE_URL, NEXT_PUBLIC_API_BASE_URL, OUR_API_BASE
    #  - API_USERNAME, OUR_API_USER, ADMIN_USERNAME
    #  - API_PASSWORD, OUR_API_PASSWORD, ADMIN_PASSWORD
    api_base = (
        args.api_base
        or os.getenv("OUR_API_BASE")
        or os.getenv("API_BASE_URL")
        or os.getenv("NEXT_PUBLIC_API_BASE_URL")
        or "http://127.0.0.1:8000/api/v1"
    )
    api_username = (
        args.api_username
        or os.getenv("API_USERNAME")
        or os.getenv("OUR_API_USER")
        or os.getenv("ADMIN_USERNAME")
        or None
    )
    api_password = (
        args.api_password
        or os.getenv("API_PASSWORD")
        or os.getenv("OUR_API_PASSWORD")
        or os.getenv("ADMIN_PASSWORD")
        or None
    )

    async def runner() -> int:
        print(f"⚙️ Конфиг: host={host}, login={login}, insecure={insecure}, save={save_path}")
        if api_username and api_password:
            print(f"🔗 Внутренний API: base={api_base} user={api_username}")
        else:
            # Подсказка, какие переменные окружения можно задать для автологина
            print(
                "🔗 Внутренний API: параметры авторизации не заданы, синхронизация с БД будет пропущена\n"
                "   Установите переменные окружения в .env: API_BASE_URL (или NEXT_PUBLIC_API_BASE_URL), API_USERNAME, API_PASSWORD\n"
                "   или запустите скрипт с параметрами: --api-base --api-username --api-password"
            )

        # Режим демонстрации стоп-листа iikoCloud
        if getattr(args, "cloud_stoplist_demo", False):
            api_key = args.iiko_api_key or os.getenv("IIKO_API_KEY")
            org_id = args.iiko_organization_id or os.getenv("IIKO_ORGANIZATION_ID")
            if not api_key or not org_id:
                print("⚠️ Требуются IIKO_API_KEY и IIKO_ORGANIZATION_ID для запроса стоп-листа.")
                return 2
            print("🔎 Запрашиваю стоп-лист iikoCloud…")
            try:
                names = await iiko_cloud_fetch_stoplist_names(api_key, org_id, verify_ssl=not insecure)
                if names:
                    print(f"✅ Найдено позиций в стоп-листе: {len(names)}")
                    for n in names:
                        print(f" • {n}")
                else:
                    print("ℹ️ Стоп-лист пуст или не удалось получить данные.")
            except Exception as e:
                print(f"⚠️ Ошибка получения стоп-листа iikoCloud: {e!r}")
            return 0
        try:
            # Авторизуемся и получаем номенклатуру по ключу, затем выполняем logout, чтобы не держать лицензию
            session_key_init = await auth_get_session_key(host, login, password, verify_ssl=not insecure)
            if session_key_init:
                try:
                    data = await fetch_nomenclature_with_key(host, session_key_init, verify_ssl=not insecure)
                finally:
                    await iiko_logout(host, session_key_init, verify_ssl=not insecure)
            else:
                # Фолбэк: старый способ с авторизацией внутри функции
                data = await fetch_nomenclature(host, login, password, verify_ssl=not insecure)
        except Exception as e:
            # Выводим repr(e), т.к. str(e) может быть пустым в некоторых случаях сбора логов
            print(f"❌ Ошибка запроса номенклатуры: {e!r}")
            try:
                with open("iiko_fetch_debug.log", "w", encoding="utf-8") as dbg:
                    dbg.write(f"Host: {host}\nLogin: {login}\nInsecure: {insecure}\n")
                    dbg.write(f"Exception repr: {e!r}\nException str: {e}\n")
                print("📝 Детали ошибки записаны в iiko_fetch_debug.log")
            except Exception:
                pass
            return 1

        # Сохраняем полный ответ, если указан --save
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"💾 Полный ответ номенклатуры сохранён в: {save_path}")
            except Exception as e:
                print(f"⚠️ Не удалось сохранить файл {save_path}: {e}")

        # Пытаемся извлечь список продуктов
        products = extract_products_server(data)
        print(f"📊 Найдено продуктов: {len(products)}")

        # Печатаем первые 20 для проверки
        for i, prod in enumerate(products[:20], start=1):
            print(f"{i:02d}. {prod.get('name', '')} | price={prod.get('price', 0)}")

        if not products:
            print("⚠️ Список продуктов пуст. Возможно, требуется другой эндпоинт или формат ответа отличается.")

        # Если нужно увеличить цены блюд — выполняем обновление
        if args.increase_rub is not None:
            print(f"🛠 Начинаем увеличение цен блюд на {args.increase_rub} руб")
            stats = await increase_all_dishes_prices(
                host,
                login,
                password,
                data,
                args.increase_rub,
                verify_ssl=not insecure,
                limit=args.update_limit,
                api_base=api_base,
                api_username=api_username,
                api_password=api_password,
            )
            print(f"✅ Обновление завершено: обработано={stats.get('processed')} | успешных={stats.get('succeeded')} | ошибок={stats.get('failed')}")
            # Показать первые 5 результатов
            details = stats.get("details") or []
            for d in details[:5]:
                print(
                    f"• {d.get('name')} ({d.get('id')}) {d.get('old_price')} → {d.get('new_price')} "
                    f"| success={d.get('success')} | status={d.get('status_code')}"
                    f" | error={d.get('error')}"
                )
                # Дополнительно напечатаем кусок ответа сервера на обновление
                ur = d.get("update_response")
                if ur:
                    print(f"   ↳ ответ сервера: {ur}")

            # Повторная выборка конкретных продуктов для верификации (по их ID), чтобы получить реальные поля sizePrices/prices
            try:
                print("🔎 Проверка: запрашиваем детальные карточки обновлённых продуктов по ID…")
                # Небольшая пауза, чтобы сервер успел применить изменения и обновить кэш
                try:
                    await asyncio.sleep(1.0)
                except Exception:
                    pass
                to_check = details[:10] if details else []
                check_ids = [str(d.get("id")) for d in to_check if d.get("id")]
                session_key_verify = await auth_get_session_key(host, login, password, verify_ssl=not insecure)
                products_after = []
                if session_key_verify and check_ids:
                    products_after = await fetch_products_by_ids_with_session(host, session_key_verify, check_ids, verify_ssl=not insecure)
                # Если ничего не получили детально — фолбэк на общую номенклатуру
                if not products_after:
                    print("ℹ️ Детальная выдача по ID пустая, пробуем общую номенклатуру…")
                    data_after = await fetch_nomenclature(host, login, password, verify_ssl=not insecure)
                    products_after = extract_products_server(data_after)
                by_id: Dict[str, Any] = {}
                for p in products_after:
                    pid = p.get("id") or p.get("guid") or p.get("uuid")
                    if pid:
                        by_id[str(pid)] = p
                for d in to_check:
                    did = str(d.get("id"))
                    expected = d.get("new_price")
                    p_after = by_id.get(did)
                    if p_after:
                        actual = _compute_price_from_product(p_after)
                        ok = False
                        try:
                            ok = float(actual) == float(expected)
                        except Exception:
                            ok = False
                        status_txt = "совпадает" if ok else "НЕ совпадает"
                        print(f"   • {d.get('name')} ({did}) текущая цена={actual} — {status_txt} с ожиданием {expected}")
                    else:
                        print(f"   • {d.get('name')} ({did}) не найден через детальную выдачу/номенклатуру")
            except Exception as e:
                print(f"⚠️ Не удалось выполнить проверочный запрос номенклатуры: {e!r}")

        # Запуск осцилляции цен
        if args.oscillate:
            print("🔁 Запускаю бесконечный цикл осцилляции цен… Нажмите Ctrl+C для остановки.")
            await oscillate_prices(
                host=host,
                login=login,
                password=password,
                verify_ssl=not insecure,
                delta_rub=(args.step_rub if getattr(args, "step_rub", None) is not None else (args.increase_rub if args.increase_rub is not None else 5.0)),
                upper_bound=args.upper,
                lower_bound=args.lower,
                interval_seconds=args.interval_seconds,
                product_type=args.product_type,
                api_base=api_base,
                api_username=api_username,
                api_password=api_password,
            )

        # Запуск алгоритма динамической регулировки цен по продажам
        if args.sales_dynamic:
            print("📈 Запускаю регулировку цен по продажам… Нажмите Ctrl+C для остановки.")
            await adjust_prices_by_sales(
                host=host,
                login=login,
                password=password,
                verify_ssl=not insecure,
                api_base=api_base,
                api_username=api_username,
                api_password=api_password,
                loop_interval_seconds=args.interval_seconds,
            )

        return 0

    return asyncio.run(runner())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
