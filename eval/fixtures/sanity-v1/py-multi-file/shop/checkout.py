from shop.pricing import line_total, total_with_tax


def checkout_total(items: list[dict], tax_rate: float) -> float:
    subtotal = sum(line_total(item["price"], item["quantity"]) for item in items)
    return total_with_tax(subtotal, tax_rate)
