#!/usr/bin/env python3


import logging

from kubernetes.client import ApiClient
from ruamel import yaml

from experiments.regression_tests.nimlibp2p import NimRegressionNodes
from regression_tests.waku import WakuRegressionNodes

logger = logging.getLogger(__name__)


def add_subparser(subparsers):
    regression_nodes = subparsers.add_parser(
        "regression_nodes", help="Run a regression_nodes test."
    )
    regression_nodes.add_argument(
        "--type", type=str, choices=["waku", "nim"], required=True, help=""
    )
    regression_nodes.add_argument(
        "--workdir",
        type=str,
        required=False,
        default=None,
        help="Folder to use for generating the deployment files.",
    )
    regression_nodes.add_argument(
        "--skip-check",
        action="store_true",
        required=False,
        help="If present, does not wait until the namespace is empty before running the test.",
    )
    regression_nodes.add_argument(
        "--delay",
        type=str,
        dest="delay",
        required=False,
        help="For nimlibp2p tests only. The delay before nodes activate in string format (eg. 1hr20min)",
    )


def run_regression_tests(api_client: ApiClient, params, values_path):
    logger.debug(f"params: {params}")

    with open(values_path, "r") as values:
        values_yaml = yaml.safe_load(values.read())
    workdir = params.get("workdir", None)

    if params["type"] == "waku":
        test = WakuRegressionNodes(api_client=api_client)
        test.run(values_yaml, workdir, params["skip_check"])
    elif params["type"] == "nim":
        test = NimRegressionNodes(api_client=api_client)
        test.run(values_yaml, workdir, params["skip_check"], params["delay"])
    else:
        raise ValueError(f"Unknown regression test type: `{params['type']}`")
