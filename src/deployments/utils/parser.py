# Python Imports
from argparse import ArgumentParser
from typing import Any, get_args, get_origin, Union
from pydantic.fields import FieldInfo
from argparse import ArgumentParser
from typing import get_args, get_origin, Union, Literal
import json
import logging
import os
import random
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar, Union
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator
from ruamel import yaml

ARG_NOT_SET = object()

def _unwrap_optional(annotation):
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
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
        "type" : str,
    }

    if annotation is bool:
        kwargs["action"] = "store_true"

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

    return flag, kwargs

def _config_model_fields_to_args(config_model: type[BaseModel]) -> list[tuple[str, dict[str, Any]]]:
    args = []
    for field_name, field in config_model.model_fields.items():
        args.append(_field_to_arg(field_name, field))
    return args
