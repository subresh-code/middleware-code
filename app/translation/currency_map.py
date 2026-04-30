from typing import Dict, Tuple

# Currency code (numeric 3-digit) → (assetCode, assetScale)
CURRENCY_MAP: Dict[str, Tuple[str, int]] = {
    "524": ("NPR", 2),  # Nepalese Rupee
    "840": ("USD", 2),  # US Dollar
    "356": ("INR", 2),  # Indian Rupee
}


def get_currency_info(currency_code: str) -> Tuple[str, int]:
    """
    Returns (assetCode, assetScale) for a given ISO 4217 numeric code.
    Raises ValueError if unsupported.
    """
    if currency_code not in CURRENCY_MAP:
        raise ValueError(f"Unsupported currency code: {currency_code}")
    return CURRENCY_MAP[currency_code]
