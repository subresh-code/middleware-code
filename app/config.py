from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")

    # Rafiki / ILP
    rafiki_api_url: str = Field(..., alias="RAFIKI_API_URL")
    rafiki_auth_token: str = Field(..., alias="RAFIKI_AUTH_TOKEN")
    rafiki_webhook_secret: str = Field(..., alias="RAFIKI_WEBHOOK_SECRET")

    # ISO 8583 Parser
    iso8583_header_length: int = Field(2, alias="ISO8583_HEADER_LENGTH")

    # TCP Server
    tcp_host: str = Field("0.0.0.0", alias="TCP_HOST")
    tcp_port: int = Field(9000, alias="TCP_PORT")
    tcp_max_connections_per_ase: int = Field(50, alias="TCP_MAX_CONNECTIONS_PER_ASE")
    tcp_connection_timeout_seconds: int = Field(30, alias="TCP_CONNECTION_TIMEOUT_SECONDS")
    tcp_max_message_bytes: int = Field(4096, alias="TCP_MAX_MESSAGE_BYTES")

    # Payment & Settlement
    payment_ttl_seconds: int = Field(300, alias="PAYMENT_TTL_SECONDS")

    # Job Queue
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


settings = Settings()
