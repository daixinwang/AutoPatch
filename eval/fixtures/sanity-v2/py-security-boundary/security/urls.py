from urllib.parse import urlparse


def is_internal_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "internal.example.com" in host
