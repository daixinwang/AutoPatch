from orders.validators import validate_quantity


def create_order(unit_price: float, quantity: int) -> dict:
    valid_quantity = validate_quantity(quantity)
    return {"total": unit_price * valid_quantity}
