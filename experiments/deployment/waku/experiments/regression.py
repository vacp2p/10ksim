import logging
import os
import time
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from deployment.base_experiment import BaseExperiment
from deployment.builders import build_deployment_type
from kube_utils import assert_equals, get_cleanup, get_flag_value, kubectl_apply, wait_for_rollout
from registry import experiment

logger = logging.getLogger(__name__)


@experiment(name="waku-regression-nodes")
class WakuRegressionNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="waku-regression-nodes")

    deployment_dir: str = Field(default=Path(os.path.dirname(__file__)).parent)

    @staticmethod
    def add_parser(subparsers) -> None:
        subparser = subparsers.add_parser(
            "waku-regression-nodes", help="Run a regression_nodes test using waku."
        )
        BaseExperiment.add_args(subparser)

    def _build(
        self,
        workdir: str,
        values_yaml: Optional[yaml.YAMLObject],
        service: str,
    ) -> yaml.YAMLObject:
        return build_deployment_type(
            deployment_dir=self.deployment_dir,
            workdir=workdir,
            cli_values=values_yaml,
            service=service,
            extra_values_names=["regression.values.yaml"],
        )

    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")
        nodes = self._build(workdir, values_yaml, "nodes")
        bootstrap = self._build(workdir, values_yaml, "bootstrap")
        publisher = self._build(workdir, values_yaml, "publisher")

        # Sanity check
        namespace = bootstrap["metadata"]["namespace"]
        logger.info(f"namespace={namespace}")
        assert_equals(nodes["metadata"]["namespace"], namespace)
        assert_equals(publisher["metadata"]["namespace"], namespace)

        # TODO [metadata output]: log start time to output file here.
        logger.info("Applying kubernetes configs.")

        cleanup = get_cleanup(
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
        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
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
