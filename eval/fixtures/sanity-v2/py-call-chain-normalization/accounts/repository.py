_PROFILES = {
    "ada@example.com": {"name": "Ada Lovelace", "email": "ada@example.com"},
}


def find_profile(email: str):
    return _PROFILES.get(email)
