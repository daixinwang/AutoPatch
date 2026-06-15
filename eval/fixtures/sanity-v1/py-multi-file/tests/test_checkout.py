from shop.checkout import checkout_total


def test_checkout_total_applies_tax_rate_to_subtotal():
    items = [{"price": 100, "quantity": 2}]
    assert checkout_total(items, 0.08) == 216


def test_empty_cart_total_is_zero():
    assert checkout_total([], 0) == 0
