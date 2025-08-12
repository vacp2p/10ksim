import argparse
import contextlib
import glob
import itertools
import logging
import logging.config
import os
import re
import shutil
import subprocess
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

import dateparser
from kubernetes import client, utils
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def get_log_level(verbosity: Union[str, int]) -> int:
    """
    Convert a verbosity value (int or str) to a logging level.

    :param verbosity: Verbosity as an integer (0-4) or log level name as a string (e.g., 'INFO').
    :type verbosity: Union[str, int]
    :return: Corresponding logging level for `logger.setLevel`.
    :rtype: int
    :raises ValueError: If the string is not a valid log level name.
    :raises TypeError: If verbosity is not int or str.
    """
    if isinstance(verbosity, int):
        if verbosity >= 4:
            return logging.NOTSET
        elif verbosity == 3:
            return logging.DEBUG
        elif verbosity == 2:
            return logging.INFO
        elif verbosity == 1:
            return logging.WARNING
        else:
            return logging.ERROR
    elif isinstance(verbosity, str):
        level = getattr(logging, verbosity.upper(), None)
        if isinstance(level, int):
            return level
        else:
            raise ValueError(f"Unknown log level name: `{verbosity}`")
    else:
        raise TypeError(
            f"Param `verbosity` must be a string or an int. Instead, given: `{type(verbosity)}`"
        )


def init_logger(logger: logging.Logger, verbosity: Union[str, int], log_path: Optional[str] = None):
    """
    Initialize the given logger's format and level. Optionally log to a file.

    :param logger: The logger instance to configure (For example: logging.getLogger(__name__)).
    :type logger: logging.Logger
    :param verbosity: Verbosity as a string (e.g., 'INFO', 'DEBUG') or as an integer (0-4).
    :type verbosity: Union[str, int]
    :param log_path: Optional path to a file to also write logs to.
    :type log_path: Optional[str]

    Set the format and level for the given logger, affecting all loggers that inherit from it.
    Optionally adds a handler to log all messages to a file.
    """
    # Remove all existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_path:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    level = get_log_level(verbosity)
    logger.setLevel(level)
    logger.info(f"Logging level set to: `{logging.getLevelName(level)}`")


logger = logging.getLogger(__name__)


def kubectl_apply(kube_yaml: yaml.YAMLObject, namespace="zerotesting"):
    logger.debug(f"kubectl_apply the following config:\n{str(yaml.dump(kube_yaml))}")
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=False) as temp:
        yaml.dump(kube_yaml, temp)
        temp.flush()
        utils.create_from_yaml(client.ApiClient(), yaml_file=temp.name, namespace=namespace)


def get_cleanup_resources(yamls: List[yaml.YAMLObject], types: Optional[List[str]] = None):
    """
    Get dict of resources to cleanup based on yamls.

    :param types: Which type of objects to gather from the yamls. If None uses default list.
    :return: Return dictionary of where key is the type of resource and values are lists of resource names.
    :rtype: Dict[Tuple[str, list[str]]]
    """
    resources = {
        "Deployment": [],
        "StatefulSet": [],
        "DaemonSet": [],
        "ReplicaSet": [],
        "ReplicationController": [],
        "Job": [],
        "CronJob": [],
        "Pod": [],
        "Service": [],
    }
    types = types if types else ["Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Pod"]
    for yaml in yamls:
        try:
            if yaml["kind"] in types:
                resources[yaml["kind"]].append(yaml["metadata"]["name"])
        except KeyError:
            pass
    return {resource[0]: resource[1] for resource in resources.items() if resource[1]}


