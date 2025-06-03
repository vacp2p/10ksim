#!/usr/bin/env python3


import argparse
import logging

from kubernetes.client import ApiClient
from ruamel import yaml

from deployment.common import BaseExperiment
from deployment.waku.experiments.regression import WakuRegressionNodes
from registry import experiment

from deployment.nimlibp2p.experiments.regression import NimRegressionNodes

logger = logging.getLogger(__name__)


@experiment(name="regression-nodes", type="dispatch")
class RegressionNodes():
    '''Proxy for running waku-regression-nodes or nim-regression-nodes.'''
    def add_parser(subparsers):
        regression_nodes = subparsers.add_parser(
            "regression-nodes", help="Run a regression_nodes test."
        )
        regression_nodes.add_argument(
            "--type", type=str, choices=["waku", "nim"], required=True, help=""
        )
        BaseExperiment.add_args(regression_nodes)
        NimRegressionNodes.add_args(regression_nodes)

    def run(self, api_client, args: argparse.Namespace, values_yaml: yaml.YAMLObject):
        logger.debug(f"args: {args}")

        if args.type == "waku":
            experiment = WakuRegressionNodes()
            experiment.run(api_client=api_client, args=args, values_yaml=values_yaml)
        elif args.type == "nim":
            experiment = NimRegressionNodes()
            experiment.run(api_client=api_client, args=args, values_yaml=values_yaml)
        else:
            raise ValueError(f"Unknown regression experiment type: `{args['type']}`")
