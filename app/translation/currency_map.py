from dataclasses import dataclass


@dataclass(frozen=True)
class CurrencyInfo:
    asset_code: str
    asset_scale: int


CURRENCY_MAP: dict[str, CurrencyInfo] = {
    "524": CurrencyInfo(asset_code="NPR", asset_scale=2),
    "840": CurrencyInfo(asset_code="USD", asset_scale=2),
    "356": CurrencyInfo(asset_code="INR", asset_scale=2),
}


def get_currency_info(iso_code: str) -> CurrencyInfo:
    info = CURRENCY_MAP.get(iso_code)
    if info is None:
        supported = ", ".join(CURRENCY_MAP.keys())
        raise ValueError(
            f"Unsupported currency code '{iso_code}'. "
            f"Supported codes: {supported}"
        )
    return info
