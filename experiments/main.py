#!/usr/bin/env python3

import argparse
import logging

from kubernetes import config
from kubernetes.client import ApiClient

from kube_utils import (
    init_logger,
)
from regression_tests.dispatch import add_subparser as add_regression_tests_subparser
from regression_tests.dispatch import run_regression_tests

logger = logging.getLogger(__name__)


def run_experiment(experiment, params, values_path, kube_config=None):
    logger.debug(f"params: {params}")
    if not kube_config:
        kube_config = "~/.kube/config"
    config.load_kube_config(config_file=kube_config)
    api_client = ApiClient()

    # TODO [automatic experiment collection]: Programmatically gather tests by searching in test folders.
    if experiment == "regression_nodes":
        run_regression_tests(api_client, params, values_path)
    else:
        raise NotImplementedError()


def main():
    parser = argparse.ArgumentParser(
        description="A tool to run experiments. Generates deployment yaml with helm and deploys using the given kubeconfig. Dependencies: helm must be installed and in $PATH."
    )

    subparsers = parser.add_subparsers(dest="experiment", required=True)

    parser.add_argument("--values", required=True, help="", dest="values_path")
    parser.add_argument(
        "--config",
        required=True,
        help="Config passed to --kubeconfig in kubernetes commands.",
        dest="kube_config",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbosity",
        default=0,
        help="Set the log level: -v (warnings), -vv (info), -vvv (debug) -vvvv (most verbose)",
    )
    parser.add_argument(
        "-l",
        "--log-file",
        type=str,
        dest="log_file_path",
        required=False,
        help="Pipes the log to given file in addition to stdout/stderr.",
    )

    # Add more subparsers as needed for new experiments here.
    add_regression_tests_subparser(subparsers)

    args = parser.parse_args()
    verbosity = args.verbosity or 2
    init_logger(logging.getLogger(), verbosity, args.log_file_path)
    params = vars(args)
    try:
        run_experiment(
            experiment=args.experiment,
            params=params,
            values_path=args.values_path,
            kube_config=args.kube_config,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
