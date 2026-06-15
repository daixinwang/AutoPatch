def is_valid_username(value: str) -> bool:
    """Return whether value is a supported username."""
    return bool(value) and all(ch.isalnum() or ch in {"_", " "} for ch in value)
