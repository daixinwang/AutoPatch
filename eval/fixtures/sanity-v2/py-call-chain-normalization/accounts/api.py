from accounts.service import get_profile


def profile_response(email: str):
    profile = get_profile(email)
    if profile is None:
        return None
    return {"display_name": profile["name"], "email": profile["email"]}
