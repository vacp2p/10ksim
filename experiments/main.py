import argparse
import logging
import os
from typing import Optional

from kubernetes import config
from kubernetes.client import ApiClient
from ruamel import yaml

from kube_utils import init_logger
from registry import registry as experiment_registry

logger = logging.getLogger(__name__)


def run_experiment(
    name: str,
    args: argparse.Namespace,
    values_path: Optional[str],
    kube_config=None,
):
    logger.debug(f"params: {args}")
    if not kube_config:
        kube_config = "~/.kube/config"
    config.load_kube_config(config_file=kube_config)
    api_client = ApiClient()

    try:
        with open(values_path, "r") as values:
            values_yaml = yaml.safe_load(values.read()) # todo: change to get_YAML().load()...
    except TypeError:
        # values_path is None.
        values_yaml = None

    info = experiment_registry[name]
    experiment = info.cls()
    experiment.run(api_client, args, values_yaml)


def main():
    parser = argparse.ArgumentParser(
        description="A tool to run experiments. Generates deployment yaml with helm and deploys using the given kubeconfig. Dependencies: helm must be installed and in $PATH."
    )

    subparsers = parser.add_subparsers(dest="experiment", required=True)

    parser.add_argument("--values", default=None, help="Path to values.yaml", dest="values_path")
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

    # Scan for experiments.
    experiment_registry.scan(os.path.join(os.path.dirname(__file__), "deployment"), mode="skip")

    # Add subparsers for all experiments.
    for info in experiment_registry.items():
        try:
            info.cls.add_parser(subparsers)
        except AttributeError as e:
            raise AttributeError(f"{info}") from e

    args = parser.parse_args()
    verbosity = args.verbosity or 2
    init_logger(logging.getLogger(), verbosity, args.log_file_path)
    try:
        run_experiment(
            name=args.experiment,
            args=args,
            values_path=args.values_path,
            kube_config=args.kube_config,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
