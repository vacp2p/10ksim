import inspect
from unittest.mock import Mock

from src.deployments.logos_core.builders.request_builder import LogoscorePodApiRequester


def _dummy_value_for_property(name: str):
    if name == "debug":
        return True
    return object()


def test_setters_call_reconcile():
    obj = LogoscorePodApiRequester()
    obj._reconcile = Mock(wraps=obj._reconcile)

    for name, member in inspect.getmembers(type(obj), lambda x: isinstance(x, property)):
        if member.fset is None:
            # Read-only properties cannot be assigned to, so skip them.
            continue

        setattr(obj, name, _dummy_value_for_property(name))
        obj._reconcile.assert_called_with(name)
