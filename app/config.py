from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = Field(..., alias="DATABASE_URL")

    # ── TCP Server ──────────────────────────────────────────────────────────
    tcp_host: str = Field("0.0.0.0", alias="TCP_HOST")
    tcp_port: int = Field(9000, alias="TCP_PORT")
    tcp_max_connections_per_ase: int = Field(50, alias="TCP_MAX_CONNECTIONS_PER_ASE")
    tcp_connection_timeout_seconds: int = Field(30, alias="TCP_CONNECTION_TIMEOUT_SECONDS")
    tcp_max_message_bytes: int = Field(4096, alias="TCP_MAX_MESSAGE_BYTES")

    # ── Payment TTL ─────────────────────────────────────────────────────────
    payment_ttl_seconds: int = Field(300, alias="PAYMENT_TTL_SECONDS")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


settings = Settings()