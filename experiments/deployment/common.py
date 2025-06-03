#!/usr/bin/env python3


from abc import ABC, abstractmethod
import argparse
import logging
import os
import shutil
import time
from typing import Optional
from ruamel.yaml.comments import CommentedMap


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

from contextlib import ExitStack

logger = logging.getLogger(__name__)


class BaseExperiment(ABC, BaseModel):
    '''Base experiment that add an ExitStack with `workdir` to `run` and uses an internal `_run`.

    How to use:
        - Inherit from this class.
        - Call `BaseExperiment.add_args` in the child class's `add_parser`
        - Implement `_run` in the child class.
    '''

    def add_args(subparser):
        subparser.add_argument(
            "--workdir",
            type=str,
            required=False,
            default=None,
            help="Folder to use for generating the deployment files.",
        )
        subparser.add_argument(
            "--skip-check",
            action="store_true",
            required=False,
            help="If present, does not wait until the namespace is empty before running the test.",
        )

    def run(self, api_client : ApiClient, args : argparse.Namespace, values_yaml : Optional[yaml.YAMLObject]):
        with ExitStack() as stack:
            workdir = args.workdir
            stack.enter_context(maybe_dir(workdir))
            try:
                shutil.rmtree(workdir)
            except FileNotFoundError:
                pass
            self._run(api_client=api_client, workdir=workdir, args=args, values_yaml=values_yaml, stack=stack)

    @abstractmethod
    def _run(self, api_client : ApiClient, workdir : str, args : argparse.Namespace, values_yaml : Optional[yaml.YAMLObject], stack : ExitStack):
        pass

    def _wait_until_clear(self, api_client : ApiClient, namespace : str, skip_check : bool):
        # Wait for namespace to be clear unless --skip-check flag was used.
        if not skip_check:
            wait_for_no_objs_in_namespace(namespace=namespace, api_client=api_client)
        else:
            namepace_is_empty = poll_namespace_has_objects(
                namespace=namespace, api_client=api_client
            )
            if not namepace_is_empty:
                logger.warning(f"Namespace is not empty! Namespace: `{namespace}`")




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
