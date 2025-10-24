import json
import logging
import os
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import List, Optional

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field

from deployment.base_experiment import BaseExperiment
from deployment.builders import build_deployment, build_deployment_2
from deployment.dict_builders.builders import WakuStatefulSetBuilder
from deployment.dict_builders.configs import StatefulSetConfig
from deployment.dict_builders.presets import WakuNode
from kube_utils import dict_set, get_YAML, get_YAML_2
from registry import experiment

logger = logging.getLogger(__name__)


def build_store_nodes() -> dict:
    config = StatefulSetConfig()
    builder = WakuStatefulSetBuilder(config)

    deployment = (
        builder.with_waku_config(name="store-0", namespace="zerotesting")
        .with_args(WakuNode.standard_args())
        .with_enr(3, ["zerotesting-bootstrap.zerotesting"])
        .with_store()
        .build()
    )

    api_client = client.ApiClient()
    return api_client.sanitize_for_serialization(deployment)
