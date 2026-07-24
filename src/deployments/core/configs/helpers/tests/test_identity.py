import pytest

from src.deployments.core.configs.helpers.identity import apply_identity
from src.deployments.core.configs.pod import PodConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig


def test_apply_identity_on_pod_config():
    config = PodConfig()
    apply_identity(config, name="n", namespace="ns", app="app")
    assert config.name == "n"
    assert config.namespace == "ns"
    assert config.labels["app"] == "app"


def test_apply_identity_on_pod_template_spec_config():
    config = PodTemplateSpecConfig()
    apply_identity(config, name="n", namespace="ns", app="app")
    assert config.name == "n"
    assert config.namespace == "ns"
    assert config.labels["app"] == "app"


def test_apply_identity_on_statefulset_spec_config():
    config = StatefulSetSpecConfig()
    apply_identity(config, name="n", namespace="ns", app="app")
    assert config.pod_template_spec_config.name == "n"
    assert config.pod_template_spec_config.namespace == "ns"
    assert config.pod_template_spec_config.labels["app"] == "app"


def test_apply_identity_on_statefulset_config():
    config = StatefulSetConfig()
    apply_identity(config, name="n", namespace="ns", app="app")
    assert config.name == "n"
    assert config.namespace == "ns"
    assert config.stateful_set_spec.pod_template_spec_config.name == "n"
    assert config.stateful_set_spec.pod_template_spec_config.namespace == "ns"
    assert config.stateful_set_spec.pod_template_spec_config.labels["app"] == "app"


def test_apply_identity_without_app_does_not_set_label():
    config = PodConfig()
    apply_identity(config, name="n", namespace="ns", app=None)
    assert config.name == "n"
    assert config.namespace == "ns"
    assert config.labels is None


def test_apply_identity_unknown_type_raises():
    with pytest.raises(ValueError):
        apply_identity(object(), name="n", namespace="ns", app="app")
