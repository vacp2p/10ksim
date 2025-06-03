import logging

import pytest

from kube_utils import dict_add, init_logger


@pytest.fixture
def logger():
    logger = logging.getLogger(__name__)
    init_logger(logging.getLogger(), "DEBUG")


@pytest.mark.parametrize(
    "start_dict,path,value,sep",
    [
        ({"a": 1, "b": 4}, ["b", "c", "d"], 5, None),
        ({"a": 1, "b": 4}, "b/c/d", 5, "/"),
        ({"a": 1, "b": 4}, ["b"], 5, None),
        ({"a": 1, "b": 4}, "b", 5, None),
        ({"a": 1, "b": {"c": 4}}, "b/c", 5, "/"),
        ({"a": 1, "b": {"c": 4}}, "b/c/d", 5, "/"),
    ],
)
def test_set_dict_key_exist(logger, start_dict, path, value, sep):
    with pytest.raises(KeyError) as excinfo:
        dict_add(start_dict, path, value, sep)
    logger.error(excinfo)


@pytest.mark.parametrize("path,sep", [([], None), ("", None), ("/", "/")])
def test_set_dict_empty_path(logger, path, sep):
    with pytest.raises(KeyError) as excinfo:
        dict_add({"a": 1, "b": 4}, path, 5, sep)
    logger.error(excinfo)


@pytest.mark.parametrize(
    "start_dict,path,value,sep,expected",
    [
        (
            {"snack": "popcorn"},
            "fruit",
            "orange",
            "/",
            {"snack": "popcorn", "fruit": "orange"},
        ),
        (
            {"snack": "popcorn"},
            "meal/sides/fruit",
            "orange",
            "/",
            {"snack": "popcorn", "meal": {"sides": {"fruit": "orange"}}},
        ),
        (
            {
                "snack": "popcorn",
                "meal": {"main": "steak", "sides": {"veggies": "corn"}},
            },
            "meal/sides/fruit",
            "orange",
            "/",
            {
                "snack": "popcorn",
                "meal": {
                    "main": "steak",
                    "sides": {"veggies": "corn", "fruit": "orange"},
                },
            },
        ),
    ],
)
def test_set_dict(logger, start_dict, path, value, sep, expected):
    modified = start_dict
    dict_add(modified, path, value, sep)
    assert modified == expected
