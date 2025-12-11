# tests/test_calculator.py

from calculator import add

def test_add_two_numbers():
    assert add(1, 2) == 3

def test_add_negative():
    assert add(-1, -2) == -3
