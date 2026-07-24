import argparse
import logging
from typing import ClassVar, Type

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.utils.parser import ARG_NOT_SET, _field_to_arg, get_from_str

logger = logging.getLogger(__name__)

# Tests for parsing complex objects in ExpConfigs.


class ImageJSON(BaseModel):
    supported_input_kinds: ClassVar[set[str]] = {"json"}

    repo: str
    tag: str


class ImageFromStr:
    supported_input_kinds: ClassVar[set[str]] = {"from_str"}

    repo: str
    tag: str

    @staticmethod
    def from_str(image: str):
        repo, tag = image.split(":")
        obj = ImageFromStr()
        obj.repo = repo
        obj.tag = tag
        return obj


class ImageDirect:
    supported_input_kinds: ClassVar[set[str]] = {"direct"}

    def __init__(self, image: str):
        repo, tag = image.split("-")
        self.repo = repo
        self.tag = tag


class ImageJSONAndFromStr(BaseModel):
    supported_input_kinds: ClassVar[set[str]] = {"json", "from_str"}

    repo: str
    tag: str

    @staticmethod
    def from_str(image: str):
        repo, tag = image.split(":")
        return ImageJSONAndFromStr(repo=repo, tag=tag)


class ImageNone:
    supported_input_kinds: ClassVar[set[str]] = set()


def get_exp_conf(image_type):
    namespace = {
        "__annotations__": {
            "image": image_type,
            "supported_input_kinds": ClassVar[set[str]],
        },
        "image": Field(description="Container image"),
        "supported_input_kinds": getattr(image_type, "supported_input_kinds", set()),
        "model_config": ConfigDict(use_attribute_docstrings=True, arbitrary_types_allowed=True),
    }
    return type(f"ExpConfig_{image_type.__name__}", (BaseModel,), namespace)


@pytest.fixture(scope="class")
def TestBaseExp(request):
    config_cls = request.param
    DynamicClass = type(f"DynamicTestExp_{config_cls.__name__}", (BaseExperiment[config_cls],), {})
    DynamicClass.config_cls = config_cls
    DynamicClass.name = f"TestBaseExpWith{config_cls.__name__}"
    return DynamicClass


class TestGetFromStr:
    def test_json_basemodel(self):
        converter = get_from_str(ImageJSON, "image")
        result = converter('{"repo": "nWaku", "tag": "v0.36"}')
        assert result.repo == "nWaku"
        assert result.tag == "v0.36"

    def test_from_str_basemodel(self):
        converter = get_from_str(ImageFromStr, "image")
        result = converter("nWaku:v0.36")
        assert result.repo == "nWaku"
        assert result.tag == "v0.36"

    def test_direct_constructor(self):
        converter = get_from_str(ImageDirect, "image")
        result = converter("nWaku-v0.36")
        assert result.repo == "nWaku"
        assert result.tag == "v0.36"

    def test_all_three_uses_json_first(self):
        converter = get_from_str(ImageJSONAndFromStr, "image")
        result = converter('{"repo": "nWaku", "tag": "v0.36"}')
        assert result.repo == "nWaku"
        assert result.tag == "v0.36"

    def test_none_fails(self):
        converter = get_from_str(ImageNone, "image")
        with pytest.raises(argparse.ArgumentTypeError):
            converter("nWaku:v0.36")


class _HelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=100, width=220)


@pytest.mark.parametrize(
    "TestBaseExp",
    [
        get_exp_conf(ImageJSONAndFromStr),
        get_exp_conf(ImageJSON),
        get_exp_conf(ImageFromStr),
        get_exp_conf(ImageDirect),
        get_exp_conf(ImageNone),
    ],
    indirect=True,
)
class TestImageInArgparse:
    def test_help_output_contains_config_params(self, capsys, TestBaseExp: Type[BaseExperiment]):
        parser = argparse.ArgumentParser(
            description="Test description", formatter_class=_HelpFormatter
        )
        subparsers = parser.add_subparsers(dest="experiment", required=True)
        subparser = subparsers.add_parser(TestBaseExp.__name__, help=TestBaseExp.__doc__)
        TestBaseExp.add_config_args(subparser)

        with pytest.raises(SystemExit):
            parser.parse_args([TestBaseExp.__name__, "--help"])
        captured = capsys.readouterr()

        assert "--image" in captured.out
        assert "Container image" in captured.out

    @pytest.mark.parametrize(
        "input_kind, input_value",
        [
            ("json", '{"repo": "nWaku", "tag": "v0.36"}'),
            ("from_str", "nWaku:v0.36"),
            ("direct", "nWaku-v0.36"),
        ],
    )
    def test_cli_parsing(self, input_kind, input_value, TestBaseExp: Type[BaseExperiment]):
        parser = argparse.ArgumentParser(description="Test parser", formatter_class=_HelpFormatter)
        subparsers = parser.add_subparsers(dest="experiment", required=True)
        subparser = subparsers.add_parser(TestBaseExp.name, help=TestBaseExp.__doc__)
        TestBaseExp.add_config_args(subparser)

        command = [TestBaseExp.name, "--image", input_value]
        should_pass = input_kind in TestBaseExp.config_cls.supported_input_kinds
        if should_pass:
            args = parser.parse_args(command)
            assert args.image.repo == "nWaku"
            assert args.image.tag == "v0.36"
        else:
            with pytest.raises(SystemExit):
                parser.parse_args(command)


class TestParserTypeWiring:
    def test_complex_type_gets_get_from_str_callable(self):
        field_info = type(
            "MockFieldInfo",
            (),
            {
                "annotation": ImageDirect,
                "description": "Container image",
                "default": ARG_NOT_SET,
            },
        )()

        flag, kwargs = _field_to_arg("image", field_info)
        assert flag == "--image"
        assert callable(kwargs["type"])
        assert kwargs["metavar"] == "(ImageDirect)"

    def test_bool_does_not_get_get_from_str(self):
        field_info = type(
            "MockFieldInfo",
            (),
            {
                "annotation": bool,
                "description": "Flag",
                "default": False,
            },
        )()

        flag, kwargs = _field_to_arg("flag", field_info)
        assert flag == "--flag"
        assert kwargs["action"] == "store_true"
        assert "type" not in kwargs

    def test_primitive_types_use_native_types(self):
        for py_type in (int, float, str):
            field_info = type(
                "MockFieldInfo",
                (),
                {
                    "annotation": py_type,
                    "description": f"{py_type.__name__} field",
                    "default": ARG_NOT_SET,
                },
            )()

            _, kwargs = _field_to_arg("field", field_info)
            assert kwargs["type"] == py_type
