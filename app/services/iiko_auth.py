import asyncio
import hashlib
from typing import Optional

import httpx

from app.utils.logger import setup_logger
from app.core.config import settings

logger = setup_logger(__name__)


class IikoServerAuthManager:
    """Singleton-style manager that maintains a persistent authenticated client to iikoServer.
    - Configured once (host, login, password)
    - Performs authentication once and reuses the cookie/session for subsequent requests
    - On 401/403 responses, can re-authenticate and retry
    """

    def __init__(self) -> None:
        self._base: str = ""
        self._login: str = ""
        self._password: str = ""
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._configured = False
        self._last_auth_ok = False
        self._session_key: Optional[str] = None

    def configure(self, base: str, login: str, password: str) -> None:
        # Normalize base: ensure scheme, strip trailing slash, drop trailing '/resto'
        new_base = (base or "").strip()
        if new_base and not new_base.lower().startswith(("http://", "https://")):
            new_base = f"http://{new_base}"
        new_base = new_base.rstrip("/")
        if new_base.lower().endswith("/resto"):
            new_base = new_base[:-len("/resto")]
        new_login = login or ""
        new_password = password or ""
        # If any of the critical fields changed, mark auth state invalid to force re-auth
        if new_base != self._base or new_login != self._login or new_password != self._password:
            self._last_auth_ok = False
        self._base = new_base
        self._login = new_login
        self._password = new_password
        self._configured = bool(self._base and self._login and self._password)
        logger.info("IikoServerAuthManager configured (host, login present: %s)", self._configured)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Persistent client to retain cookies/session
            # Align client defaults with the working test script for maximum compatibility
            # - Disable HTTP/2
            # - Follow redirects
            # - Provide a browser-like User-Agent and broad Accept
            self._client = httpx.AsyncClient(
                verify=bool(settings.IIKO_SERVER_VERIFY_SSL),
                http2=False,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
                },
            )
        return self._client

    async def ensure_authenticated(self) -> None:
        if not self._configured:
            raise RuntimeError("IikoServerAuthManager is not configured")
        async with self._lock:
            client = await self._ensure_client()
            if self._last_auth_ok:
                # Already authenticated; verify we still have usable auth material
                has_cookie_key = False
                try:
                    has_cookie_key = bool(client.cookies.get("key"))  # type: ignore[attr-defined]
                except Exception:
                    has_cookie_key = False
                if self._session_key or has_cookie_key:
                    # Still authenticated
                    return
                logger.warning("IikoServerAuthManager: auth appears stale (no session key and no 'key' cookie); reauthenticating")
            await self._authenticate(client)
            self._last_auth_ok = True

    async def reauthenticate(self) -> None:
        async with self._lock:
            client = await self._ensure_client()
            await self._authenticate(client)
            self._last_auth_ok = True

    async def _authenticate(self, client: httpx.AsyncClient) -> None:
        # Single working variant (per test script logs): GET /resto/api/auth with sha1(password) in 'pass'
        # We compute sha1 of the raw password (utf-8), lowercase hex digest
        auth_url = f"{self._base}/resto/api/auth"
        logger.info("IikoServerAuthManager: authenticating against %s", auth_url)
        try:
            sha1_lower = hashlib.sha1(self._password.encode("utf-8")).hexdigest()
            resp = await client.get(auth_url, params={"login": self._login, "pass": sha1_lower}, timeout=30)
            if resp.status_code == 200:
                # Capture session key from response body first (some servers return raw token or JSON)
                session_key: Optional[str] = None
                try:
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if "application/json" in ctype:
                        data = resp.json()
                        for k in ("key", "token", "session", "access_token"):
                            v = data.get(k) if isinstance(data, dict) else None
                            if v:
                                session_key = str(v).strip()
                                break
                    else:
                        txt = resp.text.strip()
                        if txt and len(txt) >= 16:
                            session_key = txt
                except Exception:
                    # ignore parsing errors, fall back to cookies
                    session_key = None

                # Fallback: try to capture from cookies (response or client jar)
                if not session_key:
                    key_cookie = resp.cookies.get("key")
                    if not key_cookie:
                        try:
                            key_cookie = client.cookies.get("key")  # type: ignore[attr-defined]
                        except Exception:
                            key_cookie = None
                    session_key = key_cookie if key_cookie else None

                self._session_key = session_key
                logger.info(
                    "IikoServerAuthManager: auth OK, session key %s",
                    (self._session_key[:8] + "…") if self._session_key else "<none>"
                )
                return
        except Exception:
            pass
        raise RuntimeError("Unable to authenticate to iikoServer")

    async def get_client(self) -> httpx.AsyncClient:
        return await self._ensure_client()

    def get_session_key(self) -> Optional[str]:
        return self._session_key

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def logout(self) -> bool:
        """Attempt to logout from iikoServer to free a license slot.
        Uses the stored session key (if any) and sends POST /resto/api/logout with
        both query param and Cookie header as some installations expect one or the other.
        Clears local session state on success and best-effort on failure.
        Returns True if HTTP 200 was received, False otherwise.
        """
        try:
            if not self._base:
                logger.warning("IikoServerAuthManager.logout: base URL is not configured")
                return False
            client = await self._ensure_client()
            # Try to read key from our stored session_key or from cookies
            key = self._session_key
            try:
                if not key:
                    key = client.cookies.get("key")  # type: ignore[attr-defined]
            except Exception:
                pass
            url = f"{self._base}/resto/api/logout"
            data = {"key": key} if key else None
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if key:
                headers["Cookie"] = f"key={key}"
            logger.info("IikoServerAuthManager: POST logout to %s (key present: %s)", url, bool(key))
            try:
                resp = await client.post(url, data=data, headers=headers, timeout=15)
            except Exception as e:
                logger.error("Logout request failed: %r", e)
                resp = None
            ok = bool(resp and resp.status_code == 200)
            if ok:
                txt = (resp.text or "").strip() if resp else ""
                logger.info("iikoServer logout OK (200). Body: %s", txt[:120])
            else:
                code = resp.status_code if resp else None
                body = (resp.text or "")[:200] if resp else "<no response>"
                logger.warning("iikoServer logout status=%s. Body: %s", code, body)
            # Clear session state regardless to avoid keeping license occupied
            self._session_key = None
            try:
                # Best-effort cookie removal
                client.cookies.clear()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Optionally close client to drop any persistent connection
            try:
                await self.close()
            except Exception:
                pass
            return ok
        except Exception:
            logger.error("IikoServerAuthManager.logout: unexpected error")
            return False


_manager = IikoServerAuthManager()


def get_iiko_server_auth_manager() -> IikoServerAuthManager:
    return _manager