def cleanup_resources(
    resources: dict,
    namespace: str,
    api_client,
):
    """
    Delete resources in the recommended order: controllers first, then pods, then services.
    resources: Dict mapping kind to list of names.
    """
    logger.info(f"Cleanup resources: `{resources}`")
    deletion_order = [
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "ReplicaSet",
        "ReplicationController",
        "Job",
        "CronJob",
        "Pod",
        "Service",
    ]

    map = {
        "Deployment": lambda name: client.AppsV1Api(api_client).delete_namespaced_deployment(
            name, namespace
        ),
        "StatefulSet": lambda name: client.AppsV1Api(api_client).delete_namespaced_stateful_set(
            name, namespace
        ),
        "DaemonSet": lambda name: client.AppsV1Api(api_client).delete_namespaced_daemon_set(
            name, namespace
        ),
        "ReplicaSet": lambda name: client.AppsV1Api(api_client).delete_namespaced_replica_set(
            name, namespace
        ),
        "ReplicationController": lambda name: client.CoreV1Api(
            api_client
        ).delete_namespaced_replication_controller(name, namespace),
        "Job": lambda name: client.BatchV1Api(api_client).delete_namespaced_job(name, namespace),
        "CronJob": lambda name: client.BatchV1beta1Api(api_client).delete_namespaced_cron_job(
            name, namespace
        ),
        "Pod": lambda name: client.CoreV1Api(api_client).delete_namespaced_pod(name, namespace),
        "Service": lambda name: client.CoreV1Api(api_client).delete_namespaced_service(
            name, namespace
        ),
    }

    for kind in deletion_order:
        logger.debug(f"Checking kind: `{kind}` in `{resources}`")
        names = resources.get(kind, [])
        logger.debug(f"Found {len(names)} names")
        for name in names:
            logger.debug(f"Checking name: `{name}`")
            deleter = map.get(kind)
            if not deleter:
                logger.warning(f"Unsupported kind for cleanup: `{kind}`")
                continue
            try:
                logger.info(f"Requesting deletion of {kind} `{name}` in namespace `{namespace}`.")
                deleter(name)
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"{kind} `{name}` not found.")
                else:
                    logger.warning(f"Error deleting {kind} `{name}`: {e}")


def poll_cleanup_status(
    resources: Dict[str, List[str]],
    namespace: str,
    api_client: ApiClient,
) -> bool:
    """
    Returns True if all specified resources are gone (deleted), False otherwise.
    """
    map = {
        "Deployment": lambda name: client.AppsV1Api(api_client).read_namespaced_deployment(
            name, namespace
        ),
        "StatefulSet": lambda name: client.AppsV1Api(api_client).read_namespaced_stateful_set(
            name, namespace
        ),
        "DaemonSet": lambda name: client.AppsV1Api(api_client).read_namespaced_daemon_set(
            name, namespace
        ),
        "ReplicaSet": lambda name: client.AppsV1Api(api_client).read_namespaced_replica_set(
            name, namespace
        ),
        "ReplicationController": lambda name: client.CoreV1Api(
            api_client
        ).read_namespaced_replication_controller(name, namespace),
        "Job": lambda name: client.BatchV1Api(api_client).read_namespaced_job(name, namespace),
        "CronJob": lambda name: client.BatchV1beta1Api(api_client).read_namespaced_cron_job(
            name, namespace
        ),
        "Pod": lambda name: client.CoreV1Api(api_client).read_namespaced_pod(name, namespace),
        "Service": lambda name: client.CoreV1Api(api_client).read_namespaced_service(
            name, namespace
        ),
    }

    for kind, names in resources.items():
        reader = map.get(kind.lower())
        if not reader:
            continue
        for name in names:
            try:
                reader(name)  # If no exception, resource still exists
                return False
            except ApiException as e:
                if e.status == 404:
                    continue  # Resource is gone
                else:
                    raise
    return True  # All resources are gone


def wait_for_cleanup(
    resources: Dict[str, List[str]],
    namespace: str,
    api_client,
    timeout: int = 600,
    polling_interval: int = 8,
):
    """
    Wait until all specified resources are deleted.
    """
    start_time = time.time()
    logger.info(
        f"Waiting for cleanup of resources in namespace `{namespace}` (timeout: {timeout}s)..."
    )
    while True:
        try:
            cleaned_up = poll_cleanup_status(resources, namespace, api_client)
        except ApiException as e:
            logger.warning(f"Error polling cleanup status: {e}")
            time.sleep(polling_interval)
            continue

        logger.info(f"Cleanup status: {'complete' if cleaned_up else 'incomplete'}.")

        if cleaned_up:
            logger.info(f"All specified resources cleaned up in namespace `{namespace}`.")
            return

        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(
                f"Timeout waiting for cleanup of resources in namespace `{namespace}`."
            )

        time.sleep(polling_interval)


