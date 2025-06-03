import itertools
import logging
import os
import re
import shutil
import time
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import humanfriendly
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from deployment.common import BaseExperiment
from kube_utils import (
    cleanup_resources,
    get_cleanup_resources,
    get_future_time,
    helm_build_from_params,
    kubectl_apply,
    maybe_dir,
    poll_namespace_has_objects,
    str_to_timedelta,
    timedelta_until,
    wait_for_cleanup,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
    wait_for_time,
)

logger = logging.getLogger(__name__)


class NimRegressionNodes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="nim-regression-nodes")

    @staticmethod
    def add_args(subparser: ArgumentParser):
        subparser.add_argument(
            "--delay",
            type=str,
            dest="delay",
            required=False,
            help="For nimlibp2p tests only. The delay before nodes activate in string format (eg. 1hr20min)",
        )

    @staticmethod
    def add_parser(subparsers) -> None:
        subparser = subparsers.add_parser(
            "nimlibp2p-regression-nodes", help="Run a regression_nodes test using waku."
        )
        BaseExperiment.common_flags(subparser)
        NimRegressionNodes.add_args(subparser)

    def run(
        self,
        values_yaml: yaml.YAMLObject,
        workdir: Optional[str] = None,
        skip_check: bool = False,
        delay: Optional[timedelta] = None,
    ):
        with maybe_dir(workdir) as workdir:
            try:
                shutil.rmtree(workdir)
            except FileNotFoundError:
                pass
            self._run(values_yaml, workdir, skip_check)

    def _run(
        self,
        values_yaml: yaml.YAMLObject,
        workdir: str,
        skip_check: bool,
        delay: Optional[timedelta] = None,
    ):
        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")

        if delay is not None:
            delay = str_to_timedelta(delay)
            if values_yaml.get("minutes") or values_yaml.get("hours"):
                logger.warning(
                    "values.yaml included fields (`minutes` and `hours`) are being overridden by parameter: --delay"
                )
            hours, minutes = get_future_time(timedelta(seconds=500))
            values_yaml["minutes"] = str(minutes)
            values_yaml["hours"] = str(hours)
        else:
            default_delay = (
                values_yaml["replicas"] * 3
            )  # Assume it takes ~3 seconds to bring up each node.
            if not values_yaml.get("minutes") and not values_yaml.get("hours"):
                logger.info(
                    f"Node start time not included test params. Using calculated default of `{default_delay}` seconds after utc now."
                )
                delay = timedelta(seconds=default_delay)
                hours, minutes = get_future_time(delay)
                values_yaml["minutes"] = str(minutes)
                values_yaml["hours"] = str(hours)
            else:
                delay = timedelta_until(
                    hours=values_yaml.get("hours", "0"), minutes=values_yaml("minutes", "0")
                )
        expected_start_time = datetime.now(timezone.utc) + delay

        deploy = helm_build_from_params(
            "./deployment/nimlibp2p/regression/deploy.yaml",
            values_yaml,
            workdir,
            self.release_name,
        )

        namespace = deploy["metadata"]["namespace"]
        logger.info(f"Applying deployment to namespace: `{namespace}`")
        try:
            if not skip_check:
                wait_for_no_objs_in_namespace(namespace=namespace, api_client=self.api_client)
            else:
                namepace_is_empty = poll_namespace_has_objects(
                    namespace=namespace, api_client=self.api_client
                )
                if not namepace_is_empty:
                    logger.warning(f"Namespace is not empty! Namespace: `{namespace}`")

            logger.info(f"Running a nimlibp2p regression test with values: `{values_yaml}`")

            kubectl_apply(deploy, namespace=namespace)
            logger.info("Deployment applied. Waiting for rollout.")
            wait_for_rollout(deploy["kind"], deploy["metadata"]["name"], namespace, 3000)
            logger.info("Rollout successful.")
            wait_for_time(expected_start_time)  # Wait until the nodes begin.
            time.sleep(3000)  # TODO [regression nimlibp2p2 cleanup]: Test for nodes finished?
            logger.info("Test completed successfully.")
        finally:
            logger.info("Cleaning up resources.")
            resources_to_cleanup = get_cleanup_resources([deploy])
            logger.info(f"Resources to clean up: `{resources_to_cleanup}`")

            logger.info("Start cleanup.")
            cleanup_resources(resources_to_cleanup, namespace, self.api_client)
            logger.info("Waiting for cleanup.")
            wait_for_cleanup(resources_to_cleanup, namespace, self.api_client)
            logger.info("Finished cleanup.")

    def get_image_tag(version: str, tag_type: str):
        table = {
            "1.1.0": {
                "yamux": "v1.1.0-yamux-1",
                "mplex": "v1.1.0-mplex-2",
            },
            "1.2.0": {
                "mplex": "v1.2.0-mplex",
                "yamux": "v1.2.0-yamux",
            },
            "1.3.0": {
                "mplex": "v1.3.0-mplex",
                "yamux": "v1.3.0-yamux",
            },
            "1.4.0": {
                "mplex": "v1.4.0-mplex",
                "yamux": "v1.4.0-yamux",
            },
            "1.5.0": {
                "mplex": "v1.5.0-mplex-hash-loop",
                "yamux": "v1.5.0-yamux-hash-loop",
            },
            "1.6.0": {
                "mplex": "v1.6.0-mplex",
                "yamux": "v1.6.0-yamux",
            },
            "1.7.0": {
                "mplex": "v1.7.0-mplex",
                "yamux": "v1.7.0-yamux",
            },
            "1.7.1": {
                "mplex": "v1.7.1-mplex",
                "yamux": "v1.7.1-yamux",
            },
            "1.8.0": {
                "mplex": "v1.8.0-mplex",
                "yamux": "v1.8.0-yamux",
            },
        }
        try:
            return table[version][tag_type]
        except KeyError as e:
            e.add_note(
                f"Unknown version/type combination. version: `{version}`, tag_type: `{tag_type}`"
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

        hours, minutes = get_future_time(delay)
        return {
            "messageSize": str(humanfriendly.parse_size(size)),
            "messageRate": "10000" if size == "500KB" else "1000",
            "replicas": "1000",
            "image": {"repository": "soutullostatus/dst-test-node", "tag": tag_str},
            "minutes": str(minutes),
            "hours": str(hours),
        }


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
    deploy = helm_build_from_params(
        "./deployment/nimlibp2p/regression/deploy.yaml",
        values,
        os.path.join(workdir, ".."),
        "pod",
    )

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
