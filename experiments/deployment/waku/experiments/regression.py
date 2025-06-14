#!/usr/bin/env python3


import argparse
import logging
import re
import time
from contextlib import ExitStack
from typing import Callable, List, Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from ruamel import yaml

from deployment.common import BaseExperiment
from deployment.waku.builders import WakuBuilder
from kube_utils import (
    assert_equals,
    cleanup_resources,
    get_cleanup_resources,
    kubectl_apply,
    wait_for_cleanup,
    wait_for_rollout,
)
from registry import experiment

logger = logging.getLogger(__name__)


@experiment(name="waku-regression-nodes")
class WakuRegressionNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="waku-regression-nodes")

    def add_parser(subparsers):
        subparser = subparsers.add_parser(
            "waku-regression-nodes", help="Run a regression_nodes test using waku."
        )
        BaseExperiment.add_args(subparser)

    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: argparse.Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")
        builder = WakuBuilder(api_client=api_client)
        nodes = builder.build(workdir, values_yaml, "nodes", ["regression.yaml"])
        bootstrap = builder.build(workdir, values_yaml, "bootstrap", ["regression.yaml"])
        publisher = builder.build(workdir, values_yaml, "publisher", ["regression.yaml"])

        # Sanity check
        namespace = bootstrap["metadata"]["namespace"]
        logger.info(f"namespace={namespace}")
        assert_equals(nodes["metadata"]["namespace"], namespace)
        assert_equals(publisher["metadata"]["namespace"], namespace)

        # TODO [metadata output]: log start time to output file here.
        logger.info("Applying kubernetes configs.")

        cleanup = self.get_cleanup(
            api_client=api_client,
            namespace=namespace,
            deployments=[bootstrap, nodes, publisher],
        )
        stack.callback(cleanup)

        self._wait_until_clear(
            api_client=api_client,
            namespace=namespace,
            skip_check=args.skip_check,
        )

        # Apply bootstrap
        logger.info("Applying bootstrap")
        kubectl_apply(bootstrap, namespace=namespace)
        logger.info("bootstrap applied. Waiting for rollout.")
        wait_for_rollout(bootstrap["kind"], bootstrap["metadata"]["name"], namespace, 2000)

        num_nodes = nodes["spec"]["replicas"]
        messages = self.get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = self.get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )

        # Apply nodes configuration
        logger.info("Applying nodes")
        kubectl_apply(nodes, namespace=namespace)
        logger.info("nodes applied. Waiting for rollout.")
        timeout = num_nodes * 3000
        wait_for_rollout(nodes["kind"], nodes["metadata"]["name"], namespace, timeout)

        # TODO [metadata output]: log publish message start time
        # Apply publisher configuration
        logger.info("applying publisher")
        kubectl_apply(publisher, namespace=namespace)
        logger.info("publisher applied. Waiting for rollout.")
        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            20,
            api_client,
            ("Ready", "True"),
            # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
        )
        logger.info("publisher rollout done.")

        timeout = num_nodes * messages * delay_seconds * 120
        logger.info(f"Waiting for Ready=False. Timeout: {timeout}")

        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            timeout,
            api_client,
            ("Ready", "False"),
        )
        # TODO: consider state.reason == .completed
        time.sleep(20)
        # TODO [metadata output]: log publish message end time

    def get_cleanup(
        self, api_client: ApiClient, namespace: str, deployments: List[yaml.YAMLObject]
    ) -> Callable[[], None]:
        def cleanup():
            logger.info("Cleaning up resources.")
            resources_to_cleanup = get_cleanup_resources(deployments)
            logger.info(f"Resources to clean up: `{resources_to_cleanup}`")

            logger.info("Start cleanup.")
            cleanup_resources(resources_to_cleanup, namespace, api_client)
            logger.info("Waiting for cleanup.")
            wait_for_cleanup(resources_to_cleanup, namespace, api_client)
            logger.info("Finished cleanup.")

        return cleanup

    def get_flag_value(self, flag: str, command: List[str]) -> int:
        for node in command:
            matches = re.search(f"--{flag}=(?P<numMessages>\d+)", node)
            try:
                return int(matches["numMessages"])
            except (TypeError, IndexError):
                pass
        return None


def run_waku_regression_nodes(
    workdir: Optional[str],
    client,
    values_path,
    nodes_counts: list[PositiveInt],
    message_delays: list[PositiveInt],
):

    test = WakuRegressionNodes(api_client=client)
    with open(values_path, "r") as values_file:
        values_yaml = yaml.safe_load(values_file.read())
    for values in [{**values_yaml, **{"numNodes": count}} for count in nodes_counts]:
        for values in [{**values, **{"delaySeconds": delay}} for delay in message_delays]:
            test.run(values, workdir)
            time.sleep(600)


# Example usage:
# config.load_kube_config(config_file="./kube_config.yaml")
# client = ApiClient()
# run_waku_regression_nodes(
#     "./workdir", client, "./values.yaml", [100, 200, 300], [1, 5, 10]
# )
