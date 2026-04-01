from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Calculate the sum of two numbers.

    Args:
        a (Union[int, float]): The first number.
        b (Union[int, float]): The second number.

    Returns:
        Union[int, float]: The sum of the two numbers.
    """
    return a + b

def subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Calculate the difference between two numbers.

    Args:
        a (Union[int, float]): The first number.
        b (Union[int, float]): The second number.

    Returns:
        Union[int, float]: The difference between the two numbers.
    """
    return a - b

def multiply(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Calculate the product of two numbers.

    Args:
        a (Union[int, float]): The first number.
        b (Union[int, float]): The second number.

    Returns:
        Union[int, float]: The product of the two numbers.
    """
    return a * b

def divide(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Calculate the division of two numbers.

    Args:
        a (Union[int, float]): The numerator.
        b (Union[int, float]): The denominator.

    Returns:
        Union[int, float]: The result of the division.

    Raises:
        ValueError: If the denominator (b) is zero.
    """
    if b == 0:
        raise ValueError("Division by zero is not allowed.")
    return a / b