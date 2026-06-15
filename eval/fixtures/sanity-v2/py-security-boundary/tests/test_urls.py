from security.urls import is_internal_url


def test_rejects_suffix_spoofing_host():
    assert is_internal_url("https://internal.example.com.evil.test/path") is False


def test_allows_root_and_subdomain():
    assert is_internal_url("https://internal.example.com/dashboard") is True
    assert is_internal_url("https://api.internal.example.com/status") is True
