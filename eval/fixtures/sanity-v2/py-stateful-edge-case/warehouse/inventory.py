class Inventory:
    def __init__(self, stock: int):
        self.stock = stock
        self.reserved = 0

    def reserve(self, units: int) -> str:
        if units > self.available:
            raise ValueError("not enough stock")
        self.reserved += units
        return "pending"

    @property
    def available(self) -> int:
        return self.stock - self.reserved

    def confirm(self, units: int) -> str:
        self.reserved -= units
        self.stock -= units
        return "confirmed"

    def cancel(self, units: int) -> str:
        return "cancelled"
