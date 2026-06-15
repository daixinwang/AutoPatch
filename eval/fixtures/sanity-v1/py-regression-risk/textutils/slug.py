import re


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", "", value).strip().lower()
    return cleaned.replace(" ", "-")
