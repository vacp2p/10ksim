import json
import logging
from typing import Optional, Union

from core.base_bridge import BaseBridge
from kubernetes.client import (
    V1CronJob,
    V1DaemonSet,
    V1Deployment,
    V1Job,
    V1Pod,
    V1PodTemplateSpec,
    V1StatefulSet,
)

V1Deployable = Union[
    V1PodTemplateSpec,
    V1Pod,
    V1Deployment,
    V1StatefulSet,
    V1DaemonSet,
    V1Job,
    V1CronJob,
]

import os
import shutil
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from core.kube_utils import (
    dict_get,
    get_cleanup,
    kubectl_apply,
    poll_namespace_has_objects,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
)
from helm_deployment.builders import build_deployment
from kubernetes.client import ApiClient, V1PodTemplateSpec, V1StatefulSet
from pydantic import BaseModel, Field
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap

logger = logging.getLogger(__name__)


class BaseExperiment(ABC, BaseModel):
    """Base experiment that add an ExitStack with `workdir` to `run` and uses an internal `_run`.

    How to use:
        - Inherit from this class.
        - Call `BaseExperiment.add_args` in the child class's `add_parser`
        - Implement `_run` in the child class.
    """

    events_log_path: Path = Field(default=Path("events.log"))
    metadata_log_path: Path = Field(default=Path("metadata.json"))

    deployed: dict[str, list] = defaultdict(list)
    """Dict of [namespace : yamls] for every yaml deployed with self.deploy.

    Used to determine whether or not to call `_wait_until_clear`."""

    @staticmethod
    def add_args(subparser: ArgumentParser):
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
        subparser.add_argument(
            "--dry-run",
            action="store_true",
            required=False,
            default=False,
            help="If True, does not actually deploy kubernetes configs but run kubectl apply --dry-run.",
        )
        subparser.add_argument(
            "--namespace",
            type=str,
            required=False,
            default="zerotesting",
            help="The namespace for deployments.",
        )

    def build(self, values_yaml, workdir, service: str, *, extra_values_paths=None):
        yaml_obj = build_deployment(
            deployment_dir=Path(os.path.dirname(__file__)) / ".." / "helm_deployment" / service,
            workdir=os.path.join(workdir, service),
            cli_values=values_yaml,
            name=service,
            extra_values_names=[],
            extra_values_paths=extra_values_paths,
        )

        required_fields = ["metadata/namespace", "metadata/name", "kind"]
        for field in required_fields:
            if dict_get(yaml_obj, field) is None:
                raise ValueError(
                    f"Deployment yaml must have an explicit value for field. Field: `{field}`"
                )

        return yaml_obj

    # TODO: store api_client, stack, and (experiment) args in self and remove as function params.
    async def deploy(
        self,
        api_client: ApiClient,
        stack,
        args: Namespace,
        values_yaml,
        *,
        service: Optional[str] = None,
        workdir: Optional[str] = None,
        deployment: Optional[yaml.YAMLObject | V1Deployable] = None,
        wait_for_ready: bool = True,
        extra_values_paths: List[str] = None,
        exist_ok: bool = False,
        timeout=3600,
    ):
        def given(var):
            if isinstance(var, list):
                return all(given(val) for val in var)
            return var is not None

        if given(deployment) == (given(service) and given(workdir)):
            raise ValueError(
                "Invalid arguments. Pass one of the following: `deployment`, xor (`service` and `workdir`)."
            )

        if isinstance(deployment, V1Deployable):
            deployment = api_client.sanitize_for_serialization(deployment)

        yaml_obj = (
            deployment
            if deployment is not None
            else self.build(values_yaml, workdir, service, extra_values_paths=extra_values_paths)
        )

        await self.deploy_yaml(
            api_client,
            stack,
            args,
            values_yaml,
            deployment_yaml=yaml_obj,
            wait_for_ready=wait_for_ready,
            extra_values_paths=extra_values_paths,
            exist_ok=exist_ok,
            timeout=timeout,
        )

    async def deploy_yaml(
        self,
        api_client: ApiClient,
        stack,
        args: Namespace,
        values_yaml,
        *,
        service: Optional[str] = None,
        workdir: Optional[str] = None,
        deployment_yaml: Optional[yaml.YAMLObject] = None,
        wait_for_ready: bool = True,
        extra_values_paths: List[str] = None,
        exist_ok: bool = False,
        timeout=3600,
    ):
        yaml_obj = (
            deployment_yaml
            if deployment_yaml is not None
            else self.build(values_yaml, workdir, service, extra_values_paths=extra_values_paths)
        )

        try:
            dry_run = args.dry_run
        except AttributeError:
            dry_run = False

        namespace = yaml_obj["metadata"]["namespace"]

        if len(self.deployed[namespace]) == 0:
            self._wait_until_clear(
                api_client=api_client,
                namespace=namespace,
                skip_check=args.skip_check,
            )

        if not dry_run:
            cleanup = get_cleanup(
                api_client=api_client,
                namespace=namespace,
                deployments=[yaml_obj],
            )
            stack.callback(cleanup)

        deployment_metadata = {
            "event": "deployment",
            "service": service,
            "namespace": namespace,
            "kind": yaml_obj["kind"],
            "name": yaml_obj["metadata"]["name"],
        }
        if yaml_obj["kind"] == "StatefulSet":
            deployment_metadata["replicas"] = yaml_obj["spec"]["replicas"]

        self.log_event({"phase": "start", **deployment_metadata})
        self.deployed[namespace].append(yaml_obj)
        kubectl_apply(yaml_obj, namespace=namespace, dry_run=dry_run, exist_ok=exist_ok)

        if not dry_run:
            if wait_for_ready:
                await wait_for_rollout(
                    yaml_obj["kind"],
                    yaml_obj["metadata"]["name"],
                    namespace,
                    timeout,
                    api_client,
                    ("Ready", "True"),
                )
        self.log_event({"phase": "finished", **deployment_metadata})

        return yaml_obj

    def _get_out_path(self, path: Path, out_dir: Optional[str]) -> Path:
        if path.is_absolute():
            return path
        if not path.is_absolute():
            if out_dir is None:
                raise ValueError(
                    f"Out paths are required to be absolute paths or have a non-None out path. Path: `{path}` out_dir: `{out_dir}` experiment type: `{type(self)}`"
                )
            return Path(out_dir) / path

    def _get_metadata(self) -> dict:
        return BaseBridge().get_metadata(self.events_log_path)

    def log_metadata(self, metadata: dict):
        self.log_event({**{"event": "metadata"}, **metadata})

    def _dump_metadata(self):
        metadata = self._get_metadata()
        self.log_metadata(metadata)
        out_path = Path(self.metadata_log_path)
        with open(out_path, "a") as out_file:
            out_file.write(json.dumps(metadata, default=str))

    async def run(
        self,
        api_client: ApiClient,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
    ):
        if values_yaml is None:
            values_yaml = CommentedMap()

        self.deployed.clear()

        workdir = args.output_folder
        if args.workdir:
            workdir = os.path.join(workdir, args.workdir)

        with ExitStack() as stack:
            stack.callback(lambda: self.log_event("cleanup_finished"))
            os.makedirs(workdir, exist_ok=True)
            self.events_log_path = self._get_out_path(self.events_log_path, args.output_folder)
            self.metadata_log_path = self._get_out_path(self.metadata_log_path, args.output_folder)
            logger.info(f"Events path: `{self.events_log_path}`")
            logger.info(f"Metadata path: `{self.metadata_log_path}`")
            self.log_event(
                {
                    "event": "metadata",
                    "experiment_name": self.__class__.name,
                    "experiment_class": self.__class__.__name__,
                    "args": vars(args),
                }
            )
            shutil.copy(args.values_path, os.path.join(workdir, "cli_values.yaml"))
            await self._run(
                api_client=api_client,
                workdir=workdir,
                args=args,
                values_yaml=values_yaml,
                stack=stack,
            )
            stack.callback(lambda: self.log_event("cleanup_start"))

        self.log_event("run_finished")
        self._dump_metadata()

    @abstractmethod
    async def _run(
        self,
        # TODO [move things into class]: move all into class so they can be accessed more easily and set before calling run?
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        pass

    def _wait_until_clear(self, api_client: ApiClient, namespace: str, skip_check: bool):
        # Wait for namespace to be clear unless --skip-check flag was used.
        if not skip_check:
            self.log_event("wait_for_clear_start")
            wait_for_no_objs_in_namespace(namespace=namespace, api_client=api_client)
            self.log_event("wait_for_clear_finished")
        else:
            namepace_is_empty = poll_namespace_has_objects(
                namespace=namespace, api_client=api_client
            )
            if not namepace_is_empty:
                logger.warning(f"Namespace is not empty! Namespace: `{namespace}`")

    def _preprocess_event(self, event: Any) -> Any:
        if isinstance(event, str):
            event = {"event": event}

        if isinstance(event, dict):
            event["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            return json.dumps(event, default=str)
        else:
            return event

    def log_event(self, event: Any):
        logger.info(event)
        out_path = Path(self.events_log_path)
        with open(out_path, "a") as out_file:
            out_file.write(self._preprocess_event(event))
            out_file.write("\n")
