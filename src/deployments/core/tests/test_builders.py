import pytest
from kubernetes.client import (
    V1Container,
    V1HTTPGetAction,
    V1LabelSelector,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1Pod,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Probe,
    V1ResourceRequirements,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
    V1StatefulSet,
    V1StatefulSetSpec,
)

from src.deployments.core.builders import (
    ContainerBuilder,
    ContainerCommandBuilder,
    PodBuilder,
    PodSpecBuilder,
    PodTemplateSpecBuilder,
    ServiceBuilder,
    StatefulSetBuilder,
    default_readiness_probe_health,
)
from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.helpers.utils import init_container_delay
from src.deployments.core.dependency_decorator import depends_on

# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


def _create_image(repo: str = "dst/test", tag: str = "v1.0.0") -> Image:
    """Create a real Image object for testing."""
    return Image(repo=repo, tag=tag)


def _create_pvc(name: str = "test-pvc") -> V1PersistentVolumeClaim:
    """Create a real V1PersistentVolumeClaim object for testing."""
    return V1PersistentVolumeClaim(metadata=V1ObjectMeta(name=name))


def _create_service_port(port: int = 8080, name: str = "http") -> V1ServicePort:
    """Create a real V1ServicePort object for testing."""
    return V1ServicePort(port=port, name=name)


def _create_probe() -> V1Probe:
    """Create a real V1Probe object for testing."""
    return V1Probe(
        http_get=V1HTTPGetAction(path="/health", port=8008),
        initial_delay_seconds=1,
        period_seconds=3,
    )


def _create_resource_requests_and_limits() -> V1ResourceRequirements:
    """Create a real V1ResourceRequirements object for testing."""
    return V1ResourceRequirements(
        requests={"cpu": "100m", "memory": "128Mi"}, limits={"cpu": "200m", "memory": "256Mi"}
    )


def _create_statefulset_with_default_values() -> V1StatefulSet:
    """Create expected default V1StatefulSet for testing."""
    return V1StatefulSet(
        api_version="apps/v1",
        kind="StatefulSet",
        metadata=V1ObjectMeta(name=None, namespace="default", labels=None),
        spec=V1StatefulSetSpec(
            replicas=1,  # Default from StatefulSetSpecConfig
            service_name=None,
            pod_management_policy=None,
            volume_claim_templates=None,
            selector=V1LabelSelector(match_labels=None),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(name=None, namespace=None, labels=None, annotations=None),
                spec=V1PodSpec(containers=[], init_containers=None, volumes=None, dns_config=None),
            ),
        ),
    )


def _create_pod_with_default_values() -> V1Pod:
    """Create expected default V1Pod for testing."""
    return V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=V1ObjectMeta(name=None, namespace=None, labels=None),
        spec=V1PodSpec(containers=[], init_containers=None, volumes=None, dns_config=None),
    )


def _create_service_with_default_values() -> V1Service:
    """Create expected default V1Service for testing."""
    return V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name=None, namespace=None, labels=None),
        spec=V1ServiceSpec(
            cluster_ip=None, selector=None, ports=None, type=None, publish_not_ready_addresses=None
        ),
    )


def _create_pod_template_spec_with_default_values() -> V1PodTemplateSpec:
    """Create expected default V1PodTemplateSpec for testing."""
    return V1PodTemplateSpec(
        metadata=V1ObjectMeta(name=None, namespace=None, labels=None, annotations=None),
        spec=V1PodSpec(containers=[], init_containers=None, volumes=None, dns_config=None),
    )


