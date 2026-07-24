import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.analysis.post_run_analysis import load_post_run_analysis, run_post_analysis


def install_analysis_module(
    monkeypatch,
    module_name,
    function_name,
    calls,
    *,
    error=None,
):
    module = ModuleType(module_name)

    def analysis(experiment):
        calls.append(experiment)
        if error is not None:
            raise error
        return "done"

    setattr(module, function_name, analysis)
    monkeypatch.setitem(sys.modules, module_name, module)


def test_run_post_analysis_dispatches_configured_analysis(monkeypatch):
    calls = []
    module_name = "tests_post_run_analysis_module"
    function_name = "analysis"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    install_analysis_module(monkeypatch, module_name, function_name, calls)

    experiment = SimpleNamespace(
        _type="tests.ExperimentWithAnalysis",
        metadata={"stack": {}},
        post_run_analysis=f"{module_name}:{function_name}",
    )

    result = run_post_analysis(experiment)

    assert result == "done"
    assert calls == [experiment]


def test_run_post_analysis_logs_and_suppresses_analysis_exception(monkeypatch, caplog):
    calls = []
    module_name = "tests_post_run_failing_analysis_module"
    function_name = "analysis"
    analysis_ref = f"{module_name}:{function_name}"
    install_analysis_module(
        monkeypatch,
        module_name,
        function_name,
        calls,
        error=RuntimeError("boom"),
    )

    experiment = SimpleNamespace(
        _type="tests.ExperimentWithFailingAnalysis",
        metadata={"stack": {}},
        metadata_log_path="/tmp/metadata.json",
        output_folder="/tmp/run",
        post_run_analysis=analysis_ref,
    )

    with caplog.at_level(logging.ERROR, logger="src.analysis.post_run_analysis"):
        result = run_post_analysis(experiment)

    assert result is None
    assert calls == [experiment]
    assert "Post-run analysis failed" in caplog.text
    assert "tests.ExperimentWithFailingAnalysis" in caplog.text
    assert analysis_ref in caplog.text
    assert "boom" in caplog.text


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


@pytest.mark.parametrize(
    "analysis_ref",
    [
        "",
        "tests_post_run_analysis_module.analysis",
        ":analysis",
        "module:",
        "module:thing:extra",
    ],
)
def test_load_post_run_analysis_rejects_invalid_ref(analysis_ref):
    with pytest.raises(ValueError, match="module.path:function_name"):
        load_post_run_analysis(analysis_ref)
