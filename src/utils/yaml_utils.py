# Python Imports
import re
from copy import deepcopy
from typing import List, Optional, Union

import ruamel.yaml
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap, CommentedSeq


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def read_template_yaml(template_path):
    pattern = re.compile(r"(:\s*)(\{\{.*?\}\})(?=\s*(#.*)?$)", re.MULTILINE)

    def replacer(match):
        prefix = match.group(1)
        expr = match.group(2)
        # If already quoted (just in case), skip
        if expr.startswith('"') and expr.endswith('"'):
            return match.group(0)
        return f'{prefix}"{expr}"'

    with open(template_path, "r") as in_file:
        content = pattern.sub(replacer, in_file.read())
        return yaml.safe_load(content)


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def get_defs_from_template(template_path):
    # TODO [multiple docs]: currently only supports reading in one yaml
    # document.
    def extract_keys(line):
        keys = []
        template_re = re.compile("{{\\s*(?P<template>[a-zA-Z0-9-_\\.]+)\\s*}}")
        value_re = re.compile("Values.(?P<key>[a-zA-Z0-9-_\\.]+)")
        # TODO [label optional values]: add logic for `default <default_value>
        # <key>`
        for line_match in template_re.finditer(line):
            for var_match in value_re.finditer(line_match.group("template")):
                variable = var_match.group("key")
                keys.append(variable)
        return keys

    all_keys = []
    stack = [read_template_yaml(template_path)]
    while stack:
        curr = stack.pop()
        for _, value in curr.items():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                stack.append(value)
            else:
                all_keys.extend(extract_keys(value))
    return all_keys


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def validate_values_yaml(values_yaml, template_yamls: List[yaml.yaml_object]):
    # TODO: ensure bijection between values.yaml and deployments.yaml.
    # Consider experiments with multiple deployments.yaml. For example:
    # bootstrap, nodes, publishers.
    raise NotImplementedError()


def get_YAML():
    """Return a ruamel.yaml.YAML() that dumps multipline strings as multiple lines instead of escaping newlines."""

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml = ruamel.yaml.YAML()
    yaml.Representer.add_representer(str, str_representer)
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # Prevent wrapping for long values such as bash scripts.
    return yaml


def merge_yaml_values(base, override) -> object:
    """Return the result of merging `override` into `base`.

    # Yaml merging rules

    maps: Merged recursively, favoring `override`.
    The combined map should have have all key value pairs
    between `base` and `override` with unique keys. For non-unique keys,
    if the value is map, then the map is merge recursively,
    otherwise, the `override` value is used.

    lists and other values: The value from `base` is overridden entirely
    by the value from `override`. No merging is done for lists or any
    other non-map type.

    :param base: Base value in a Yaml object
    :type base: object
    :param override: Yaml oject value to merge into `base`
    :type override: object
    :return: The yaml value resulting from merging `override` into `base`
    :rtype: object
    """
    if isinstance(base, CommentedMap) and isinstance(override, CommentedMap):
        merged = deepcopy(base)
        for key in override:
            if key in merged:
                merged[key] = merge_yaml_values(merged[key], override[key])
            else:
                merged[key] = deepcopy(override[key])
        return merged
    return override


def merge_helm_values(
    yamls: List[Union[str, CommentedMap, CommentedSeq]],
) -> Optional[yaml.YAMLObject]:
    if not yamls:
        return None

    def load_yaml(item: Union[str, CommentedMap, CommentedSeq]) -> yaml.YAMLObject:
        if isinstance(item, str):
            with open(item, "r") as fin:
                return yaml.safe_load(fin)
        return item

    merged_yaml = load_yaml(item[0])
    for item in yamls[1:]:
        merged_yaml = merge_yaml_values(merged_yaml, load_yaml(item))
    return merged_yaml
