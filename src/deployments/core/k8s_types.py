# Python Imports
from typing import Union

# Project Imports
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
