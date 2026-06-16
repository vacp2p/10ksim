# Python Imports
from typing import Optional

# Project Imports
from src.deployments.core.configs.helpers.utils import HigherConfigTypes
from src.deployments.core.configs.pod import PodConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig


def apply_pod_config(config: PodConfig, namespace: str, name: str, app: str):
    config.name = name
    config.namespace = namespace
    if app:
        config.with_app(app, overwrite=True)


def apply_pod_template_spec_config(
    config: PodTemplateSpecConfig, namespace: str, name: str, app: str
):
    config.name = name
    config.namespace = namespace
    if app:
        config.with_app(app, overwrite=True)


def apply_stateful_set_spec_config(
    config: StatefulSetSpecConfig, namespace: str, name: str, app: str
):
    if app:
        config.with_app(app, overwrite=True)
    apply_pod_template_spec_config(config.pod_template_spec_config, namespace, name, app)


def apply_stateful_set_config(
    config: StatefulSetConfig, namespace: str, name: str, app: Optional[str] = None
):
    config.name = name
    config.namespace = namespace
    apply_stateful_set_spec_config(config.stateful_set_spec, namespace, name, app)


def apply_identity(config: HigherConfigTypes, name: str, namespace: str, app: Optional[str] = None):
    if isinstance(config, StatefulSetConfig):
        return apply_stateful_set_config(config, namespace=namespace, name=name, app=app)
    if isinstance(config, StatefulSetSpecConfig):
        return apply_stateful_set_spec_config(config, namespace=namespace, name=name, app=app)
    if isinstance(config, PodConfig):
        return apply_pod_config(config, namespace=namespace, name=name, app=app)
    elif isinstance(config, PodTemplateSpecConfig):
        return apply_pod_template_spec_config(config, namespace=namespace, app=app)

    raise ValueError(f"Unknown config type: {type(config)}")
