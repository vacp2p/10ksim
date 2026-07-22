from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.deployments.experiments.base_experiment import BaseExperiment

logger = logging.getLogger(__name__)

PostRunAnalysis = Callable[["BaseExperiment"], Any]


def run_post_analysis(experiment: "BaseExperiment") -> Any:
    analysis_ref = getattr(experiment, "post_run_analysis", None)
    if analysis_ref is None:
        logger.info(f"No post-run analysis configured for `{experiment._type}`")
        return None

    if experiment.metadata is None:
        raise ValueError(
            f"Cannot run post-run analysis before metadata is set: `{experiment._type}`"
        )

    analysis = load_post_run_analysis(analysis_ref)
    return analysis(experiment)


def load_post_run_analysis(analysis_ref: str) -> PostRunAnalysis:
    try:
        module_name, function_name = analysis_ref.split(":", maxsplit=1)
    except ValueError as e:
        raise ValueError(
            "post_run_analysis must use the format `module.path:function_name`; "
            f"got `{analysis_ref}`"
        ) from e

    module = import_module(module_name)
    analysis = getattr(module, function_name)
    if not callable(analysis):
        raise TypeError(f"Configured post-run analysis is not callable: `{analysis_ref}`")

    return analysis
