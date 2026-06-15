def line_total(price: float, quantity: int) -> float:
    return price * quantity


def total_with_tax(subtotal: float, tax_rate: float) -> float:
    return subtotal + tax_rate
