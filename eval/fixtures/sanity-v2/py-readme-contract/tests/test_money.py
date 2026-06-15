from billing.money import format_usd


def test_format_usd_rounds_to_cents():
    assert format_usd(1.239) == "$1.24"


def test_format_usd_keeps_two_decimals():
    assert format_usd(7) == "$7.00"
