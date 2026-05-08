from __future__ import annotations


def ok(data, message: str = "success") -> dict:
    return {
        "code": 0,
        "data": data,
        "message": message
    }


def fail(message: str, code: int = 1, data=None) -> dict:
    return {
        "code": code,
        "data": data,
        "message": message
    }
