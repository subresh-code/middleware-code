"""
Rafiki Configuration Module

Configuration specific to Rafiki integration.
"""

from app.utils.config import config


class RafikiConfig:
    """
    Rafiki-specific configuration settings.
    """

    # API endpoints
    ILP_ENDPOINT = "/ilp"
    ACCOUNTS_ENDPOINT = "/accounts"
    TRANSACTIONS_ENDPOINT = "/transactions"
    HEALTH_ENDPOINT = "/health"

    # ILP-specific settings
    DEFAULT_EXECUTION_CONDITION = "execution_condition_placeholder"
    DEFAULT_FULFILLMENT = "fulfillment_placeholder"

    # Timeout settings
    DEFAULT_TIMEOUT = config.rafiki_timeout
    HEALTH_CHECK_TIMEOUT = 5

    # Retry settings
    MAX_RETRIES = config.max_retries
    RETRY_DELAY = config.retry_delay

    @classmethod
    def get_base_url(cls) -> str:
        """Get Rafiki base URL."""
        return config.rafiki_base_url

    @classmethod
    def get_api_key(cls) -> str:
        """Get Rafiki API key."""
        return config.rafiki_api_key