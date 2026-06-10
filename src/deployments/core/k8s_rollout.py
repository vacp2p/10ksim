# Python Imports
import asyncio
import logging
import time
from typing import Callable, Iterable, Optional, Tuple

from kubernetes import client
from kubernetes.client import (
    ApiException,
    V1DaemonSet,
    V1Deployment,
    V1Pod,
    V1StatefulSet,
)

from src.deployments.core.k8s_deploy import get_namespaced
from src.deployments.core.k8s_object import V1Deployable, dict_to_k8s_object, k8s_obj_to_dict

logger = logging.getLogger(__name__)


def poll_rollout_status(
    deployment: dict | V1Deployable,
    *,
    condition: Callable[[V1Deployable], bool] | None = None,
) -> Tuple[int, int]:
    """
    Poll the rollout status for the given resource.

    :condition: Used to determine if the deployment is ready.
    `condition(obj) -> bool`, should return `True` for ready and `False` for not ready.
    If `None` and  `kind == StatefulSet`, checks that all pods are updated and ready.
    If `None` and `kind == Pod`, checks that the pod has a status condition with `("Ready", "True")`.
    etc.
    """
    if isinstance(deployment, dict):
        deployment = dict_to_k8s_object(deployment, "V1" + deployment["kind"])
    kind = deployment.kind.lower()

    obj = get_namespaced(deployment)

    if kind == "deployment":

        def default_condition(obj: V1Deployment):
            desired = obj.spec.replicas
            available = obj.status.available_replicas or 0
            return available == desired

    elif kind == "statefulset":

        def default_condition(obj: V1StatefulSet):
            ready = getattr(obj.status, "ready_replicas", 0) or 0
            desired = obj.spec.replicas
            logger.info(f"Statefulset `{obj.metadata.name}` ready={ready} total={desired}")
            return (
                obj.status.current_revision == obj.status.update_revision
                and desired == getattr(obj.status, "available_replicas", 0)
                and desired == getattr(obj.status, "updated_replicas", 0)
                and desired == getattr(obj.status, "ready_replicas", 0)
            )

    elif kind == "daemonset":

        def default_condition(obj: V1DaemonSet):
            desired = obj.spec.replicas
            desired = obj.status.desired_number_scheduled or 0
            available = obj.status.number_available or 0
            return available == desired

    elif kind == "pod":

        def default_condition(pod: V1Pod):
            return check_pod_condition(pod)

    elif kind == "service":
        # Services don't have a rollout status, they are immediately available
        return True

    else:
        raise ValueError(f"Unsupported kind: `{kind}`")

    if condition is None:
        return default_condition(obj)
    return condition(obj)


async def wait_for_rollout(
    deployment: dict | V1Deployable,
    api_client,
    *,
    timeout: int = 300,
    polling_interval: int = 8,
    condition: Optional[Callable[[V1Deployable], bool]] = None,
):
    """
    Wait for a rollout of a Kubernetes workload, or a pod ready condition.

    :timeout: Timeout in seconds.

    :condition: Used to determine if the rollout is done.
    `condition(obj) -> bool`, should return `True` for ready and `False` for not ready.
    If `None` and  `kind == StatefulSet`, checks that all pods are updated and ready.
    If `None` and `kind == Pod`, checks that the pod has a status condition with `("Ready", "True")`.
    etc.

    Raises TimeoutError if timeout is exceeded.
    """
    deployment = k8s_obj_to_dict(deployment)
    namespace = deployment["metadata"]["namespace"]
    name = deployment["metadata"]["name"]
    kind = deployment["kind"]

    logger.info(f"Waiting for {kind} `{name}` in namespace `{namespace}` (timeout: {timeout}s)...")

    start_time = time.time()
    while True:
        try:
            is_ready = poll_rollout_status(deployment, condition=condition)
        except ApiException as e:
            logger.warning(f"Error fetching `{kind}`: `{e}`")
            await asyncio.sleep(polling_interval)
            continue

        logger.info(f"Waiting for {kind} `{name}`...")

        if is_ready:
            logger.info(f"{kind} `{name}` is ready")
            return

        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Timeout waiting for {kind} `{name}`.")

        await asyncio.sleep(polling_interval)


def get_pods_for_statefulset(name: str, namespace: str, api_client=None) -> Iterable[V1Pod]:
    api_client = api_client or client.ApiClient()
    apps_api = client.AppsV1Api(api_client)
    core_api = client.CoreV1Api(api_client)

    kwargs = {
        "namespace": namespace,
    }

    statefulset = apps_api.read_namespaced_stateful_set(name=name, namespace=namespace)
    selector = statefulset.spec.selector
    labels = selector.match_labels if selector and selector.match_labels else None
    if labels is not None:
        kwargs["label_selector"] = ",".join(f"{k}={v}" for k, v in labels.items())

    def has_matching_owner(obj: V1Pod):
        def is_ss_owner(owner):
            return all(
                [
                    owner.kind == "StatefulSet",
                    owner.api_version == "apps/v1",
                    owner.name == statefulset.metadata.name,
                    owner.uid == statefulset.metadata.uid,
                    getattr(owner, "controller", True),
                ]
            )

        owners = obj.metadata.owner_references
        if not owners:
            return False
        return any(is_ss_owner(owner) for owner in owners)

    return filter(
        lambda obj: has_matching_owner(obj),
        core_api.list_namespaced_pod(**kwargs).items,
    )


def check_pod_condition(
    pod: V1Pod, condition: Optional[Tuple[str, str] | Callable[[V1Pod], bool]] = None
) -> bool:
    if condition is None:
        condition = ("Ready", "True")

    if isinstance(condition, tuple):
        conditions = pod.status.conditions or []
        key, value = condition
        if any(cond.type == key and cond.status == value for cond in conditions):
            return True
        else:
            return False
    else:
        return condition(pod)
