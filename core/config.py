import json
from pathlib import Path
from typing import Any
from pydantic import field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    class _BaseSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )
except ImportError:
    from pydantic import BaseModel
    class _BaseSettings(BaseModel):
        pass


class Settings(_BaseSettings):

    # General
    APP_NAME: str = "BaliTowerOps"
    APP_ENV: str = "development"
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8050
    DEBUG: bool = True
    PUBLIC_URL: str | None = None
    SECRET_KEY: str = "super-secret-enterprise-key-for-balitowerops"
    ALLOWED_ORIGINS: list[str] | str = [
        "http://localhost:8050",
        "http://127.0.0.1:8050",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Corporate LLM Gateway & standard env keys
    LLM_KEY: str | None = None
    LLM_URL: str | None = None
    API_LLM: str | None = None
    API_KEY_LLM: str | None = None

    # Active AI Model Configuration (Single Model: qwen-38)
    MODEL_NAME: str = "qwen-38"
    MODEL_URL: str = "http://localhost:8001/v1"
    MODEL_API_KEY: str = "dummy-key"

    # Integrations & Dispatchers (Email)
    SMTP_SERVER: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_EMAIL: str | None = None
    DEFAULT_RECIPIENT_EMAIL: str | None = None

    # File Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    DOCUMENTS_DIR: Path = BASE_DIR / "storage" / "documents"
    PENDING_DIR: Path = BASE_DIR / "storage" / "pending"
    APPROVED_DIR: Path = BASE_DIR / "storage" / "approved"
    REJECTED_DIR: Path = BASE_DIR / "storage" / "rejected"
    DATA_DIR: Path = BASE_DIR / "data"

    def model_post_init(self, __context: Any) -> None:
        def _clean(val: Any) -> Any:
            if isinstance(val, str):
                return val.strip().strip('"').strip("'")
            return val

        def _normalize_llm_url(url: str | None) -> str | None:
            if not url:
                return None
            u = _clean(url)
            if not u:
                return None
            if not (u.startswith("http://") or u.startswith("https://")):
                u = f"http://{u}"
            u = u.rstrip("/")
            if u.endswith("/models"):
                u = u[:-7].rstrip("/")
            if "/v1" not in u:
                u = f"{u}/v1"
            return u

        self.APP_NAME = _clean(self.APP_NAME)
        self.API_HOST = _clean(self.API_HOST)
        self.LLM_KEY = _clean(self.LLM_KEY)
        self.LLM_URL = _clean(self.LLM_URL)
        self.API_LLM = _clean(self.API_LLM)
        self.API_KEY_LLM = _clean(self.API_KEY_LLM)
        self.MODEL_NAME = _clean(self.MODEL_NAME)
        self.MODEL_API_KEY = _clean(self.MODEL_API_KEY)
        self.MODEL_URL = _clean(self.MODEL_URL)
        self.SMTP_SERVER = _clean(self.SMTP_SERVER)
        self.SMTP_EMAIL = _clean(self.SMTP_EMAIL)
        self.SMTP_PASSWORD = _clean(self.SMTP_PASSWORD)
        self.SMTP_USERNAME = _clean(self.SMTP_USERNAME) or self.SMTP_EMAIL
        self.DEFAULT_RECIPIENT_EMAIL = _clean(self.DEFAULT_RECIPIENT_EMAIL) or self.SMTP_EMAIL or ""
        self.PUBLIC_URL = _clean(self.PUBLIC_URL)
        self.SECRET_KEY = _clean(self.SECRET_KEY) or "super-secret-enterprise-key-for-balitowerops"
        if self.APP_ENV in ["production", "staging"] and self.SECRET_KEY in ["super-secret-enterprise-key-for-balitowerops", "super-secret-enterprise-key-for-autorestock-agent"]:
            import logging
            logging.getLogger(__name__).warning("INSECURE CONFIG: Running in production/staging with default SECRET_KEY! Please override via environment variable.")

        # Fallback for API_LLM / API_KEY_LLM alias
        if not self.LLM_URL and self.API_LLM:
            self.LLM_URL = self.API_LLM
        if not self.LLM_KEY and self.API_KEY_LLM:
            self.LLM_KEY = self.API_KEY_LLM

        # If LLM_KEY is provided, sync with MODEL_API_KEY
        if self.LLM_KEY and (self.MODEL_API_KEY in ["dummy-key", "dummy-key-for-local", "", None]):
            self.MODEL_API_KEY = self.LLM_KEY

        # Normalize and sync URLs
        if self.LLM_URL:
            self.LLM_URL = _normalize_llm_url(self.LLM_URL)
            self.MODEL_URL = self.LLM_URL
        elif self.MODEL_URL:
            self.MODEL_URL = _normalize_llm_url(self.MODEL_URL)


settings = Settings()

# Ensure directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
settings.PENDING_DIR.mkdir(parents=True, exist_ok=True)
settings.APPROVED_DIR.mkdir(parents=True, exist_ok=True)
settings.REJECTED_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_base_url(request: Any = None) -> str:
    """
    Returns the reachable base URL for interactive email action buttons and PDF download links.
    Detects public/LAN IP or request Host, preventing unroutable 127.0.0.1 in emails.
    """
    if request:
        try:
            r_url = str(request.base_url).rstrip("/")
            if "localhost" not in r_url and "127.0.0.1" not in r_url:
                return r_url
        except Exception:
            pass

    if settings.PUBLIC_URL and settings.PUBLIC_URL.strip() not in ["", "http://localhost:8050", "http://127.0.0.1:8050"]:
        return settings.PUBLIC_URL.rstrip("/")

    # Detect active LAN IP via UDP socket
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "127.0.0.1":
            return f"http://{ip}:{settings.API_PORT}"
    except Exception:
        pass

    if settings.PUBLIC_URL and settings.PUBLIC_URL.strip():
        return settings.PUBLIC_URL.rstrip("/")

    return f"http://{settings.API_HOST or '127.0.0.1'}:{settings.API_PORT}"


