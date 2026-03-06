import argparse
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.kube_utils import init_logger, set_config_file
from kubernetes import config
from kubernetes.client import ApiClient
from registry import registry as experiment_registry
from ruamel import yaml

logger = logging.getLogger(__name__)


async def run_experiment(
    name: str,
    args: argparse.Namespace,
    values_path: Optional[str],
    kube_config=None,
):
    logger.debug(f"params: {args}")
    if not kube_config:
        kube_config = "~/.kube/config"
    config.load_kube_config(config_file=kube_config)
    set_config_file(kube_config)
    api_client = ApiClient()

    try:
        with open(values_path, "r") as values:
            values_yaml = yaml.safe_load(values.read())  # todo: change to get_YAML().load()...
    except TypeError:
        # values_path is None.
        values_yaml = None

    info = experiment_registry[name]
    experiment = info.cls()
    logger.info(f"Running experiment. name `{info.name}` file: `{info.metadata['module_path']}`")
    await experiment.run(api_client, args, values_yaml)


def setup_output_folder(args: argparse.Namespace) -> Path:
    base_out_dir = Path(__file__).parent / "out"
    if args.out_folder is not None:
        out_dir = (
            args.out_folder if args.out_folder.is_absolute() else base_out_dir / args.out_folder
        )
    else:
        out_dir = base_out_dir / datetime.now().strftime("%Y.%m.%d_%H.%M.%f")[:-3]

    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


async def main():
    parser = argparse.ArgumentParser(
        description="A tool to run experiments. Generates deployment yaml with helm and deploys using the given kubeconfig. Dependencies: helm must be installed and in $PATH."
    )

    subparsers = parser.add_subparsers(dest="experiment", required=True)

    parser.add_argument("--values", default=None, help="Path to values.yaml", dest="values_path")
    parser.add_argument(
        "--config",
        required=False,
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
        "--out-folder",
        type=Path,
        dest="out_folder",
        default=None,
        required=False,
        help="Output folder to contain all experiment output. "
        "Path is relative to `__file__/out/` unless given as absolute path. "
        "Default path uses `__file__/out/{{datetime}}`.",
    )

    # Scan for experiments.
    experiment_registry.scan(os.path.dirname(__file__), mode="skip")

    # Add subparsers for all experiments.
    for info in experiment_registry.items():
        try:
            info.cls.add_parser(subparsers)
        except AttributeError as e:
            raise AttributeError(f"{info}") from e

    args = parser.parse_args()
    out_folder = setup_output_folder(args)
    args.output_folder = out_folder
    verbosity = args.verbosity or 2
    init_logger(logging.getLogger(), verbosity, out_folder / "out.log")
    try:
        await run_experiment(
            name=args.experiment,
            args=args,
            values_path=args.values_path,
            kube_config=args.kube_config,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(main())