def get_cleanup(
    api_client: ApiClient, namespace: str, deployments: List[yaml.YAMLObject]
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


def poll_rollout_status(
    kind: str,
    name: str,
    namespace: str,
    api_client,
    # TODO [extend condition checks]: union lambda
    pod_status_condition: Optional[Tuple[str, str]] = None,
    # TODO [extend condition checks]: lambda
) -> bool:
    """
    Poll the rollout status for the given resource.

    Returns: True if the resource is ready, False otherwise.

    For pod, returns True if a pod status can be found such that
    kind == pod_ready_condition[0] and status == pod_ready_condition[1].
    """

    kind = kind.lower()

    if kind == "deployment":
        obj = client.AppsV1Api(api_client).read_namespaced_deployment(name, namespace)
        desired = obj.spec.replicas or 0
        available = obj.status.available_replicas or 0
        return available == desired

    elif kind == "statefulset":
        obj = client.AppsV1Api(api_client).read_namespaced_stateful_set(name, namespace)
        desired = obj.spec.replicas or 0
        available = getattr(obj.status, "available_replicas", None)
        if available is None:
            available = getattr(obj.status, "ready_replicas", 0)
        return available == desired

    elif kind == "daemonset":
        obj = client.AppsV1Api(api_client).read_namespaced_daemon_set(name, namespace)
        desired = obj.status.desired_number_scheduled or 0
        available = obj.status.number_available or 0
        return available == desired

    # TODO [extend condition checks]: example lambda:
    # def container_cond(status):
    #     try:
    #         if status.name == "publisher-container" and status.state.terminated.reason == "Completed":
    #             return True
    #     except AttributeError:
    #         pass
    #     return False

    elif kind == "pod":
        if pod_status_condition is None:
            # TODO [extend condition checks]: add to comment: or container
            # status check.
            raise ValueError("Polling a pod requires a status condition.")
        key, value = pod_status_condition
        v1 = client.CoreV1Api(api_client)
        pod = v1.read_namespaced_pod(name, namespace)

        # for status in pod.status.container_statuses:
        #     # TODO [extend condition checks]: use lambda here
        #     container_cond(status)

        conditions = pod.status.conditions or []
        for cond in conditions:
            # TODO [extend condition checks]: use lambda here
            if cond.type == key:
                if cond.status == value:
                    return True

        return False

    else:
        raise ValueError(f"Unsupported kind: `{kind}`")


def wait_for_rollout(
    kind: str,
    name: str,
    namespace: str,
    timeout: int = 300,
    api_client=None,
    pod_ready_condition: Optional[Tuple[str, str]] = None,
    polling_interval: int = 8,
):
    """
    Wait for a rollout of a Kubernetes workload, or a pod ready condition.

    :timeout: Timeout in seconds.

    :pod_ready_condition: If set, wait for pod's Ready condition to match ('True' or 'False').

    Raises TimeoutError if timeout is exceeded.
    """
    start_time = time.time()
    target_desc = (
        f"pod `{name}` Ready=`{pod_ready_condition}`"
        if kind.lower() == "pod" and pod_ready_condition is not None
        else f"`{kind}` `{name}`"
    )
    logger.info(f"Waiting for {target_desc} in namespace `{namespace}` (timeout: {timeout}s)...")

    while True:
        try:
            ready = poll_rollout_status(
                kind,
                name,
                namespace,
                api_client,
                pod_status_condition=pod_ready_condition,
            )
        except ApiException as e:
            logger.warning(f"Error fetching `{kind}`: `{e}`")
            time.sleep(polling_interval)
            continue

        logger.info(f"Waiting: {target_desc} ready=`{ready}`...")

        if ready:
            logger.info(f"{target_desc} is ready.")
            return

        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Timeout waiting for: `{target_desc}`.")

        time.sleep(polling_interval)


def poll_namespace_has_objects(
    namespace: str, api_client: ApiClient, types: Optional[List[str]] = None
):
    """
    Poll kubernetes to see if the namespace has any objects of the given types in it*.

    *By default, does not check for secrets, configmaps, PVCs or services

    Also note that there may be some services running that won't be found
    for kubernetes versions lower than v1.25 which uses the batch/v1beta1 endpoint.

    :return: True if any such resources are found, False otherwise.
    :rtype: bool
    """
    types = types if types else ["Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Pod"]
    logger.debug(f"Checking in namespace `{namespace}` for types: `{types}`")
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api(api_client)
    batch_v1 = client.BatchV1Api(api_client)

    resource_checks = {
        "Pod": lambda: v1.list_namespaced_pod(namespace).items,
        "Service": lambda: v1.list_namespaced_service(namespace).items,
        "PersistentVolumeClaim": lambda: v1.list_namespaced_persistent_volume_claim(
            namespace
        ).items,
        "Deployment": lambda: apps_v1.list_namespaced_deployment(namespace).items,
        "StatefulSet": lambda: apps_v1.list_namespaced_stateful_set(namespace).items,
        "ReplicaSet": lambda: apps_v1.list_namespaced_replica_set(namespace).items,
        "DaemonSet": lambda: apps_v1.list_namespaced_daemon_set(namespace).items,
        "Job": lambda: batch_v1.list_namespaced_job(namespace).items,
        "ReplicationController": lambda: v1.list_namespaced_replication_controller(namespace).items,
        "CronJob": lambda: batch_v1.list_namespaced_cron_job(namespace),
    }

    for type, check in resource_checks.items():
        try:
            if type not in types:
                continue
            if check():
                return True
        except ApiException:
            continue
    return False


def wait_for_no_objs_in_namespace(
    namespace: str,
    timeout: int = 300,
    api_client: ApiClient = None,
    polling_interval: int = 2,
    types: Optional[List[str]] = None,
):
    """
    Wait until the namespace has no objects of any of the given types.

    :param timeout: Timeout in seconds.
    :type timeout: int
    :param types: Which type of objects to check for.
        See `poll_namespace_has_objects` for default value of `types`.
    :type types: list, optional
    :raises TimeoutError: If timeout is exceeded.
    """
    start_time = time.time()
    logger.info(
        f"Waiting for namespace to be clean. Namespace: `{namespace}` (timeout: {timeout}s)..."
    )
    while True:
        has_objects = poll_namespace_has_objects(
            namespace,
            api_client,
            types,
        )

        if not has_objects:
            logger.info(f"`{namespace}` is empty.")
            return

        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(
                f"Timeout waiting for namespace to be empty. Namespace: `{namespace}`"
            )

        time.sleep(polling_interval)


# TODO [friendly errors]: consider checking for nessesary services before attempting to deploy(?)
def check_for_services(yamls: list[yaml.YAMLObject]):
    raise NotImplementedError()


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def read_template_yaml(template_path):
    pattern = re.compile(r"(:\s*)(\{\{.*?\}\})(?=\s*(#.*)?$)", re.MULTILINE)

    def replacer(match):
        prefix = match.group(1)
        expr = match.group(2)
        # If already quoted (just in case), skip
        if expr.startswith('"') and expr.endswith('"'):
            return match.group(0)
        return f'{prefix}"{expr}"'

    with open(template_path, "r") as in_file:
        content = pattern.sub(replacer, in_file.read())
        return yaml.safe_load(content)


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def get_defs_from_template(template_path):
    # TODO [multiple docs]: currently only supports reading in one yaml
    # document.
    def extract_keys(line):
        keys = []
        template_re = re.compile("{{\\s*(?P<template>[a-zA-Z0-9-_\\.]+)\\s*}}")
        value_re = re.compile("Values.(?P<key>[a-zA-Z0-9-_\\.]+)")
        # TODO [label optional values]: add logic for `default <default_value>
        # <key>`
        for line_match in template_re.finditer(line):
            for var_match in value_re.finditer(line_match.group("template")):
                variable = var_match.group("key")
                keys.append(variable)
        return keys

    all_keys = []
    stack = [read_template_yaml(template_path)]
    while stack:
        curr = stack.pop()
        for _, value in curr.items():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                stack.append(value)
            else:
                all_keys.extend(extract_keys(value))
    return all_keys


# TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
def validate_values_yaml(values_yaml, template_yamls: List[yaml.yaml_object]):
    # TODO: ensure bijection between values.yaml and deployments.yaml.
    # Consider experiments with multiple deployments.yaml. For example:
    # bootstrap, nodes, publishers.
    raise NotImplementedError()


def gen_argparse(arg_defs):
    parser = argparse.ArgumentParser(description="Args generated from template.")
    # TODO [mutually exclusive args]: add logic here
    for arg in arg_defs:
        kwargs = {key: value for key, value in arg.items() if key != "name"}
        parser.add_argument(arg["name"], **kwargs)
    raise NotImplementedError()


def dict_get(
    dict: Dict, path: str | List[str], *, default: Any = None, sep: Optional[str] = os.path.sep
) -> Any:
    if isinstance(path, str):
        path = [node for node in path.split(sep) if node]
    if len(path) < 1:
        raise KeyError(f"Invalid path. Path: `{path}`")

    if len(path) == 1:
        return dict.get(path[0], default)

    try:
        return dict_get(dict[path[0]], path[1:], default=default, sep=sep)
    except (TypeError, KeyError):
        return default


def dict_set(
    dict: Dict,
    path: str | List[str],
    value: Any,
    *,
    replace_leaf: bool = False,
    replace_nondict_stems: bool = False,
    sep: Optional[str] = os.path.sep,
) -> Optional[Any]:
    """Set value in `dict` at `path`, creating sub-dicts at path nodes if they do not already exist.

    :param dict: `dict` or `dict`-like object.
    :type dict: Dict
    :param path: If given as a str, uses `sep` as separator to make a list of separators.
    :type path: str | List[str]
    :param value: Value to be set or add to the dict.
    :type value: Any
    :param replace_leaf: If False, raises KeyError if there is already a value at `path` in `dict`.
    :type replace_leaf: bool
    :param replace_nondict_stems: If True, replaces existing values in `dict` with empty `dict`s while traversing the `path`.
    :type replace_nondict_stems: bool
    :param sep: Separator to use for getting the list of path components from `path.
    :type sep: str | None

    :return: The value that already existed at `path` in `dict` and `replace_leaf == True`, or `None` if no value existed.
    :rvalue: Optional[Any]

    Raises KeyError if any node on the path is not a dict unless `replace_nondict_stems== True`.
    Raises KeyError if a value already exists at the given path unless `replace_leaf == True`.
    """
    if isinstance(path, str):
        path = [node for node in path.split(sep) if node]
    if len(path) < 1:
        raise KeyError(f"Invalid path. Path: `{path}`")
    for i, node in enumerate(path[:-1]):
        node = path[i]
        try:
            if node not in dict.keys() or replace_nondict_stems:
                dict[node] = {}
            dict = dict[node]
        except (AttributeError, TypeError):
            raise KeyError(
                f"Non-dict value already exists at path. Path: `{path[0:i]}`\tKey: `{node}`\tValue: `{dict}`"
            )

    previous = None
    if path[-1] in dict:
        if not replace_leaf:
            raise KeyError(
                f"Value already exists at path. Path: `{path}`\tValue: `{dict[path[-1]]}`"
            )
        previous = dict[path[-1]]
    dict[path[-1]] = value
    return previous


def default_chart_yaml_str(name) -> str:
    return """
    apiVersion: v2
    name: {name}
    version: 0.1.0
    description: A Helm chart for Kubernetes""".format(
        name=name
    )


def helm_build_dir(workdir: str, values_paths: List[str], name: str) -> yaml.YAMLObject:
    values = [["--values", values_path] for values_path in values_paths]
    command = ["helm", "template", ".", "--name-template", name, "--debug"] + list(
        itertools.chain(*values)
    )
    logger.info(f"Running helm template command. cwd: `{workdir}`\tcommand: `{command}`")
    # import pdb; pdb.set_trace() # todo asdf
    logger.info(f"Usable command: `{' '.join(command)}`")
    result = subprocess.run(
        command,
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise Exception(
            f"Failed to build helm template. cwd: `{workdir}`\tcommand: `{command}`\tstderr: `{result.stderr}`"
        )

    return yaml.safe_load(result.stdout)


import ruamel.yaml


def get_YAML():
    """Return a ruamel.yaml.YAML() that dumps multipline strings as multiple lines instead of escaping newlines."""

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml = ruamel.yaml.YAML()
    yaml.Representer.add_representer(str, str_representer)
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # Prevent wrapping for long values such as bash scripts.
    return yaml


def helm_build(
    # list of (source_path, target_path) or (source_path)
    deployment_template_paths: Union[List[Tuple[str, str]], List[str]],
    values: Union[List[Tuple[yaml.YAMLObject, str]], List[yaml.YAMLObject]],
    workdir,
    name,
    chart_yaml=None,
) -> yaml.YAMLObject:
    """
    :deployment_template_paths: list of (source_path, target_path) or (source_path).
    `target_path` is relative to workdir/templates/ (eg. workdir/templates/<target_path>).

    :values: list of (values.yaml, target_path) or (values.yaml).
    `target_path` is relative to workdir/templates/ (eg. workdir/templates/<target_path>).

    :name: name to be used for `--name-template` argument in `helm` command,
    which will be used for `.Release.Name` when making the deployment template.
    """
    assert values, Exception("'patches' should have at least one patch.")

    # Process params.
    if not isinstance(values[0], tuple):
        values = [(path, f"values_{i+1}.yaml") for i, path in enumerate(values)]
    if not isinstance(deployment_template_paths[0], tuple):
        deployment_template_paths = [
            (path, f"deployment_{i+1}.yaml") for i, path in enumerate(deployment_template_paths)
        ]

    # Write files.
    os.makedirs(os.path.join(workdir, "templates"), exist_ok=True)
    for source_path, target_path in deployment_template_paths:
        shutil.copy(source_path, os.path.join(workdir, "templates", target_path))
    for path, values_yaml in values:
        with open(os.path.join(workdir, path), "w") as out:
            out.write(yaml.dump(values_yaml, Dumper=yaml.RoundTripDumper))
    with open(os.path.join(workdir, "Chart.yaml"), "w") as chart:
        chart.write(chart_yaml)

    # Build and output.
    values_paths = [value[0] for value in values]
    return helm_build_dir(workdir, values_paths, name)


def helm_build_from_params(
    template_path,
    values_yaml: yaml.YAMLObject,
    workdir: str,
    name: str = None,
) -> yaml.YAMLObject:
    """

    :name: name to be used for `--name-template` argument in `helm` command,
    which will be used for `.Release.Name` when making the deployment template.
    """
    values = [("values.yaml", values_yaml)]
    chart_yaml = default_chart_yaml_str("my-chart")
    name = name if name else "noname"
    return helm_build([template_path], values, workdir, name, chart_yaml)


def prepend_paths(base_path: str, paths: List[str]) -> List[str]:
    return [os.path.join(base_path, path) for path in paths]


def relative_paths(base_path: str, paths: List[str]) -> List[str]:
    return [
        os.path.relpath(
            os.path.join(base_path, path) if not os.path.isabs(path) else path, base_path
        )
        for path in paths
    ]


def get_values_yamls(
    work_sub_dir,
    *,
    include_default: bool = False,
    base_dir: Optional[str] = None,
    absolute_paths: bool = False,
) -> List[str]:
    """Get all *.yaml files from this experiment that should be included in `--values <values.yaml>` args.

    :param include_default: If True, includes the "values.yaml",
                            which is included by default in `helm` projects.
                            The default values.yaml will be the first value in returned list.
    :param absolute_paths: If True, return list as absolute paths. Overrides `base_dir`.
    :param base_dir: If True, return list as relative paths using `base_dir` as the root path.
    :return: A list of all relevant *.yaml files according to the options provided.
    :rtype: List[str]

    Make sure to add your own cli_values.yaml passed through the CLI.
    """
    templates_dir = os.path.join(work_sub_dir, "templates")
    paths = [
        os.path.relpath(path, work_sub_dir)
        for path in glob.glob(os.path.join(templates_dir, "**", "*.values.yaml"), recursive=True)
    ]

    if include_default:
        default_path = os.path.join(work_sub_dir), "values.yaml"
        if os.path.exists(default_path):
            paths = [default_path] + paths

    absolute_values = [os.path.join(work_sub_dir, path) for path in paths]
    if absolute_paths:
        return absolute_values

    if base_dir:
        return relative_paths(base_dir, absolute_values)

    return paths


def merge_yaml_values(base, override) -> object:
    """Return the result of merging `override` into `base`.

    # Yaml merging rules

    maps: Merged recursively, favoring `override`.
    The combined map should have have all key value pairs
    between `base` and `override` with unique keys. For non-unique keys,
    if the value is map, then the map is merge recursively,
    otherwise, the `override` value is used.

    lists and other values: The value from `base` is overridden entirely
    by the value from `override`. No merging is done for lists or any
    other non-map type.

    :param base: Base value in a Yaml object
    :type base: object
    :param override: Yaml oject value to merge into `base`
    :type override: object
    :return: The yaml value resulting from merging `override` into `base`
    :rtype: object
    """
    if isinstance(base, CommentedMap) and isinstance(override, CommentedMap):
        merged = deepcopy(base)
        for key in override:
            if key in merged:
                merged[key] = merge_yaml_values(merged[key], override[key])
            else:
                merged[key] = deepcopy(override[key])
        return merged
    return override


def merge_helm_values(
    yamls: List[Union[str, CommentedMap, CommentedSeq]],
) -> Optional[yaml.YAMLObject]:
    if not yamls:
        return None

    def load_yaml(item: Union[str, CommentedMap, CommentedSeq]) -> yaml.YAMLObject:
        if isinstance(item, str):
            with open(item, "r") as fin:
                return yaml.safe_load(fin)
        return item

    merged_yaml = load_yaml(item[0])
    for item in yamls[1:]:
        merged_yaml = merge_yaml_values(merged_yaml, load_yaml(item))
    return merged_yaml


@contextlib.contextmanager
def maybe_dir(dir: Optional[str]) -> Iterator[str]:
    if dir:
        yield dir
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir


def assert_equals(obj_1, obj_2):
    assert obj_1 == obj_2, f"Assertion failed: `{obj_1}` == `{obj_2}`"


def get_future_time(delay: timedelta, timezone: Optional[dt_timezone] = None) -> datetime:
    """
    Get the time it will be in `timezone` after `delay`.

    :param delay: The delay from current time.
    :param timezone: The timezone of the future time.
    :return: datetime in `timezone` of the now + `delay`.
    :rtype: datetime
    """
    timezone = timezone if timezone else dt_timezone.utc
    current_time_utc = datetime.now(timezone)
    return current_time_utc + delay


def wait_for_time(target_dt: datetime):
    """
    Wait until the specified target datetime.

    This function sleeps until the current UTC time reaches or surpasses
    the given `target_dt`.

    :param target_dt: The target datetime to wait for. Must be timezone-aware.
    :type target_dt: datetime.datetime

    :raises ValueError: If `target_dt` is not timezone-aware.
    """
    if target_dt.tzinfo is None or target_dt.tzinfo.utcoffset(target_dt) is None:
        raise ValueError("target_dt must be timezone-aware")

    now = datetime.now(dt_timezone.utc)
    seconds = (target_dt - now).total_seconds()
    if seconds > 0:
        time.sleep(seconds)


def timedelta_until(hours: int, minutes: int) -> timedelta:
    """Get the timedelta for the next UTC time represented by the given `hours` and `minutes`."""
    now = datetime.now(dt_timezone.utc)
    target = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    # If target is in the past, add 1 day to get the next occurrence.
    if target <= now:
        target += timedelta(days=1)

    return target - now


def str_to_timedelta(duration: str):
    utc_now = datetime.now(dt_timezone.utc)
    parsed_date = dateparser.parse(
        duration,
        settings={
            "RELATIVE_BASE": utc_now,
            "TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    if parsed_date is None:
        raise ValueError(f"Failed to parse duration: `{duration}`")
    return utc_now - parsed_date


def get_flag_value(flag: str, command: List[str]) -> Optional[int]:
    for node in command:
        matches = re.search(f"--{flag}=(?P<numMessages>\\d+)", node)
        try:
            return int(matches["numMessages"])
        except (TypeError, IndexError):
            pass
    return None
