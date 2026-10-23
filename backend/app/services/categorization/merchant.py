import re

def normalize_merchant(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip().lower()

    if not value:
        return None

    value = re.sub(r"\s+", " ", value)

    return value