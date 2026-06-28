# Python Imports
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

ARG_NOT_SET = object()


from typing import Any, Literal, Union, get_args, get_origin


def _annotation_display(annotation) -> str:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if annotation in (int, float, str, bool):
        return f"({annotation.__name__})"

    if origin is Literal:
        values = ", ".join(repr(v) for v in get_args(annotation))
        return f"(choices: [{values}])"

    if hasattr(annotation, "__name__"):
        return f"({annotation.__name__})"

    return str(annotation)


def _unwrap_optional(annotation):
    origin = get_origin(annotation)
    if origin is Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _field_to_arg(field_name: str, field: FieldInfo) -> tuple[str, dict[str, Any]]:
    annotation = _unwrap_optional(field.annotation)
    flag = f"--{field_name.replace('_', '-')}"

    kwargs: dict[str, Any] = {
        "dest": field_name,
        "default": ARG_NOT_SET,
        "required": False,
        "type": str,
    }

    if annotation is bool:
        kwargs["action"] = "store_true"
        del kwargs["type"]

    if annotation in (int, float, str):
        kwargs["type"] = annotation

    origin = get_origin(annotation)
    if origin is Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1 and args[0] in (int, float, str):
            kwargs["type"] = args[0]

    if origin is Literal:
        choices = get_args(annotation)
        if choices:
            kwargs["type"] = type(choices[0])

    if field.description:
        kwargs["help"] = field.description

    type_label = _annotation_display(annotation)
    if "type" in kwargs.keys():
        kwargs["metavar"] = f"{type_label}"

    return flag, kwargs


def _config_model_fields_to_args(config_model: type[BaseModel]) -> list[tuple[str, dict[str, Any]]]:
    args = []
    for field_name, field in config_model.model_fields.items():
        args.append(_field_to_arg(field_name, field))
    return args
