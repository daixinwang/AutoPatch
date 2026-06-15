def calculate_discounted_total(subtotal: float, discount_percent: float) -> float:
    """Return subtotal after applying a percentage discount."""
    return subtotal - (subtotal * discount_percent)
