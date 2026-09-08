"""Tiny fixture module: exactly four symbols for tapps_file_api tests."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


class Calculator:
    def multiply(self, a, b):
        return a * b

    def divide(
        self,
        a,
        b,
    ):
        return a / b
