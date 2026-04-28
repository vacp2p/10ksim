"""Common functions for mesh analysis."""

import json
import logging
import os
import sys
import traceback
from collections import defaultdict
from typing import Awaitable, Callable, Iterable

from log_multi_analysis import unravel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deployments")))

import logging
import os
import traceback

logger = logging.getLogger(__name__)


async def analyze_exps(actions: Iterable[Callable[[], Awaitable[dict]]]):
    all_statuses = defaultdict(int)
    summary = defaultdict(int)
    all_results = []
    for action in actions:
        try:
            results = await action()
            all_results.append(results)
            passed = True
            for item in results["results"]:
                all_statuses[item.status] += 1
                if item.status != "passed":
                    passed = False

            if passed:
                summary["passed"] += 1
        except Exception as e:
            # Catch all exceptions so we can still print results table
            # even if an experiment had a problem.
            logger.error(f"exception: {e}")
            full_trace = traceback.format_exc()
            logger.error(f"exception: {full_trace}")

    logger.info(f"=== All Results ===\n{json.dumps(unravel(all_results), indent=2, default=str)}")
    not_passed = len(all_results) - summary["passed"]
    logger.info(f"Passed: {summary['passed']}\nNot Passed: {not_passed}\nTotal: {len(all_results)}")
    status_str = "\n".join([f"{key}: {value}" for key, value in all_statuses.items()])
    logger.info(f"=== Statuses === \n{status_str}")

    if not_passed:
        logger.error("At least one check failed!")
