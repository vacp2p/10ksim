import itertools
import logging
import os
import re
import shutil
import time
from argparse import ArgumentParser, Namespace
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Literal, Optional, Tuple

import humanfriendly
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from ruamel import yaml

from deployment.builders import build_deployment
from experiments.base_experiment import BaseExperiment

# from deployment.nimlibp2p.builders import Nimlibp2pBuilder
from kube_utils import (
    dict_set,
    get_cleanup,
    get_future_time,
    kubectl_apply,
    wait_for_rollout,
    wait_for_time,
)
from registry import experiment

logger = logging.getLogger(__name__)


def set_delay(
    values_yaml: yaml.YAMLObject, hours_key: str, minutes_key: str, delay: str
) -> yaml.YAMLObject:
    result = deepcopy(values_yaml)
    future_time = get_future_time(timedelta(seconds=int(delay)))
    dict_set(result, minutes_key, future_time.minute, sep=".", replace_leaf=True)
    dict_set(result, hours_key, future_time.hour, sep=".", replace_leaf=True)
    return result


@experiment(name="nimlibp2p-regression-nodes")
class NimRegressionNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="nim-regression-nodes")
    this_dir: str = Field(default=Path(os.path.dirname(__file__)))
    hours_key: str = Field(default="nimlibp2p.nodes.hours", no_init=True)
    minutes_key: str = Field(default="nimlibp2p.nodes.minutes", no_init=True)

    @staticmethod
    def add_args(subparser: ArgumentParser):
        subparser.add_argument(
            "--delay",
            type=str,
            dest="delay",
            required=False,
            help="For nimlibp2p tests only. The delay before nodes activate in string format (eg. 1hr20min)",
        )

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run a regression_nodes test using waku.")
        BaseExperiment.add_args(subparser)
        NimRegressionNodes.add_args(subparser)

    def _build(
        self, workdir: str, cli_values: yaml.YAMLObject, delay: Optional[str]
    ) -> Tuple[yaml.YAMLObject, PositiveInt]:
        build = lambda values: build_deployment(
            deployment_dir=os.path.join(self.this_dir, "..", "..", "nodes"),
            workdir=os.path.join(workdir, "nodes"),
            cli_values=values,
            name=self.release_name,
            extra_values_names=[],
            extra_values_paths=[os.path.join(self.this_dir, f"nodes.values.yaml")],
        )
        if delay is None:
            deployment = build(cli_values)
            num_nodes = deployment["spec"]["replicas"]
            # Assume it takes ~3 seconds to bring up each node.
            delay = (3 * 60) + (num_nodes * 3)
            logger.info(f"Using default delay (in seconds): {delay}")

        cli_values = set_delay(cli_values, self.hours_key, self.minutes_key, delay)
        return build(cli_values), delay

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

        deploy, delay = self._build(workdir, values_yaml, delay=args.delay)
        logger.info(f"Using delay: {delay}")

        this_time = datetime.now(dt_timezone.utc)
        logger.info(f"Current UTC time: {this_time.hour:02d}:{this_time.minute:02d}")

        future_time = get_future_time(timedelta(seconds=int(delay)))
        logger.info(f"Messages will begin at: {future_time.hour:02d}:{future_time.minute:02d}")

        namespace = deploy["metadata"]["namespace"]
        logger.info(f"Applying deployment to namespace: `{namespace}`")

        self._wait_until_clear(
            api_client=api_client,
            namespace=namespace,
            skip_check=args.skip_check,
        )

        cleanup = get_cleanup(
            api_client=api_client,
            namespace=namespace,
            deployments=[deploy],
        )
        stack.callback(cleanup)

        kubectl_apply(deploy, namespace=namespace)
        logger.info("Deployment applied. Waiting for rollout.")

        wait_for_rollout(deploy["kind"], deploy["metadata"]["name"], namespace, 3000)
        logger.info("Rollout successful.")

        logger.info(
            f"Waiting for message begin time: {future_time.hour:02d}:{future_time.minute:02d}"
        )
        wait_for_time(future_time)  # Wait until the nodes begin.

        num_nodes = deploy["spec"]["replicas"]
        time_to_resolve = (60 * 3) + (num_nodes * 3)
        logger.info(f"Waiting for messages to resolve. Sleep: {timedelta(seconds=time_to_resolve)}")
        time.sleep(
            time_to_resolve
        )  # TODO [regression nimlibp2p2 cleanup]: Test for nodes finished?

        this_time = datetime.now(dt_timezone.utc)
        logger.info(
            f"Test completed successfully at UTC time: {this_time.hour:02d}:{this_time.minute:02d}"
        )

    def generate_values(
        version: str,
        size: str,
        tag_type: Literal["yamux", "mplex"],
        delay: Optional[timedelta] = None,
    ) -> yaml.YAMLObject:
        if delay is None:
            delay = timedelta(hours=0, minutes=0)

        if version == "1.1.0":
            if tag_type == "yamux":
                tag_suffix = "yamux-1"
            elif tag_type == "mplex":
                tag_suffix = "mplex-2"
        else:
            tag_suffix = tag_type

        if version == "1.5.0":
            tag_str = f"v{version}-{tag_suffix}-hash-loop"
        else:
            tag_str = f"v{version}-{tag_suffix}"

        future_time = get_future_time(delay)

        values = {}
        for key, value in {
            "messageSize": str(humanfriendly.parse_size(size)),
            "messageRate": "10000" if size == "500KB" else "1000",
            "replicas": "1000",
            "image": {"repository": "soutullostatus/dst-test-node", "tag": tag_str},
            "minutes": str(future_time.minute),
            "hours": str(future_time.hour),
        }.items():
            dict_set(values, ["nimlibp2p", "nodes", key], value)

        return values


def generate_deployments(workdir, versions, sizes, suffixes):
    """Generate the all the manual deployments for the given lists of parameters."""
    table = list(itertools.product(versions, sizes, suffixes))

    for version, size, suffix in table:
        generate_deployment(workdir, version, size, suffix)


def generate_deployment(workdir, version, size, suffix):
    folder_name = re.sub(r"\.", "-", version)
    if version == "1.8.0":
        version_string = version
    else:
        folder_name = re.sub(r"-0$", "", folder_name)
        version_string = re.sub(r".0$", "", version)
    folder_name = f"v{folder_name}"
    filename = f"deploy_{size}-{suffix}-{version_string}.yaml"

    try:
        os.makedirs(os.path.join(workdir, folder_name))
    except FileExistsError:
        pass

    values = NimRegressionNodes.generate_values(version, size, suffix)
    deploy, _ = NimRegressionNodes()._build(workdir, values, None)

    with open(os.path.join(workdir, folder_name, filename), "w") as fout:
        yaml.safe_dump(deploy, fout)


def generate_all():
    """
    Generate the all the manual deployments.

    The result should (mostly) match the old file tree from `deployment/kubernetes-utilities/nimlibp2p/regression/manual/`.
    Note that some of the yaml files may appear different as they are in a different format.
    Additionally, the arguments for "minutes" and "hours" will be different.
    """
    versions = [
        "1.1.0",
        "1.2.0",
        "1.3.0",
        "1.4.0",
        "1.5.0",
        "1.6.0",
        "1.7.1",
        "1.7.0",
        "1.8.0",
    ]

    sizes = [
        "100b",
        "1000b",
        "1KB",
        "50KB",
        "500KB",
    ]

    suffixes = [
        "mplex",
        "yamux",
    ]

    workdir = "./workdir/nim/manual"
    try:
        shutil.rmtree(workdir)
    except FileNotFoundError:
        pass
    generate_deployments(workdir, versions, sizes, suffixes)
