from autopatch_demo.calculator import calculate_discounted_total


def test_percentage_discount_uses_percent_units():
    assert calculate_discounted_total(200, 10) == 180


def test_zero_discount_keeps_subtotal():
    assert calculate_discounted_total(200, 0) == 200