# --------------------------------------------------------------------------- #
# StatefulSetBuilder Tests
# --------------------------------------------------------------------------- #
class TestStatefulSetBuilder:
    """Tests for the StatefulSetBuilder class."""

    def test_build_with_no_config_returns_valid_statefulset(self):
        """Should build a valid V1StatefulSet with default config values."""
        builder = StatefulSetBuilder()
        builder.config.namespace = "default"  # Required by builder
        new_sts = builder.build()
        expected_sts = _create_statefulset_with_default_values()
        expected_sts.metadata.namespace = "default"

        # Verify the result matches expected defaults
        assert isinstance(new_sts, V1StatefulSet)
        assert new_sts == expected_sts

    def test_with_label_adds_label_to_config_and_spec(self):
        """Should add label to config, selector, and pod template."""
        builder = StatefulSetBuilder()
        builder.with_label("cluster", "vaclab")

        assert builder.config.labels == {"cluster": "vaclab"}
        assert builder.config.stateful_set_spec.selector_labels == {"cluster": "vaclab"}
        assert builder.config.stateful_set_spec.pod_template_spec_config.labels == {
            "cluster": "vaclab"
        }

    def test_with_label_returns_statefulset_builder(self):
        """Should return a StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        result = builder.with_label("test", "value")
        assert result is builder

    def test_with_label_supports_method_chaining(self):
        """Should handle successive calls correctly."""
        builder = StatefulSetBuilder()
        builder.with_label("cluster", "vaclab").with_label("team", "dst")

        assert builder.config.labels == {"cluster": "vaclab", "team": "dst"}
        assert builder.config.stateful_set_spec.selector_labels == {
            "cluster": "vaclab",
            "team": "dst",
        }

    @pytest.mark.parametrize("overwrite", [False, True])
    def test_with_image_in_container_calls_helper_with_correct_params(self, mocker, overwrite):
        """Should call with_image_for_container helper with correct arguments."""
        builder = StatefulSetBuilder()
        image = _create_image("dst/test", "v1.0.0")
        mock_with_image = mocker.patch("src.deployments.core.builders.with_image_for_container")

        builder.with_image_in_container(image, "test-container", overwrite=overwrite)

        mock_with_image.assert_called_once_with(
            config=builder.config, image=image, container_name="test-container", overwrite=overwrite
        )

    def test_with_image_in_container_returns_statefulset_builder(self, mocker):
        """Should return a StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        mocker.patch("src.deployments.core.builders.with_image_for_container")
        result = builder.with_image_in_container(_create_image(), "container")

        assert isinstance(result, StatefulSetBuilder)

    def test_with_network_delay_calls_helper(self, mocker):
        """Should call init_container_delay."""
        builder = StatefulSetBuilder()
        # Create a proper ContainerConfig to return from the mock
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        # Patch where it's imported in builders module
        mock_init_delay = mocker.patch(
            "src.deployments.core.builders.init_container_delay",
            return_value=delay_container,
        )

        builder.with_network_delay("100ms", "10ms")
        mock_init_delay.assert_called_once_with("100ms", "10ms", None)

    def test_with_network_delay_adds_init_container_to_pod_spec(self, mocker):
        """Should add init container to pod spec with correct delay and jitter values."""
        builder = StatefulSetBuilder()
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        # Add command with delay and jitter to match what init_container_delay creates
        delay_container.command_config.insert_command(
            "tc",
            [
                "qdisc",
                "add",
                "dev",
                "eth0",
                "root",
                "netem",
                "delay",
                "100ms",
                "10ms",
                "distribution",
                "normal",
            ],
        )

        mock_init_delay = mocker.patch(
            "src.deployments.core.builders.init_container_delay",
            return_value=delay_container,
        )

        builder.with_network_delay("100ms", "10ms")
        mock_init_delay.assert_called_once_with("100ms", "10ms", None)
        init_containers = (
            builder.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.init_containers
        )
        assert init_containers is not None
        assert len(init_containers) == 1
        assert init_containers[0] == delay_container

    def test_with_network_delay_returns_statefulset_builder(self, mocker):
        """Test that with_network_delay returns StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_delay", return_value=delay_container
        )
        result = builder.with_network_delay("100ms", "10ms")
        assert isinstance(result, StatefulSetBuilder)

    def test_init_container_delay_folds_rate_into_netem(self):
        """delay + a bandwidth cap share one netem qdisc (a separate tbf root would collide)."""
        assert init_container_delay(50, 0, 50).command == [
            "tc qdisc add dev eth0 root netem delay 50ms rate 50mbit"
        ]
        # existing delay+jitter output is unchanged
        assert init_container_delay(100, 10).command == [
            "tc qdisc add dev eth0 root netem delay 100ms 10ms distribution normal"
        ]

    def test_with_bandwidth_limit_calls_helper(self, mocker):
        """Should call init_container_bandwidth_limit."""
        builder = StatefulSetBuilder()
        bandwidth_container = ContainerConfig(
            name="bandwidth-limit",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        mock_init_bandwidth = mocker.patch(
            "src.deployments.core.builders.init_container_bandwidth_limit",
            return_value=bandwidth_container,
        )

        builder.with_bandwidth_limit(ingress_rate="1mbit", egress_rate="500kbit")
        mock_init_bandwidth.assert_called_once_with(
            ingress_rate="1mbit", egress_rate="500kbit", burst="32kbit"
        )

    def test_with_bandwidth_limit_adds_init_container_to_pod_spec(self, mocker):
        """Should add bandwidth limit init container to pod spec."""
        builder = StatefulSetBuilder()
        bandwidth_container = ContainerConfig(
            name="bandwidth-limit",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_bandwidth_limit",
            return_value=bandwidth_container,
        )

        builder.with_bandwidth_limit(ingress_rate="1mbit", egress_rate="500kbit", burst="32kbit")
        init_containers = (
            builder.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.init_containers
        )
        assert init_containers is not None
        assert len(init_containers) == 1
        assert init_containers[0] == bandwidth_container

    def test_with_bandwidth_limit_returns_statefulset_builder(self, mocker):
        """Test that with_bandwidth_limit returns StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        bandwidth_container = ContainerConfig(
            name="bandwidth-limit",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_bandwidth_limit",
            return_value=bandwidth_container,
        )
        result = builder.with_bandwidth_limit(ingress_rate="1mbit", egress_rate="500kbit")
        assert isinstance(result, StatefulSetBuilder)

    def test_with_bandwidth_limit_with_no_rates_returns_without_adding_container(self, mocker):
        """Should return early when neither ingress_rate nor egress_rate is provided."""
        builder = StatefulSetBuilder()
        mock_init_bandwidth = mocker.patch(
            "src.deployments.core.builders.init_container_bandwidth_limit"
        )

        result = builder.with_bandwidth_limit()

        assert isinstance(result, StatefulSetBuilder)
        assert (
            builder.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.init_containers
            is None
        )
        mock_init_bandwidth.assert_not_called()

    def test_multiple_init_containers_added_correctly(self, mocker):
        """Should handle adding multiple init containers."""
        builder = StatefulSetBuilder()
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        bandwidth_container = ContainerConfig(
            name="bandwidth-limit",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent",
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_delay", return_value=delay_container
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_bandwidth_limit",
            return_value=bandwidth_container,
        )

        builder.with_network_delay("100ms", "10ms").with_bandwidth_limit(
            ingress_rate="1mbit", egress_rate="500kbit"
        )
        init_containers = (
            builder.config.stateful_set_spec.pod_template_spec_config.pod_spec_config.init_containers
        )
        assert init_containers is not None
        assert len(init_containers) == 2
        assert delay_container in init_containers
        assert bandwidth_container in init_containers

    def test_with_replicas_sets_replica_count(self):
        """Should set the replica count in stateful_set_spec."""
        builder = StatefulSetBuilder()
        result = builder.with_replicas(5)
        assert builder.config.stateful_set_spec.replicas == 5

    def test_with_replicas_returns_statefulset_builder(self):
        """Should return a StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        result = builder.with_replicas(3)
        assert isinstance(result, StatefulSetBuilder)

    def test_with_volume_claim_template_adds_pvc_to_templates(self):
        """Should add PVC to volume_claim_templates in stateful_set_spec."""
        builder = StatefulSetBuilder()
        pvc = _create_pvc("data")
        result = builder.with_volume_claim_template(pvc)

        assert builder.config.stateful_set_spec.volume_claim_templates is not None
        assert len(builder.config.stateful_set_spec.volume_claim_templates) == 1
        assert builder.config.stateful_set_spec.volume_claim_templates[0] == pvc

    def test_with_volume_claim_template_returns_statefulset_builder(self):
        """Should return a StatefulSetBuilder for method chaining."""
        builder = StatefulSetBuilder()
        pvc = _create_pvc("data")
        result = builder.with_volume_claim_template(pvc)
        assert isinstance(result, StatefulSetBuilder)

    def test_with_volume_claim_template_can_add_multiple_pvcs(self):
        """Should add multiple PVCs via chained calls."""
        builder = StatefulSetBuilder()
        pvc1 = _create_pvc("data")
        pvc2 = _create_pvc("logs")
        builder.with_volume_claim_template(pvc1).with_volume_claim_template(pvc2)
        assert len(builder.config.stateful_set_spec.volume_claim_templates) == 2
        assert builder.config.stateful_set_spec.volume_claim_templates[0] == pvc1
        assert builder.config.stateful_set_spec.volume_claim_templates[1] == pvc2

    def test_build_with_no_namespace_raises_exception(self):
        """Should raise ValueError if namespace is not set."""
        builder = StatefulSetBuilder()
        with pytest.raises(ValueError) as exc_info:
            builder.build()
        assert "You must set the namespace before building the StatefulSet." in str(exc_info.value)

    def test_build_calls_build_stateful_set(self, mocker):
        """Should call build_stateful_set with the current config."""
        builder = StatefulSetBuilder()
        builder.config.namespace = "default"  # Required for build
        mock_build_sts = mocker.patch(
            "src.deployments.core.builders.build_stateful_set", return_value=V1StatefulSet()
        )
        result = builder.build()
        mock_build_sts.assert_called_once_with(builder.config)
        assert isinstance(result, V1StatefulSet)


# --------------------------------------------------------------------------- #
# PodBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodBuilder:
    """Tests for the PodBuilder class."""

    def test_build_with_no_config_returns_valid_pod(self):
        """Should build a valid V1Pod with default values."""
        builder = PodBuilder()
        result = builder.build()
        expected_pod = _create_pod_with_default_values()
        assert isinstance(result, V1Pod)
        assert result == expected_pod

    def test_with_app_returns_pod_builder(self):
        """Should return a PodBuilder for method chaining."""
        builder = PodBuilder()
        result = builder.with_app("app")
        assert isinstance(result, PodBuilder)

    def test_with_app_sets_app_label_in_config(self):
        """Should set the app label in config."""
        builder = PodBuilder()
        builder.with_app("test-app")
        assert builder.config.labels["app"] == "test-app"

    def test_build_calls_build_pod(self, mocker):
        """Should call build_pod"""
        builder = PodBuilder()
        mock_build_pod = mocker.patch(
            "src.deployments.core.builders.build_pod", return_value=V1Pod()
        )
        result = builder.build()
        mock_build_pod.assert_called_once_with(builder.config)
        assert isinstance(result, V1Pod)

    def test_dependency_reconciles_on_field_change(self, mocker):
        class ChildBuilder(PodBuilder):
            @depends_on("name")
            def _touch(self):
                pass

        child_builder = ChildBuilder()
        touch_func = mocker.patch.object(ChildBuilder, "_touch", autospec=True)
        child_builder.with_name("x")
        touch_func.assert_called_once_with(child_builder)


# --------------------------------------------------------------------------- #
# ServiceBuilder Tests
# --------------------------------------------------------------------------- #
class TestServiceBuilder:
    """Tests for the ServiceBuilder class."""

    def test_build_with_no_config_returns_valid_service(self):
        """Should build a valid V1Service with default values."""
        builder = ServiceBuilder()
        result = builder.build()
        expected_service = _create_service_with_default_values()
        assert isinstance(result, V1Service)
        assert result == expected_service

    def test_with_name_sets_service_name(self):
        """Should set the service name."""
        builder = ServiceBuilder()
        builder.with_name("my-service")
        assert builder.config.name == "my-service"

    def test_with_name_returns_service_builder(self):
        """Should return a ServiceBuilder for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_name("service")
        assert isinstance(result, ServiceBuilder)

    def test_with_namespace_sets_namespace(self):
        """Should set the service namespace."""
        builder = ServiceBuilder()
        builder.with_namespace("my-namespace")
        assert builder.config.namespace == "my-namespace"

    def test_with_namespace_returns_service_builder(self):
        """Should return a ServiceBuilder for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_namespace("my-namespace")
        assert isinstance(result, ServiceBuilder)

    @pytest.mark.parametrize("cluster_ip", ["10.0.0.1", "None"])
    def test_with_cluster_ip_sets_cluster_ip(self, cluster_ip):
        """Should set the cluster IP in the service spec."""
        builder = ServiceBuilder()
        builder.with_cluster_ip(cluster_ip)
        assert builder.config.service_spec.cluster_ip == cluster_ip

    def test_with_cluster_ip_returns_service_builder(self):
        """Should return a ServiceBuilder for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_cluster_ip("None")
        assert isinstance(result, ServiceBuilder)

    def test_with_selector_adds_selector(self):
        """Should add selector to the service spec."""
        builder = ServiceBuilder()
        builder.with_selector("app", "my-app")
        assert builder.config.service_spec.selector == {"app": "my-app"}

    def test_with_selector_returns_service_builder(self):
        """Should return a ServiceBuilder for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_selector("key", "value")
        assert isinstance(result, ServiceBuilder)

    def test_with_port_adds_port_to_service(self):
        """Should add port to service."""
        builder = ServiceBuilder()
        port = _create_service_port(8080, "http")
        builder.with_port(port)
        assert builder.config.service_spec.ports is not None
        assert len(builder.config.service_spec.ports) == 1
        assert builder.config.service_spec.ports[0] == port

    def test_with_port_returns_service_builder(self):
        """Should return a ServiceBuilder for method chaining."""
        builder = ServiceBuilder()
        port = _create_service_port(8080, "http")
        result = builder.with_port(port)
        assert isinstance(result, ServiceBuilder)

    def test_with_port_can_append_multiple_ports(self):
        """Should append multiple ports."""
        builder = ServiceBuilder()
        port1 = _create_service_port(8080, "http")
        port2 = _create_service_port(9090, "metrics")
        builder.with_port(port1).with_port(port2)
        assert len(builder.config.service_spec.ports) == 2
        assert builder.config.service_spec.ports[0] == port1
        assert builder.config.service_spec.ports[1] == port2

    def test_with_namespace_adds_namespace_to_config(self):
        """Should set the namespace in the service config."""
        builder = ServiceBuilder()
        builder.with_namespace("test-namespace")
        assert builder.config.namespace == "test-namespace"

    def test_with_publish_not_ready_addresses_sets_flag_and_returns_builder(self):
        """Should set publish_not_ready_addresses and return ServiceBuilder."""
        builder = ServiceBuilder()
        result = builder.with_publish_not_ready_addresses()

        assert isinstance(result, ServiceBuilder)
        assert builder.config.service_spec.publish_not_ready_addresses is True

    def test_build_calls_build_service(self, mocker):
        """Should call build_service with the current config."""
        builder = ServiceBuilder()
        mock_build_service = mocker.patch(
            "src.deployments.core.builders.build_service", return_value=V1Service()
        )
        result = builder.build()
        mock_build_service.assert_called_once_with(builder.config)
        assert isinstance(result, V1Service)


# --------------------------------------------------------------------------- #
# ContainerBuilder Tests
# --------------------------------------------------------------------------- #
class TestContainerBuilder:
    """Tests for the ContainerBuilder class."""

    def test_create_builder_with_no_config_raises_exception(self):
        """
        Should raise an exception when creating builder because of missing required fields.
        since ContainerConfig requires name, image, and image_pull_policy and doesn't have defaults.
        """
        with pytest.raises(ValueError) as exc_info:
            builder = ContainerBuilder()
        assert "validation errors for ContainerConfig" in str(exc_info.value)

    def test_build_with_custom_config_returns_container(self):
        """Should build with provided config."""
        config = ContainerConfig(name="custom", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        assert builder.config == config
        result = builder.build()
        assert isinstance(result, V1Container)

    def test_with_command_script_adds_command_lines_to_config(self):
        """Should add script lines to command config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        script = ["echo 'Hello'", "ls -la", "pwd"]
        builder.with_command_script(script)
        # Commands are inserted via insert_command method
        assert len(builder.config.command_config.commands) >= 3
        assert builder.config.command_config.commands[0].command == "echo 'Hello'"
        assert builder.config.command_config.commands[1].command == "ls -la"
        assert builder.config.command_config.commands[2].command == "pwd"

    def test_with_command_script_with_empty_list_preserves_commands(self):
        """Should handle empty script list."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        initial_len = len(builder.config.command_config.commands)
        builder.with_command_script([])

        assert len(builder.config.command_config.commands) == initial_len

    def test_with_command_script_returns_container_builder(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_command_script(["echo test"])
        assert isinstance(result, ContainerBuilder)

    def test_with_command_script_can_be_chained(self):
        """Should support method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_command_script(["echo test"]).with_command_script(["ls -la"])
        assert result.config.command_config.commands[0].command == "echo test"
        assert result.config.command_config.commands[1].command == "ls -la"

    def test_with_readiness_probe_sets_probe(self):
        """Should set readiness probe in config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        probe = _create_probe()
        builder.with_readiness_probe(probe)
        assert builder.config.readiness_probe == probe

    def test_with_readiness_probe_returns_container_builder(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_readiness_probe(_create_probe())
        assert isinstance(result, ContainerBuilder)

    def test_with_resources_sets_resources(self):
        """Should set resources in config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        resources = _create_resource_requests_and_limits()
        builder.with_resources(resources)
        assert builder.config.resources == resources

    def test_with_resources_returns_container_builder(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_resources(_create_resource_requests_and_limits())
        assert isinstance(result, ContainerBuilder)

    def test_build_calls_build_container(self, mocker):
        """Should call build_container with the current config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        mock_build_container = mocker.patch(
            "src.deployments.core.builders.build_container", return_value=V1Container(name="mock")
        )
        result = builder.build()
        mock_build_container.assert_called_once_with(builder.config)
        assert isinstance(result, V1Container)


# --------------------------------------------------------------------------- #
# PodTemplateSpecBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodTemplateSpecBuilder:
    """Tests for the PodTemplateSpecBuilder class."""

    def test_build_with_no_config_returns_valid_pod_template_spec(self):
        """Should build a valid V1PodTemplateSpec with default values."""
        builder = PodTemplateSpecBuilder()
        result = builder.build()
        expected = _create_pod_template_spec_with_default_values()
        assert isinstance(result, V1PodTemplateSpec)
        assert result == expected

    def test_build_calls_build_pod_template_spec(self, mocker):
        """Should call build_pod_template_spec with the current config."""
        builder = PodTemplateSpecBuilder()
        mock_build_pod_template_spec = mocker.patch(
            "src.deployments.core.builders.build_pod_template_spec",
            return_value=V1PodTemplateSpec(),
        )
        result = builder.build()
        mock_build_pod_template_spec.assert_called_once_with(builder.config)
        assert isinstance(result, V1PodTemplateSpec)


# --------------------------------------------------------------------------- #
# PodSpecBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodSpecBuilder:
    """Tests for the PodSpecBuilder class."""

    def test_build_with_no_config_returns_valid_pod_spec(self):
        """Should build a valid V1PodSpec with default config."""
        builder = PodSpecBuilder()
        result = builder.build()
        assert isinstance(result, V1PodSpec)
        assert result is not None

    def test_add_container_append_new_container(self):
        """Should append new container in config."""
        builder = PodSpecBuilder()
        builder.add_container(
            ContainerConfig(name="test1", image=_create_image(), image_pull_policy="IfNotPresent")
        )
        builder.add_container(
            ContainerConfig(name="test2", image=_create_image(), image_pull_policy="Always")
        )
        assert len(builder.config.container_configs) == 2
        assert builder.config.container_configs[0].name == "test1"
        assert builder.config.container_configs[1].name == "test2"

    def test_add_container_supports_dict_and_v1container(self):
        """Should support adding containers as dict or V1Container."""
        builder = PodSpecBuilder()
        container_dict = {
            "name": "dict-container",
            "image": "busybox:latest",
            "imagePullPolicy": "IfNotPresent",
        }
        v1_container = V1Container(
            name="v1-container", image="nginx:latest", image_pull_policy="Always"
        )
        builder.add_container(container_dict)
        builder.add_container(v1_container)
        assert len(builder.config.container_configs) == 2
        assert builder.config.container_configs[0].name == "dict-container"
        assert builder.config.container_configs[1].name == "v1-container"

    def test_add_container_returns_pod_spec_builder(self):
        """Should return self for method chaining."""
        builder = PodSpecBuilder()
        container = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        result = builder.add_container(container)
        assert isinstance(result, PodSpecBuilder)

    def test_add_init_container_adds_init_container(self):
        """Should add init container in config."""
        builder = PodSpecBuilder()
        init_container = ContainerConfig(
            name="init", image=_create_image(), image_pull_policy="Always"
        )
        builder.add_init_container(init_container)
        assert builder.config.init_containers is not None
        assert len(builder.config.init_containers) == 1
        assert builder.config.init_containers[0].name == "init"

    def test_add_init_container_returns_pod_spec_builder(self):
        """Should return self for method chaining."""
        builder = PodSpecBuilder()
        init_container = ContainerConfig(
            name="init", image=_create_image(), image_pull_policy="Always"
        )
        result = builder.add_init_container(init_container)
        assert isinstance(result, PodSpecBuilder)

    def test_add_container_supports_chained_calls(self):
        """Should support full method chaining."""
        builder = PodSpecBuilder()
        container = ContainerConfig(name="main", image=_create_image(), image_pull_policy="Always")
        init_container = ContainerConfig(
            name="init", image=_create_image(), image_pull_policy="Always"
        )
        result = builder.add_container(container).add_init_container(init_container)
        assert isinstance(result, PodSpecBuilder)
        assert len(builder.config.container_configs) == 1
        assert len(builder.config.init_containers) == 1

    def test_with_service_account_name_sets_value_and_returns_pod_spec_builder(self):
        """Should set service account name and return PodSpecBuilder."""
        builder = PodSpecBuilder()
        result = builder.with_service_account_name("default")

        assert isinstance(result, PodSpecBuilder)
        assert builder.config.service_account_name == "default"


# --------------------------------------------------------------------------- #
# ContainerCommandBuilder Tests
# --------------------------------------------------------------------------- #
class TestContainerCommandBuilder:
    """Tests for the ContainerCommandBuilder class."""

    def test_build_with_no_config_returns_none_command_list(self):
        """Should build command list with default config."""
        builder = ContainerCommandBuilder()
        command, args = builder.build()

        # Empty command config returns (None, None)
        assert command is None
        assert args is None

    def test_add_line_with_valid_command_adds_to_list(self):
        """Should add command line to the list."""
        builder = ContainerCommandBuilder()
        builder.add_line("echo", ["hello"])

        assert len(builder.config.commands) == 1
        assert builder.config.commands[0].command == "echo"
        assert builder.config.commands[0].args == ["hello"]
        assert builder.config.commands[0].multiline is False

    def test_add_line_with_none_args_converts_adds_empty_args(self):
        """Should handle None args by converting to empty list."""
        builder = ContainerCommandBuilder()
        builder.add_line("pwd", None)

        assert len(builder.config.commands) == 1
        assert builder.config.commands[0].command == "pwd"
        assert builder.config.commands[0].args == []

    def test_add_line_supports_tuple_args(self):
        """Should handle tuple args."""
        builder = ContainerCommandBuilder()
        args = [("--port", "8080"), ("--host", "0.0.0.0")]
        builder.add_line("serve", args)
        assert builder.config.commands[0].args == args

    def test_add_line_with_multiline_flag_sets_multiline(self):
        """Should set multiline flag correctly."""
        builder = ContainerCommandBuilder()
        builder.add_line("cat", ["file.txt"], multiline=True)
        assert builder.config.commands[0].multiline is True

    def test_add_line_returns_container_command_builder(self):
        """Should return self for method chaining."""
        builder = ContainerCommandBuilder()
        result = builder.add_line("echo", ["test"])
        assert isinstance(result, ContainerCommandBuilder)

    def test_add_line_supports_multiple_chaining(self):
        """Should handle multiple command lines."""
        builder = ContainerCommandBuilder()
        builder.add_line("mkdir", ["-p", "/app"]).add_line("npm", ["install"]).add_line(
            "npm", ["start"]
        )

        assert len(builder.config.commands) == 3
        assert builder.config.commands[0].command == "mkdir"
        assert builder.config.commands[0].args == ["-p", "/app"]
        assert builder.config.commands[1].command == "npm"
        assert builder.config.commands[1].args == ["install"]
        assert builder.config.commands[2].command == "npm"
        assert builder.config.commands[2].args == ["start"]

    def test_build_calls_build_command_with_current_config(self, mocker):
        """Should call build_command with the current config."""
        builder = ContainerCommandBuilder()
        builder.add_line("echo", ["hello"])
        mock_build_command = mocker.patch(
            "src.deployments.core.builders.build_command", return_value=(["echo"], ["hello"])
        )
        command, args = builder.build()
        mock_build_command.assert_called_once_with(builder.config)
        assert command == ["echo"]
        assert args == ["hello"]


# --------------------------------------------------------------------------- #
# default_readiness_probe_health Tests
# --------------------------------------------------------------------------- #
class TestDefaultReadinessProbeHealth:
    """Tests for the default_readiness_probe_health function."""

    def test_default_readiness_probe_health_when_called_returns_dict_with_correct_structure(self):
        """Should return a dictionary with the expected probe configuration."""
        result = default_readiness_probe_health()

        assert isinstance(result, dict)
        assert "failureThreshold" in result
        assert "httpGet" in result
        assert "initialDelaySeconds" in result
        assert "periodSeconds" in result
        assert "successThreshold" in result
        assert "timeoutSeconds" in result

    def test_default_readiness_probe_health_when_called_returns_correct_values(self):
        """Should return probe config with correct default values."""
        result = default_readiness_probe_health()

        assert result["failureThreshold"] == 1
        assert result["initialDelaySeconds"] == 1
        assert result["periodSeconds"] == 3
        assert result["successThreshold"] == 3
        assert result["timeoutSeconds"] == 5

    def test_default_readiness_probe_health_when_called_configures_http_get(self):
        """Should configure httpGet with correct path and port."""
        result = default_readiness_probe_health()

        assert "httpGet" in result
        assert result["httpGet"]["path"] == "/health"
        assert result["httpGet"]["port"] == 8008

    def test_default_readiness_probe_health_with_multiple_calls_returns_new_dict_each_time(self):
        """Should return a new dict instance on each call."""
        result1 = default_readiness_probe_health()
        result2 = default_readiness_probe_health()
        assert result1 is not result2
        assert result1 == result2
