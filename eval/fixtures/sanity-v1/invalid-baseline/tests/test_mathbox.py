from mathbox.core import add


def test_adds_positive_integers():
    assert add(2, 3) == 5


def test_adds_zero():
    assert add(5, 0) == 5
