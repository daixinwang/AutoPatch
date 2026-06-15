from accounts.api import profile_response


def test_get_profile_accepts_mixed_case_email():
    assert profile_response(" Ada@Example.COM ") == {
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
    }


def test_get_profile_returns_none_for_unknown_email():
    assert profile_response("unknown@example.com") is None
