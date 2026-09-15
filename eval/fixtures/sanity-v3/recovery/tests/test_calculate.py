from service import add

from api import calculate


def test_positive():
    assert calculate(2, 3) == 5
    assert add(2, 3) == 5

def test_negative():
    assert calculate(2, -3) == -1

def test_zero():
    assert calculate(2, 0) == 2
