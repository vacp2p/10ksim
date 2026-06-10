# Python Imports
import json
import logging
import subprocess
import tempfile
from functools import lru_cache, partial
from typing import Dict, Tuple

from kubernetes import client, utils
from kubernetes.utils import FailToCreateError
from ruamel import yaml

from src.deployments.core.k8s_config import get_config_file
from src.deployments.core.k8s_object import V1Deployable, k8s_obj_to_dict

logger = logging.getLogger(__name__)


def _extract_kind_and_name(kube_yaml: dict) -> Tuple[str, str]:
    kind = kube_yaml.get("kind")
    name = kube_yaml.get("metadata", {}).get("name")
    if not kind or not name:
        raise ValueError(
            f"YAML missing nessesary attributes 'kind' and 'metadata.name'. yaml: `{kube_yaml}`"
        )
    return kind, name


@lru_cache(maxsize=16)
def _kind_api_map(operation: str) -> Dict[str, Tuple[str, str]]:
    kind_map = {
        "Deployment": ("apps", "deployment"),
        "StatefulSet": ("apps", "stateful_set"),
        "DaemonSet": ("apps", "daemonset"),
        "ReplicaSet": ("apps", "replicaset"),
        "Job": ("batch", "job"),
        "CronJob": ("batch", "cronjob"),
        "ReplicationController": ("core", "replicationcontroller"),
        "Pod": ("core", "pod"),
        "Service": ("core", "service"),
    }

    template = {}
    api_prefix = f"{operation}_namespaced"

    for kind, (group, suffix) in kind_map.items():
        template[kind] = (group, f"{api_prefix}_{suffix}")

    return template


def _kubectl_operation(
    kube_yaml: dict,
    namespace: str,
    name: str,
    operation: str,
):
    """Execute kubectl operation for specific kind of Kubernetes resource."""
    logger.debug(f"{operation} the following config:\n{yaml.dump(kube_yaml)}")
    kind, _ = _extract_kind_and_name(kube_yaml)

    try:
        group, method_name = _kind_api_map(operation)[kind]
    except KeyError:
        raise ValueError(
            f"The attempted operation is not supported for this resource. kind: `{kind}`"
        )

    api_client = client.ApiClient()
    api_group_map = {
        "apps": client.AppsV1Api(api_client),
        "batch": client.BatchV1Api(api_client),
        "core": client.CoreV1Api(api_client),
    }
    api = api_group_map[group]
    method = getattr(api, method_name)

    if operation != "create":
        # A "create" operation does not need the name. Others do.
        method = partial(method, name=name)
    if operation != "read":
        # A "read" operation does not need the body. Others do.
        method = partial(method, body=kube_yaml)
    method = partial(method, namespace=namespace)

    return method()


def _kubectl_create(kube_yaml: dict, namespace: str):
    return _kubectl_operation(kube_yaml, namespace, "", "create")


def _kubectl_patch(kube_yaml: dict, namespace: str):
    _, name = _extract_kind_and_name(kube_yaml)
    return _kubectl_operation(kube_yaml, namespace, name, "patch")


def _kubectl_replace(kube_yaml: dict, namespace: str):
    _, name = _extract_kind_and_name(kube_yaml)
    return _kubectl_operation(kube_yaml, namespace, name, "replace")


def get_namespaced(obj: dict | V1Deployable):
    deployment_dict = k8s_obj_to_dict(obj)
    return _kubectl_operation(deployment_dict, obj.metadata.namespace, obj.metadata.name, "read")


def kubectl_apply(
    kube_yaml: yaml.YAMLObject,
    namespace: str,
    *,
    config_file=None,
    dry_run=False,
    exist_ok=False,
):
    """Attempts to apply a yaml, similar to the command `kubectl apply`.

    Unlike `kubectl apply`, does not track previous resources; thus, does not prune old resources.
    """
    if dry_run:
        _kubectl_apply_dry_run(kube_yaml, namespace, config_file=config_file)
    else:
        _kubectl_apply(kube_yaml, namespace, exist_ok=exist_ok)


def _kubectl_apply(kube_yaml: yaml.YAMLObject, namespace: str, *, exist_ok=True):
    """Attempts to apply a yaml.

    :param exists_ok:
        If True, replaces the deployment if it already.
        If False, reraises the exception if the deployment already exists."""
    logger.debug(f"kubectl_apply the following config:\n{str(yaml.dump(kube_yaml))}")
    kind = kube_yaml.get("kind")
    name = kube_yaml.get("metadata", {}).get("name")
    if not kind or not name:
        raise ValueError(
            f"YAML missing nessesary attributes 'kind' and 'metadata.name'. yaml: `{kube_yaml}`"
        )

    api_client = client.ApiClient()

    try:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=False) as temp:
            yaml.dump(kube_yaml, temp)
            temp.flush()
            utils.create_from_yaml(client.ApiClient(), yaml_file=temp.name, namespace=namespace)
    except FailToCreateError as e:
        if not (is_already_exists_error(e) and exist_ok):
            raise
        _kubectl_patch(kube_yaml, namespace)


def _kubectl_apply_dry_run(kube_yaml: yaml.YAMLObject, namespace: str, *, config_file: str):
    config = config_file if config_file else get_config_file()

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=False) as temp:
        yaml.dump(kube_yaml, temp)
        temp.flush()
        config_segment = ["--kubeconfig", config] if config else []
        cmd = (
            ["kubectl"]
            + config_segment
            + ["apply", "-f", temp.name, "--namespace", namespace, "--dry-run=server"]
        )
        logger.info(f"Running command: `{' '.join(cmd)}`")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(
                f"Dry run for applying kubernetes config failed."
                f"deploy.yaml: `{kube_yaml}`"
                f"returncode: `{result.returncode}`"
                f"stdout: `{result.stdout}`"
                f"stderr: `{result.stderr}`"
            )
            raise ValueError("Dry run for applying kubernetes config failed.")
        logger.debug(f"Dry run deploying `{kube_yaml}`" f"stdout: `{result.stdout}`")
        return result


def is_already_exists_error(error: FailToCreateError) -> bool:
    for api_exception in error.api_exceptions:
        try:
            body = json.loads(api_exception.body or "{}")
        except ValueError:
            continue
        reason = body.get("reason", "").lower()
        if reason == "alreadyexists":
            return True
    return False


# TODO [friendly errors]: consider checking for nessesary services before attempting to deploy(?)
def check_for_services(yamls: list[yaml.YAMLObject]):
    raise NotImplementedError()
