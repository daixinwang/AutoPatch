def validate_quantity(quantity: int) -> int:
    if quantity <= 0:
        raise ValueError("invalid quantity")
    return quantity
