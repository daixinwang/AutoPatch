from autopatch_guard.username import is_valid_username


def test_username_rejects_spaces():
    assert not is_valid_username("bad name")


def test_username_accepts_letters_numbers_and_underscore():
    assert is_valid_username("user_123")
