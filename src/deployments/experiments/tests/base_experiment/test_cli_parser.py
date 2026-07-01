import argparse
import logging
from typing import ClassVar, List, Literal, Optional, Type

import pytest
from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.utils.parser import ARG_NOT_SET

logger = logging.getLogger(__name__)


class _HelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=100, width=220)


# Test ExpConfig help strings.


class ExpConfigWithoutHelpString(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    str_arg: str = "Alice"

    expected_param_strings: ClassVar[List[str]] = ["str-arg (str)"]


class ExpConfigWithHelpString(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    str_arg: str = "Alice"
    """Help string for Alice"""

    expected_param_strings: ClassVar[List[str]] = ["str-arg (str)", "Help string for Alice"]


class ExpConfigWithFieldDescription(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    str_arg: str = Field(description="Help string for Alice", default="Alice")

    expected_param_strings: ClassVar[List[str]] = ["str-arg (str)", "Help string for Alice"]


class ExpConfigWithoutDocStringsAttr(BaseModel):
    """
    Test that we can still generate if we're missing this line:
    model_config = ConfigDict(use_attribute_docstrings=True)
    """

    num_relay_nodes: NonNegativeInt = 30
    """Docstring here will not show up. That's ok."""
    num_messages: NonNegativeInt = 20
    message_size_bytes: NonNegativeInt = 1000

    expected_param_strings: ClassVar[List[str]] = [
        "num-relay-nodes (int)",
        "num-messages",
        "message-size-bytes",
    ]


Choice = Literal["choice_1", "choice_2", "choice_3"]


class ClassArg(BaseModel):
    pass


class ExpConfigTypes(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    int_arg: NonNegativeInt = 30
    float_arg: NonNegativeFloat = 1
    str_arg: str = "Alice"
    choice_arg: Choice = "choice_1"
    literal_arg: Literal["literal_1", "literal_2"] = "literal_1"
    class_arg: ClassArg = ClassArg()
    flag_arg: bool = False

    expected_param_strings: ClassVar[List[str]] = [
        "int-arg (int)",
        "float-arg (float)",
        "str-arg (str)",
        "--choice-arg (choices: ['choice_1', 'choice_2', 'choice_3'])",
        "--literal-arg (choices: ['literal_1', 'literal_2'])",
        "class-arg (ClassArg)",
        "flag-arg",
    ]


@pytest.fixture(scope="class")
def TestBaseExp(request):
    """Fixture for creating an arbitrary Experiment that derives from BaseExperiment[ExpConfig] using a custom ExpConfig."""
    config_cls = request.param

    DynamicClass = type(f"DynamicTestExp_{config_cls.__name__}", (BaseExperiment[config_cls],), {})
    DynamicClass.config_cls = config_cls
    DynamicClass.name = f"TestBaseExpWith{config_cls}"

    return DynamicClass


@pytest.mark.parametrize(
    "TestBaseExp",
    [
        ExpConfigWithoutHelpString,
        ExpConfigWithHelpString,
        ExpConfigWithFieldDescription,
        ExpConfigWithoutDocStringsAttr,
        ExpConfigTypes,
    ],
    indirect=True,
)
class TestExperimentLogic:
    # TODO: add other expconfigs (types, etc.)
    def test_class_methods_work(self, capsys, TestBaseExp: Type[BaseExperiment]):
        parser = argparse.ArgumentParser(
            description="Test description", formatter_class=_HelpFormatter
        )
        subparsers = parser.add_subparsers(dest="experiment", required=True)
        subparser = subparsers.add_parser(TestBaseExp.__name__, help=TestBaseExp.__doc__)
        TestBaseExp.add_config_args(subparser)

        with pytest.raises(SystemExit):
            _args = parser.parse_args([TestBaseExp.__name__, "--help"])
        captured = capsys.readouterr()

        for expected_string in TestBaseExp.config_cls.expected_param_strings:
            assert expected_string in captured.out


# Test Experiment class subparsers


class BasicExpConfig(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    basic_config_arg: str = "Alice"

    expected_param_strings: ClassVar[List[str]] = [
        "basic-config-arg (str)",
    ]


class BasicExp(BaseExperiment[BasicExpConfig]):
    async def _run(self):
        pass

    name: ClassVar[str] = "BasicExp"


BASE_EXPECTED = [
    "-h, --help",
    "show this help message and exit",
]

BASE_EXP_EXPECTED = [
    "--skip-check",
    "If present, does not wait",
    "--dry-run",
    "If True, does not actually deploy",
    "--namespace (str)",
    "The namespace for deployments.",
]


class EmptyExpConfig(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)


class ExpWithoutDescription(BaseExperiment[EmptyExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: ClassVar[str] = "ExpWithoutDescription"
    expected_description: ClassVar[List[str]] = ["ExpWithoutDescription"]

    async def _run(self):
        pass


class ExpWithDescription(BaseExperiment[EmptyExpConfig]):
    """
    A dummy experiment.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def _run(self):
        pass

    name: ClassVar[str] = "ExpWithDescription"
    expected_description: ClassVar[List[str]] = [
        "ExpWithDescription",
        "A dummy experiment.",
    ]


class ExpWithCustomParserExperiment(BaseExperiment[EmptyExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help=cls.__doc__, formatter_class=_HelpFormatter
        )
        subparser.add_argument(
            "--custom-arg",
            type=str,
            required=False,
            default="custom-arg",
            metavar="(str)",
            help="A custom arg added via a custom add_parser function",
        )

    async def _run(self):
        pass

    name: ClassVar[str] = "ExpWithCustomParserExperiment"
    expected_param_strings: ClassVar[List[str]] = [
        "ExpWithCustomParserExperiment",
        "--custom-arg (str)",
        "custom add_parser function",
    ]

    unexpected_param_strings: ClassVar[List[str]] = BASE_EXP_EXPECTED


class CustomArgsExperiment(BaseExperiment[EmptyExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_args(cls, subparser) -> None:
        subparser.add_argument(
            "--my-custom-arg",
            type=str,
            default=ARG_NOT_SET,
            help="My custom arg.",
            metavar="(str)",
        )

    expected_param_strings: ClassVar[List[str]] = [
        "--my-custom-arg (str)",
        "My custom arg.",
    ]

    async def _run(self):
        pass

    name: ClassVar[str] = "CustomArgsExperiment"


@pytest.mark.parametrize(
    "Exp", [ExpWithoutDescription, ExpWithDescription, BasicExp, CustomArgsExperiment]
)
def test_experiments(capsys, Exp: Type[BaseExperiment]):
    """add_parser should add help for base args and config args."""
    _test_help_string(capsys, Exp, "params", BASE_EXPECTED + BASE_EXP_EXPECTED)
    _test_help_string(capsys, Exp, "params", getattr(Exp, "expected_param_strings", []))
    _test_help_string(capsys, Exp, "description", getattr(Exp, "expected_description", []))


def test_experiment_custom(capsys):
    """add_parser should add help for base args and config args."""
    _test_help_string(
        capsys,
        ExpWithCustomParserExperiment,
        "description",
        getattr(ExpWithCustomParserExperiment, "expected_description", []),
    )
    _test_help_string(
        capsys,
        ExpWithCustomParserExperiment,
        "params",
        getattr(ExpWithCustomParserExperiment, "expected_param_strings", []),
        unexpected=getattr(ExpWithCustomParserExperiment, "unexpected_param_strings", []),
    )


def _test_help_string(
    capsys,
    Exp: Type[BaseExperiment],
    which_help_str: Literal["description", "params"],
    expected: List[str],
    unexpected: Optional[List[str]] = None,
):
    """add_parser should add help for base args and config args."""
    parser = argparse.ArgumentParser(description="Test parser", formatter_class=_HelpFormatter)
    subparsers = parser.add_subparsers(dest="experiment", required=True)
    Exp.add_parser(subparsers)

    with pytest.raises(SystemExit):
        if which_help_str == "params":
            command = [Exp.name, "--help"]
        elif which_help_str == "description":
            command = ["--help"]
        _args = parser.parse_args(command)
    captured = capsys.readouterr()

    for expected_string in expected:
        assert expected_string in captured.out

    if unexpected:
        for string in unexpected:
            assert string not in captured.out
