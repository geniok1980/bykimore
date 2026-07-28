from typing import List

from pydantic import field_validator, Field, computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI General Chatbot"

    # Добавлены порты 3001 для фронтенд Dev-сервера Next.js
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    @classmethod
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    import json
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except Exception:
                    pass
            return [i.strip() for i in s.split(",") if i.strip()]
        if isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    LIVEKIT_URL: str = "livekit_url"
    LIVEKIT_API_KEY: str = "********"
    LIVEKIT_API_SECRET: str = "********"
    LIVEKIT_ROOM_NAME: str = "voice-assistant-room"
    LIVEKIT_HOST: str = "localhost"
    LIVEKIT_PORT: int = 7880
    LIVEKIT_REDIS_HOST: str = "localhost"
    LIVEKIT_REDIS_PORT: int = 6379
    LIVEKIT_REDIS_PASSWORD: str = ""
    LIVEKIT_TURN_ENABLED: bool = True
    LIVEKIT_TURN_DOMAIN: str = "localhost"
    LIVEKIT_TURN_TLS_PORT: int = 5349
    LIVEKIT_TURN_UDP_PORT: int = 3478

    OPENAI_API_KEY: str = "********"
    DEEPGRAM_API_KEY: str = "********"

    STT_API_URL: str = "http://10.1.2.94:8000/v1/"
    LLM_API_URL: str = "http://10.1.2.94:11434/v1/"
    TTS_API_URL: str = "http://10.1.2.94:3000/api/v1/"
    TTS_API_KEY: str = "********"

    SECRET_KEY: str = "********"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 172800

    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./app.db"

    LANGCHAIN_TRACING_V2: bool = 'true'
    LANGSMITH_ENDPOINT: str = "https: // api.smith.langchain.com"
    LANGSMITH_API_KEY: str= "********"
    LANGSMITH_PROJECT: str = "pr-only-surround-27"

    QDRANT_PORT: int = 6333
    QDRANT_HOST: str = "127.0.0.1"

    TAVILY_API_KEY: str = "********"
    FIRECRAWL_API_KEY: str = "********"
    OPENWEATHERMAP_API_KEY: str = "********"

    # Optional MCP servers; if empty, MCP is disabled
    MCP_RESEARCHER_URL: str | None = None
    MCP_SCRAPPER_URL: str | None = None

    # iiko integration settings
    # Mode can be 'cloud' or 'server'. Defaults to 'cloud'.
    IIKO_MODE: str = "cloud"
    # Base URL for iikoCloud (e.g., https://api-ru.iiko.services). If using server mode, set to your iikoServer host.
    IIKO_BASE_URL: str = "https://api-ru.iiko.services"
    # For iikoCloud: API key and organization ID
    IIKO_API_KEY: str | None = None
    IIKO_ORGANIZATION_ID: str | None = None
    # For iikoServer (on-prem): server host and login/password
    IIKO_SERVER_HOST: str | None = None
    IIKO_SERVER_LOGIN: str | None = None
    IIKO_SERVER_PASSWORD: str | None = None
    # SSL verification for iikoServer connections (set to false for self-signed certs)
    IIKO_SERVER_VERIFY_SSL: bool = True

    # iikoCloud WebHook security (optional). If set, webhook requires this shared secret
    IIKO_WEBHOOK_SECRET: str | None = None
    # Restrict processing to specific organizations (optional)
    # Read raw env as string to avoid JSON decode errors on empty values; computed property will parse it.
    IIKO_WEBHOOK_ALLOWED_ORGS_RAW: str | None = Field(default=None, env="IIKO_WEBHOOK_ALLOWED_ORGS")
    # Public webhook URL (for documentation/configuration purposes)
    IIKO_WEBHOOK_PUBLIC_URL: str | None = None
    # Optional: периодический опрос стоп-листа из iikoCloud (в минутах).
    # Если 0 или None — опрос отключён. Если > 0 — при отсутствии свежих данных и вебхуков,
    # сервер выполнит одиночное обновление из iikoCloud, когда возраст кэша превысит интервал.
    IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES: int | None = None

    # OLAP пресет и параметры фонового цикла динамического ценообразования
    IIKO_OLAP_PRESET_ID: str | None = None
    SALES_PRICING_LOOP_INTERVAL_SECONDS: int | None = 60
    # Ограничение частоты обращений к OLAP: минимальный TTL кэша результатов
    SALES_OLAP_REFRESH_INTERVAL_SECONDS: int | None = None
    SALES_OLAP_REFRESH_INTERVAL_MINUTES: int | None = None

    # Local timezone for time comparisons and logging (e.g., "Europe/Moscow")
    LOCAL_TIMEZONE: str | None = None

    @classmethod
    @field_validator("IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES", mode="before")
    def _parse_refresh_interval(cls, v: str | int | None) -> int | None:
        # Разрешаем пустую строку и None, приводим к целому и не допускаем отрицательные значения
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            try:
                iv = int(s)
            except Exception:
                # Некорректное значение — отключаем интервал
                return None
            return iv if iv >= 0 else 0
        if isinstance(v, int):
            return v if v >= 0 else 0
        # Любые другие типы — отключаем
        return None

    @computed_field(return_type=List[str])
    def IIKO_WEBHOOK_ALLOWED_ORGS(self) -> List[str]:
        """Parse allowed orgs from raw env value.
        Supports:
        - Comma-separated GUIDs: "id1,id2"
        - JSON array string: "[\"id1\", \"id2\"]"
        - Empty or missing values → []
        """
        v = self.IIKO_WEBHOOK_ALLOWED_ORGS_RAW
        if v is None:
            return []
        s = str(v).strip()
        if not s:
            return []
        # JSON array
        if s.startswith("[") and s.endswith("]"):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(i).strip() for i in parsed if str(i).strip()]
            except Exception:
                # fall through to comma-split
                pass
        # Comma-separated
        return [i.strip() for i in s.split(",") if i.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
