import logging
from argparse import Namespace

from ruamel import yaml

from deployment.base_experiment import BaseExperiment
from deployment.nimlibp2p.experiments.regression.regression import NimRegressionNodes
from deployment.waku.experiments.regression.regression import WakuRegressionNodes
from registry import experiment

logger = logging.getLogger(__name__)


@experiment(name="regression-nodes", type="dispatch")
class RegressionNodes:
    """Proxy for running waku-regression-nodes or nim-regression-nodes."""

    @classmethod
    def add_parser(cls, subparsers) -> None:
        regression_nodes = subparsers.add_parser(cls.name, help="Run a regression_nodes test.")
        regression_nodes.add_argument(
            "--type", type=str, choices=["waku", "nim"], required=True, help=""
        )
        BaseExperiment.add_args(regression_nodes)
        NimRegressionNodes.add_args(regression_nodes)

    def run(self, api_client, args: Namespace, values_yaml: yaml.YAMLObject):
        logger.debug(f"args: {args}")
        run_args = {
            "api_client": api_client,
            "args": args,
            "values_yaml": values_yaml,
        }

        if args.type == "waku":
            WakuRegressionNodes().run(**run_args)
        elif args.type == "nim":
            NimRegressionNodes().run(**run_args)
        else:
            raise ValueError(f"Unknown regression experiment type: `{args['type']}`")
