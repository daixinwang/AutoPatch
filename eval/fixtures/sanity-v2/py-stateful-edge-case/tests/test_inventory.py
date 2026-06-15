from warehouse.inventory import Inventory


def test_cancel_pending_reservation_releases_stock():
    inventory = Inventory(stock=5)
    inventory.reserve(3)

    assert inventory.cancel(3) == "cancelled"
    assert inventory.available == 5


def test_confirmed_reservation_keeps_stock_deducted():
    inventory = Inventory(stock=5)
    inventory.reserve(3)

    assert inventory.confirm(3) == "confirmed"
    assert inventory.available == 2
