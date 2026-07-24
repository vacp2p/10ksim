from collections.abc import Mapping
from typing import Any


def stack_for_window(metadata: Mapping[str, Any], window_name: str) -> dict[str, Any]:
    """Return a copy of metadata["stack"] using one named results window.

    Bridges store all named event windows under metadata["results"]. DataPuller
    reads the active query interval from stack["start_time"] and stack["end_time"].
    This helper copies the stack and replaces those two fields with the selected
    window, so callers can run multiple analyses over different windows.
    """
    try:
        stack = metadata["stack"]
    except KeyError as e:
        raise ValueError("metadata is missing `stack`") from e
    if not isinstance(stack, Mapping):
        raise TypeError(f"metadata[`stack`] must be a mapping; got {type(stack).__name__}")

    try:
        window = metadata["results"][window_name]
    except KeyError as e:
        available = sorted(metadata.get("results", {}).keys())
        raise ValueError(
            f"metadata is missing results window `{window_name}`; available windows: {available}"
        ) from e
    if not isinstance(window, Mapping):
        raise TypeError(
            f"metadata[`results`][`{window_name}`] must be a mapping; "
            f"got {type(window).__name__}"
        )

    missing = [key for key in ("start", "end") if key not in window]
    if missing:
        raise ValueError(f"results window `{window_name}` is missing keys: {missing}")

    return {
        **dict(stack),
        "start_time": window["start"],
        "end_time": window["end"],
    }
