from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # directConnection=true: connect directly to the single-node replica set
    # without resolving the rs member hostname (matters when accessed from the host).
    mongo_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongo_db: str = "forms"

    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Draft responses live until expires_at, then a TTL index removes them.
    draft_ttl_seconds: int = 7 * 24 * 3600

    # Anonymous public surface (submit/draft/upload): per-IP request budget.
    public_rate_limit: int = 30
    public_rate_window_seconds: int = 60

    # Hard cap on a single uploaded file; protects the anonymous upload endpoint.
    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()
