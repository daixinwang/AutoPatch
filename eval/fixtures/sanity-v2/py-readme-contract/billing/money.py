def format_usd(amount: float) -> str:
    cents = int(amount * 100)
    return f"${cents / 100:.2f}"
