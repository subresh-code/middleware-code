"""
Configuration Management for Middleware

Centralized configuration using Pydantic for validation and type safety.
Supports environment variables and config files.
"""

import os
from pydantic import BaseSettings, Field
from typing import Optional


class MiddlewareConfig(BaseSettings):
    """
    Global configuration for the middleware system.
    """

    # Server settings
    host: str = Field(default="0.0.0.0", env="MIDDLEWARE_HOST")
    port: int = Field(default=8583, env="MIDDLEWARE_PORT")
    max_connections: int = Field(default=100, env="MAX_CONNECTIONS")

    # Rafiki settings
    rafiki_base_url: str = Field(default="https://rafiki.example.com", env="RAFIKI_BASE_URL")
    rafiki_api_key: str = Field(..., env="RAFIKI_API_KEY")  # Required
    rafiki_timeout: int = Field(default=30, env="RAFIKI_TIMEOUT")

    # ILP settings
    default_currency: str = Field(default="USD", env="DEFAULT_CURRENCY")
    ilp_address_prefix: str = Field(default="ilp.", env="ILP_ADDRESS_PREFIX")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Security
    tls_enabled: bool = Field(default=True, env="TLS_ENABLED")
    tls_cert_path: Optional[str] = Field(default=None, env="TLS_CERT_PATH")
    tls_key_path: Optional[str] = Field(default=None, env="TLS_KEY_PATH")

    # Retry settings
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    retry_delay: float = Field(default=1.0, env="RETRY_DELAY")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global config instance
config = MiddlewareConfig()