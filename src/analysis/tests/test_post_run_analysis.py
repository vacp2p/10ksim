import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.analysis.post_run_analysis import load_post_run_analysis, run_post_analysis


def install_analysis_module(module_name, function_name, calls):
    module = ModuleType(module_name)

    def analysis(experiment):
        calls.append(experiment)
        return "done"

    setattr(module, function_name, analysis)
    sys.modules[module_name] = module


def test_run_post_analysis_dispatches_configured_analysis(monkeypatch):
    calls = []
    module_name = "tests_post_run_analysis_module"
    function_name = "analysis"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    install_analysis_module(module_name, function_name, calls)

    experiment = SimpleNamespace(
        _type="tests.ExperimentWithAnalysis",
        metadata={"stack": {}},
        post_run_analysis=f"{module_name}:{function_name}",
    )

    result = run_post_analysis(experiment)

    assert result == "done"
    assert calls == [experiment]


def test_run_post_analysis_is_noop_when_no_analysis_is_configured():
    experiment = SimpleNamespace(
        _type="tests.ExperimentWithoutAnalysis",
        metadata={"stack": {}},
        post_run_analysis=None,
    )

    assert run_post_analysis(experiment) is None


def test_run_post_analysis_requires_metadata_for_configured_analysis():
    experiment = SimpleNamespace(
        _type="tests.ExperimentWithoutMetadata",
        metadata=None,
        post_run_analysis="tests_post_run_analysis_module:analysis",
    )

    with pytest.raises(ValueError, match="Cannot run post-run analysis before metadata is set"):
        run_post_analysis(experiment)


def test_load_post_run_analysis_rejects_invalid_ref():
    with pytest.raises(ValueError, match="module.path:function_name"):
        load_post_run_analysis("tests_post_run_analysis_module.analysis")
