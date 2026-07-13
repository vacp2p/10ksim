from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import PrivateAttr

from src.deployments.experiments.multi_experiment import Config, Multiple, dict_to_namespace
from src.deployments.registry import Registry

# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


class ConcreteMultiple(Multiple):
    """Multiple.get_params_list is abstract; fill it with an injectable param list."""

    _param_sets: list = PrivateAttr(default_factory=list)

    def get_params_list(self):
        return self._param_sets


def _make_multiple(mocker, param_sets: list, output_folder: Path, **config_kwargs):
    """Create a ConcreteMultiple instance, bypassing full pydantic validation."""
    exp = ConcreteMultiple.model_construct(
        api_client=mocker.Mock(),
        config=Config(**config_kwargs),
        namespace="ns",
        output_folder=output_folder,
        skip_check=False,
        dry_run=False,
    )
    exp._param_sets = param_sets
    return exp


@pytest.fixture
def registered_target(mocker):
    """Create an isolated local Registry
    to avoid using the shared global registry."""
    run_mock = mocker.AsyncMock()
    fake_experiment = SimpleNamespace(run=run_mock)
    factory = mocker.Mock(return_value=fake_experiment)

    local_registry = Registry()
    local_registry.add("dummy-multi-target", factory, module_path="dummy-module")
    mocker.patch("src.deployments.experiments.multi_experiment.experiment_registry", local_registry)

    return factory, run_mock


# --------------------------------------------------------------------------- #
# dict_to_namespace Tests
# --------------------------------------------------------------------------- #
class TestDictToNamespace:
    """Tests for the dict_to_namespace function."""

    def test_dict_to_namespace_converts_nested_dicts(self):
        """Should recursively convert nested dicts into SimpleNamespace objects."""
        result = dict_to_namespace({"a": 1, "b": {"c": 2, "d": {"e": 3}}})
        assert result.a == 1
        assert result.b.c == 2
        assert result.b.d.e == 3

    @pytest.mark.parametrize("value", [5, "str", None, [1, 2]])
    def test_dict_to_namespace_passes_through_non_dict(self, value):
        """Should return non-dict values unchanged."""
        assert dict_to_namespace(value) == value


# --------------------------------------------------------------------------- #
# Config Tests
# --------------------------------------------------------------------------- #
class TestConfig:
    """Tests for the Config class."""

    def test_get_raw_input_returns_original_data(self):
        """Should return the exact kwargs passed to the constructor."""
        cfg = Config(name="exp", delay=5, extra_field="value")
        assert cfg.get_raw_input() == {"name": "exp", "delay": 5, "extra_field": "value"}

    def test_get_extra_fields_returns_only_extras(self):
        """Should return only the fields not declared on the model."""
        cfg = Config(name="exp", foo="bar", nested={"a": 1})
        assert cfg.get_extra_fields() == {"foo": "bar", "nested": {"a": 1}}

    def test_get_extra_fields_empty_when_no_extra(self):
        """Should return an empty dict when no extra fields were provided."""
        cfg = Config(name="exp")
        assert cfg.get_extra_fields() == {}


# --------------------------------------------------------------------------- #
# Multiple.get_name_from_params Tests
# --------------------------------------------------------------------------- #
class TestMultipleGetNameFromParams:
    """Tests for the Multiple.get_name_from_params method."""

    def test_get_name_from_params_joins_key_value_pairs(self, mocker, tmp_path):
        """Should join each key/value pair with `_` and separate pairs with `__`."""
        exp = _make_multiple(mocker, [], tmp_path, name="dummy-multi-target", delay=1)
        result = exp.get_name_from_params({"lr": 0.1, "batch": 32})
        assert result == "lr_0.1__batch_32"


# --------------------------------------------------------------------------- #
# Multiple._run Tests
# --------------------------------------------------------------------------- #
class TestMultipleRun:
    """Tests for the Multiple._run method."""

    @pytest.mark.asyncio
    async def test_run_raises_if_delay_not_set(self, mocker, tmp_path):
        """Should raise AssertionError when delay is falsy."""
        exp = _make_multiple(mocker, [{}], tmp_path, name="dummy-multi-target", delay=0)
        with pytest.raises(AssertionError):
            await exp._run()

    @pytest.mark.asyncio
    async def test_run_raises_if_no_experiment_name(self, mocker, tmp_path):
        """Should raise ValueError when config.name is not set."""
        mocker.patch("src.deployments.experiments.multi_experiment.asyncio.sleep")
        exp = _make_multiple(mocker, [{}], tmp_path, name=None, delay=0.01)
        with pytest.raises(ValueError):
            await exp._run()

    @pytest.mark.asyncio
    async def test_run_merges_params_into_a_fresh_copy_of_raw_input_each_iteration(
        self, mocker, tmp_path, registered_target
    ):
        """Should merge each param set onto a fresh deep copy of the raw config, not a
        previously mutated copy."""
        factory, run_mock = registered_target
        mocker.patch("src.deployments.experiments.multi_experiment.asyncio.sleep")
        exp = _make_multiple(
            mocker,
            [{"model.lr": 0.2}, {"model.batch": 8}],
            tmp_path,
            name="dummy-multi-target",
            delay=0.01,
            model={"lr": 0.1, "batch": 4},
        )

        await exp._run()

        assert factory.call_count == 2
        first_config = factory.call_args_list[0].kwargs["config"]
        assert first_config["model"] == {"lr": 0.2, "batch": 4}
        second_config = factory.call_args_list[1].kwargs["config"]
        assert second_config["model"] == {"lr": 0.1, "batch": 8}
        assert run_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_run_passes_experiment_context_to_child_experiment(
        self, mocker, tmp_path, registered_target
    ):
        """Should forward namespace, skip_check, dry_run, and a nested output_folder."""
        factory, _ = registered_target
        mocker.patch("src.deployments.experiments.multi_experiment.asyncio.sleep")
        exp = _make_multiple(
            mocker,
            [{"model.lr": 0.2}],
            tmp_path,
            name="dummy-multi-target",
            delay=0.01,
            model={"lr": 0.1},
        )

        await exp._run()

        kwargs = factory.call_args_list[0].kwargs
        assert kwargs["namespace"] == "ns"
        assert kwargs["skip_check"] is False
        assert kwargs["dry_run"] is False
        assert Path(kwargs["output_folder"]).parent == tmp_path

    @pytest.mark.asyncio
    async def test_run_sleeps_delay_between_each_experiment(
        self, mocker, tmp_path, registered_target
    ):
        """Should sleep for config.delay seconds after every experiment run."""
        sleep_mock = mocker.patch("src.deployments.experiments.multi_experiment.asyncio.sleep")
        exp = _make_multiple(mocker, [{}, {}, {}], tmp_path, name="dummy-multi-target", delay=42)

        await exp._run()

        assert sleep_mock.await_count == 3
        sleep_mock.assert_awaited_with(42)

    @pytest.mark.asyncio
    async def test_run_continues_after_child_experiment_raises(
        self, mocker, tmp_path, registered_target
    ):
        """Should log the exception and continue the loop if a child experiment raises."""
        factory, run_mock = registered_target
        run_mock.side_effect = [RuntimeError("boom"), None]
        mocker.patch("src.deployments.experiments.multi_experiment.asyncio.sleep")
        exp = _make_multiple(mocker, [{}, {}], tmp_path, name="dummy-multi-target", delay=0.01)

        await exp._run()

        assert factory.call_count == 2
        assert run_mock.await_count == 2
