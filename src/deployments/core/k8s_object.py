# Python Imports
import json
from typing import Any, Literal, Union

from kubernetes import client
from kubernetes.client import (
    V1ConfigMap,
    V1CronJob,
    V1DaemonSet,
    V1Deployment,
    V1Job,
    V1Pod,
    V1PodTemplateSpec,
    V1Probe,
    V1Role,
    V1RoleBinding,
    V1Service,
    V1ServiceAccount,
    V1StatefulSet,
)

V1Deployable = Union[
    V1Role,
    V1RoleBinding,
    V1PodTemplateSpec,
    V1Pod,
    V1Deployment,
    V1Service,
    V1StatefulSet,
    V1DaemonSet,
    V1Job,
    V1CronJob,
    V1ConfigMap,
    V1ServiceAccount,
]

K8sModelStr = Literal[
    "V1Pod",
    "V1PodSpec",
    "V1Container",
    "V1Service",
    "V1Deployment",
    "V1StatefulSet",
    "V1DaemonSet",
    "V1Job",
    "V1ConfigMap",
    "V1Secret",
    "V1PersistentVolumeClaim",
    "V1Ingress",
    "V1ResourceRequirements",
    "V1Volume",
    "V1EnvVar",
    "V1Probe",
]


def dict_to_k8s_object(data: dict, model: K8sModelStr):
    """Convert a dict to a Kubernetes object."""
    api_client = client.ApiClient()

    class _FakeResponse:
        def __init__(self, obj):
            self.data = json.dumps(obj)

    return api_client.deserialize(_FakeResponse(data), model)


def dict_to_v1probe(probe_dict: dict) -> V1Probe:
    return dict_to_k8s_object(probe_dict, "V1Probe")


def k8s_obj_to_dict(deployment: Any) -> dict:
    api_client = client.ApiClient()
    return api_client.sanitize_for_serialization(deployment)
