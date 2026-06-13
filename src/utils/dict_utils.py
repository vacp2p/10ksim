# Python Imports
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional


def dict_get(
    obj: Dict | list,
    path: str | List[str | int] | Path,
    *,
    default: Any = None,
    sep: Optional[str] = "/",
) -> Any:
    if isinstance(path, str):
        path = [node for node in path.split(sep) if node]
    if isinstance(path, Path):
        path = [node for node in path.parts]
    if len(path) < 1:
        raise KeyError(f"Invalid path. Path: `{path}`")

    if len(path) == 1:
        if isinstance(obj, list):
            return obj[int(path[0])]
        return obj.get(path[0], default)

    try:
        key = int(path[0]) if isinstance(obj, list) else path[0]
        return dict_get(obj[key], path[1:], default=default, sep=sep)
    except (TypeError, KeyError):
        return default


def dict_set(
    obj: Dict,
    path: str | List[str] | Path,
    value: Any,
    *,
    replace_leaf: bool = False,
    replace_nondict_stems: bool = False,
    sep: Optional[str] = "/",
) -> Optional[Any]:
    """Set value in `dict` at `path`, creating sub-dicts at path nodes if they do not already exist.

    :param dict: `dict` or `dict`-like object.
    :type dict: Dict
    :param path: If given as a str, uses `sep` as separator to make a list of separators.
    :type path: str | List[str]
    :param value: Value to be set or add to the dict.
    :type value: Any
    :param replace_leaf: If False, raises KeyError if there is already a value at `path` in `dict`.
    :type replace_leaf: bool
    :param replace_nondict_stems: If True, replaces existing values in `dict` with empty `dict`s while traversing the `path`.
    :type replace_nondict_stems: bool
    :param sep: Separator to use for getting the list of path components from `path.
    :type sep: str | None

    :return: The value that already existed at `path` in `dict` and `replace_leaf == True`, or `None` if no value existed.
    :rvalue: Optional[Any]

    Raises KeyError if any node on the path is not a dict unless `replace_nondict_stems== True`.
    Raises KeyError if a value already exists at the given path unless `replace_leaf == True`.
    """
    if isinstance(path, str):
        path = [node for node in path.split(sep) if node]
    if isinstance(path, Path):
        path = path.parts
    if len(path) < 1:
        raise KeyError(f"Invalid path. Path: `{path}`")
    for i, node in enumerate(path[:-1]):
        node = path[i]
        try:
            if isinstance(obj, list):
                node = int(node)
                if node == len(obj):
                    obj[node].append({})
                obj = obj[node]
            else:
                if node not in obj.keys() or replace_nondict_stems:
                    obj[node] = {}
                obj = obj[node]
        except (AttributeError, TypeError):
            raise KeyError(
                f"Non-dict value already exists at path. Path: `{path[0:i]}`\tKey: `{node}`\tValue: `{obj}`"
            )

    previous = None
    key = int(path[-1]) if isinstance(obj, list) else path[-1]
    if key in obj:
        if not replace_leaf:
            raise KeyError(f"Value already exists at path. Path: `{path}`\tValue: `{obj[key]}`")
        previous = obj[key]
    obj[key] = value
    return previous


def dict_partial_compare(complete_dict: Dict[Any, Any], partial_dict: Dict[Any, Any]) -> bool:
    """
    Compare two dictionaries, but only check keys present in partial_dict.

    :param complete_dict: The complete dictionary to compare against.
    :param partial_dict: The partial dictionary containing keys to test.

    :return: True if for every key in partial_dict, complete_dict has the same key and value. False otherwise.
    :rtype: bool
    """
    for key, partial_value in partial_dict.items():
        if key not in complete_dict:
            return False
        if complete_dict[key] != partial_value:
            return False
    return True


def dict_apply(
    obj: Any,
    func: Callable[[Any], Any],
    path: Path | None = None,
    *,
    order: Literal["pre", "post"] = "pre",
) -> dict:
    """Applies `func(obj)` to every obj in `node` and adds the result to the same path in a new dict.
    Wrapper around `dict_visit` that returns a new dict using the provided `func`.

    Note: `None` values are ignored and not added to the new dict.
    """
    new_dict = {}

    def apply(path, node):
        nonlocal new_dict
        new_value = func(node)
        if new_value is not None:
            if path == Path():
                new_dict = new_value
            else:
                dict_set(new_dict, path, new_value)

    dict_visit(obj, apply, path, order=order)
    return new_dict


def dict_visit(
    node: Any,
    func: Callable[[Path, Any], Any],
    path: Path | None = None,
    *,
    order: Literal["pre", "post"] = "pre",
):
    """Calls `func(path, obj)` for every obj in `node`. `path` is Path used to retreive that value from the dict.
    In other words, `dict_get(node, path)` would return `obj`.

    Calls `func(path, value)` for value in dict.items()

    Calls `func(path, item)` for each list item in list.

    Calls `func(path, node)` for each other node.
    """
    if order not in ["pre", "post"]:
        raise ValueError(f'Invalid order. Expected "pre" or "post". order: `{order}`')

    if path is None:
        path = Path()

    if order == "pre":
        func(path, node)

    if isinstance(node, dict):
        for key, value in node.items():
            dict_visit(value, func, path / str(key), order=order)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            dict_visit(item, func, path / str(index), order=order)

    if order == "post":
        func(path, node)
