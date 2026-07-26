from __future__ import annotations

from collections import defaultdict
from functools import wraps
from typing import Any, Callable


def depends_on(*fields: str):
    def decorator(fn: Callable[..., Any]):
        setattr(fn, "_depends_on_fields", set(fields))

        @wraps(fn)
        def wrapped(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapped

    return decorator


class DependencyRegistry:
    def __init__(self) -> None:
        self._field_to_methods: dict[str, list[str]] = defaultdict(list)

    def register(self, method_name: str, fields: set[str]) -> None:
        for field in fields:
            if method_name not in self._field_to_methods[field]:
                self._field_to_methods[field].append(method_name)

    def methods_for(self, field: str) -> list[str]:
        return list(self._field_to_methods.get(field, []))
