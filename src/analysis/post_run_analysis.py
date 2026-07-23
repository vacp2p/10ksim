from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.deployments.experiments.base_experiment import BaseExperiment

logger = logging.getLogger(__name__)

PostRunAnalysis = Callable[["BaseExperiment"], Any]


def _invalid_analysis_ref(analysis_ref: Any) -> ValueError:
    return ValueError(
        "post_run_analysis must use the format `module.path:function_name` "
        f"with non-empty module and function names; got `{analysis_ref}`"
    )


def run_post_analysis(experiment: "BaseExperiment") -> Any:
    analysis_ref = getattr(experiment, "post_run_analysis", None)
    if analysis_ref is None:
        logger.info(f"No post-run analysis configured for `{experiment._type}`")
        return None

    if experiment.metadata is None:
        raise ValueError(
            f"Cannot run post-run analysis before metadata is set: `{experiment._type}`"
        )

    try:
        analysis = load_post_run_analysis(analysis_ref)
        return analysis(experiment)
    except Exception:
        logger.exception(
            "Post-run analysis failed for experiment_type=`%s`, analysis_ref=`%s`, "
            "metadata_log_path=`%s`, output_folder=`%s`",
            getattr(experiment, "_type", type(experiment).__qualname__),
            analysis_ref,
            getattr(experiment, "metadata_log_path", None),
            getattr(experiment, "output_folder", None),
        )
        return None


def load_post_run_analysis(analysis_ref: str) -> PostRunAnalysis:
    if not isinstance(analysis_ref, str) or analysis_ref.count(":") != 1:
        raise _invalid_analysis_ref(analysis_ref)

    module_name, function_name = (part.strip() for part in analysis_ref.split(":"))
    if not module_name or not function_name:
        raise _invalid_analysis_ref(analysis_ref)

    module = import_module(module_name)
    analysis = getattr(module, function_name)
    if not callable(analysis):
        raise TypeError(f"Configured post-run analysis is not callable: `{analysis_ref}`")

    return analysis
