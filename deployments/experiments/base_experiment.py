import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from kubernetes.client import ApiClient
from pydantic import BaseModel, Field
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap

from helm_deployment.builders import build_deployment
from kube_utils import (
    dict_apply,
    dict_get,
    dict_partial_compare,
    dict_set,
    dict_visit,
    get_cleanup,
    kubectl_apply,
    poll_namespace_has_objects,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
)

logger = logging.getLogger(__name__)


def parse_events_log(
    log_path: str,
    events_list: List[Tuple[Dict[str, str], str]],
    *,
    extract: Callable[[dict], Any] | None = None,
) -> dict:
    """
    Return a new dict constructed by parsing the event log.
    Each line in `log_path` is converted to an event (dict).
    If the event contains all of the (key, value) items from a dict in `events_list`,
    then the event is converted to a new value using `extract(event)` and added at `path` in the new dict,
    where `path` is the value from the `events_list`.

    :param log_path: Path to events log.
    :param events_list: List of tuples mapping a dict to compare to the line to a path in the return dict.
    :param extract: A function mapping the json loaded from the event log to the value in the return dict.
    :return: dict constructed from extracting matchign lines from log_path and converting them to values using `extract`.
    :rtype: dict
    """
    if extract is None:
        extract = lambda event: datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
    return_dict = {}
    with open(log_path, "r") as events_log:
        for line in events_log:
            event = json.loads(line)
            for key, path in events_list:
                try:
                    if dict_partial_compare(event, key):
                        new_value = extract(event)
                        dict_set(
                            return_dict,
                            path,
                            new_value,
                            sep=".",
                        )
                except KeyError:
                    pass
    return return_dict


def format_metadata_timestamps(metadata: dict) -> dict:
    def format_item(node):
        try:
            return node.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except AttributeError:
            pass

    return dict_apply(metadata, format_item)


def get_valid_shifted_times(deltatime_map: Dict[str, timedelta], metadata: dict) -> dict:
    shifted = deepcopy(metadata)
    for path, delta in deltatime_map.items():
        time_value = dict_get(shifted, path, default=None, sep=".")
        if time_value is not None:
            shifted_time = time_value + delta
            dict_set(shifted, path, shifted_time, sep=".", replace_leaf=True)

    filtered = {}

    def filter(path, obj):
        try:
            start_dt = obj["start"]
            end_dt = obj["end"]
            if end_dt <= start_dt:
                return
            dict_set(filtered, path / "start", start_dt)
            dict_set(filtered, path / "end", end_dt)
        except (KeyError, TypeError) as e:
            pass

    dict_visit(shifted, filter)

    return filtered


class BaseExperiment(ABC, BaseModel):
    """Base experiment that add an ExitStack with `workdir` to `run` and uses an internal `_run`.

    How to use:
        - Inherit from this class.
        - Call `BaseExperiment.add_args` in the child class's `add_parser`
        - Implement `_run` in the child class.
    """

    events_log_path: Path = Field(default=Path("events.log"))

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

    def build(self, values_yaml, workdir, service: str, *, extra_values_paths=None):
        yaml_obj = build_deployment(
            deployment_dir=Path(os.path.dirname(__file__)) / service,
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

    def deploy(
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
        timeout=3600,
    ):
        def given(var):
            return var is not None

        if given(deployment_yaml) == (given(service) and given(workdir)):
            raise ValueError(
                "Invalid arguments. Pass `deployment_yaml` xor (`service` and `workdir`) as arguments."
            )

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

        self.log_event(
            {"event": "deployment", "phase": "start", "service": service, "namespace": namespace}
        )
        self.deployed[namespace].append(yaml_obj)
        kubectl_apply(yaml_obj, namespace=namespace, dry_run=dry_run)

        if not dry_run:
            if wait_for_ready:
                wait_for_rollout(
                    yaml_obj["kind"],
                    yaml_obj["metadata"]["name"],
                    namespace,
                    timeout,
                    api_client,
                    ("Ready", "True"),
                )
        self.log_event(
            {"event": "deployment", "phase": "finished", "service": service, "namespace": namespace}
        )

        return yaml_obj

    def _set_events_log(self, workdir: Optional[str]) -> None:
        if self.events_log_path.is_absolute():
            return
        if not self.events_log_path.is_absolute():
            if workdir is None:
                raise ValueError(
                    f"Logging event requires absolute events_log_path or non-None workdir. Path: `{self.events_log_path}` workdir: `{workdir}` experiment type: `{type(self)}`"
                )
            self.events_log_path = Path(workdir) / self.events_log_path

    def run(
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
            self._set_events_log(workdir)
            shutil.copy(args.values_path, os.path.join(workdir, "cli_values.yaml"))
            self._run(
                api_client=api_client,
                workdir=workdir,
                args=args,
                values_yaml=values_yaml,
                stack=stack,
            )
            stack.callback(lambda: self.log_event("cleanup_start"))

        self.log_event("run_finished")

    @abstractmethod
    def _run(
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
            return json.dumps(event)
        else:
            return event

    def log_event(self, event: Any):
        out_path = Path(self.events_log_path)
        with open(out_path, "a") as out_file:
            out_file.write(self._preprocess_event(event))
            out_file.write("\n")
