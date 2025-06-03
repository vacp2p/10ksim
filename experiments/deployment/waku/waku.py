#!/usr/bin/env python3


import logging
import os
import shutil
import time
from typing import Optional

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from ruamel import yaml

from kube_utils import (
    assert_equals,
    cleanup_resources,
    get_cleanup_resources,
    helm_build_from_params,
    kubectl_apply,
    maybe_dir,
    poll_namespace_has_objects,
    wait_for_cleanup,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
)

logger = logging.getLogger(__name__)


class WakuRegressionNodes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    api_client: ApiClient = Field(default=client.ApiClient())
    release_name: str = Field(default="waku-regression-nodes")

    def _build_nodes(self, values_yaml: yaml.yaml_object, workdir: str) -> yaml.YAMLObject:
        template_path = "./deployment/waku/regression/nodes.yaml"
        return helm_build_from_params(
            template_path,
            values_yaml,
            os.path.join(
                workdir,
                "nodes",
                self.release_name,
            ),
        )

    def _build_bootstrap(self, values_yaml: yaml.yaml_object, workdir: str) -> yaml.YAMLObject:
        path = "./deployment/waku/regression/bootstrap.yaml"
        return helm_build_from_params(
            path,
            values_yaml,
            os.path.join(
                workdir,
                "bootstrap",
                self.release_name,
            ),
        )

    def _build_publisher(self, values_yaml: yaml.yaml_object, workdir: str):
        publisher_yaml = "./deployment/waku/regression/publisher_msg.yaml"
        return helm_build_from_params(
            publisher_yaml,
            values_yaml,
            os.path.join(workdir, "publisher"),
            self.release_name,
        )

    def run(
        self, values_yaml: yaml.YAMLObject, workdir: Optional[str] = None, skip_check: bool = False
    ):
        with maybe_dir(workdir) as workdir:
            try:
                shutil.rmtree(workdir)
            except FileNotFoundError:
                pass
            self._run(values_yaml, workdir, skip_check)

    def _run(self, values_yaml: yaml.YAMLObject, workdir: str, skip_check: bool):
        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")
        nodes = self._build_nodes(values_yaml, workdir)
        bootstrap = self._build_bootstrap(values_yaml, workdir)
        publisher = self._build_publisher(values_yaml, workdir)

        logger.info(
            f"Running a waku regression test with params: {{ nodes: {values_yaml['numNodes']},\tmessages: {values_yaml['messages']},\tMessage Delay: {values_yaml['delaySeconds']} }}"
        )

        # Sanity check
        namespace = bootstrap["metadata"]["namespace"]
        logger.info(f"namespace={namespace}")
        assert_equals(nodes["metadata"]["namespace"], namespace)
        assert_equals(publisher["metadata"]["namespace"], namespace)

        logger.info("Applying kubernetes configs.")
        try:
            # Wait for namespace to be clear unless --skip-check flag was used.
            if not skip_check:
                wait_for_no_objs_in_namespace(namespace=namespace, api_client=self.api_client)
            else:
                namepace_is_empty = poll_namespace_has_objects(
                    namespace=namespace, api_client=self.api_client
                )
                if not namepace_is_empty:
                    logger.warning(f"Namespace is not empty! Namespace: `{namespace}`")

            # Apply bootstrap
            logger.info("Applying bootstrap")
            kubectl_apply(bootstrap, namespace=namespace)
            logger.info("bootstrap applied. Waiting for rollout.")
            wait_for_rollout(bootstrap["kind"], bootstrap["metadata"]["name"], namespace, 2000)

            # Apply nodes configuration
            logger.info("Applying nodes")
            kubectl_apply(nodes, namespace=namespace)
            logger.info("nodes applied. Waiting for rollout.")
            timeout = values_yaml["numNodes"] * 3000
            wait_for_rollout(nodes["kind"], nodes["metadata"]["name"], namespace, timeout)

            # Apply publisher configuration
            logger.info("applying publisher")
            kubectl_apply(publisher, namespace=namespace)
            logger.info("publisher applied. Waiting for rollout.")
            wait_for_rollout(
                publisher["kind"],
                publisher["metadata"]["name"],
                namespace,
                20,
                self.api_client,
                ("Ready", "True"),
                # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
            )
            logger.info("publisher rollout done.")

            logger.info("Waiting for Ready=False")
            timeout = (
                values_yaml["numNodes"]
                * values_yaml["messages"]
                * values_yaml["delaySeconds"]
                * 120
            )
            wait_for_rollout(
                publisher["kind"],
                publisher["metadata"]["name"],
                namespace,
                timeout,
                self.api_client,
                ("Ready", "False"),
            )
            # TODO: consider state.reason == .completed
            time.sleep(20)
        finally:
            logger.info("Cleaning up resources.")
            resources_to_cleanup = get_cleanup_resources([bootstrap, nodes, publisher])
            logger.info(f"Resources to clean up: `{resources_to_cleanup}`")

            logger.info("Start cleanup.")
            cleanup_resources(resources_to_cleanup, namespace, self.api_client)
            logger.info("Waiting for cleanup.")
            wait_for_cleanup(resources_to_cleanup, namespace, self.api_client)
            logger.info("Finished cleanup.")


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
