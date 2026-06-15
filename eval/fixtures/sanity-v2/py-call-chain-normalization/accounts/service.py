from accounts.repository import find_profile


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_profile(email: str):
    return find_profile(email)
