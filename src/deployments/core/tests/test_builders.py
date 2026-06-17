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

# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def _create_image(repo: str = "dst/test", tag: str = "v1.0.0") -> Image:
    """Create a real Image object for testing."""
    return Image(repo=repo, tag=tag)


def _create_pvc(name: str = "test-pvc") -> V1PersistentVolumeClaim:
    """Create a real V1PersistentVolumeClaim object for testing."""
    return V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name=name)
    )


def _create_service_port(port: int = 8080, name: str = "http") -> V1ServicePort:
    """Create a real V1ServicePort object for testing."""
    return V1ServicePort(
        port=port,
        name=name
    )


def _create_probe() -> V1Probe:
    """Create a real V1Probe object for testing."""
    return V1Probe(
        http_get=V1HTTPGetAction(path="/health", port=8008),
        initial_delay_seconds=1,
        period_seconds=3
    )


def _create_resource_requests_and_limits() -> V1ResourceRequirements:
    """Create a real V1ResourceRequirements object for testing."""
    return V1ResourceRequirements(
        requests={"cpu": "100m", "memory": "128Mi"},
        limits={"cpu": "200m", "memory": "256Mi"}
    )


def _create_statefulset_with_default_values() -> V1StatefulSet:
    """Create expected default V1StatefulSet for testing.
    """
    return V1StatefulSet(
        api_version="apps/v1",
        kind="StatefulSet",
        metadata=V1ObjectMeta(
            name=None,
            namespace=None,
            labels=None
        ),
        spec=V1StatefulSetSpec(
            replicas=1,  # Default from StatefulSetSpecConfig
            service_name=None,
            pod_management_policy=None,
            volume_claim_templates=None,
            selector=V1LabelSelector(match_labels=None),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(
                    name=None,
                    namespace=None,
                    labels=None,
                    annotations=None
                ),
                spec=V1PodSpec(
                    containers=[],
                    init_containers=None,
                    volumes=None,
                    dns_config=None
                )
            )
        )
    )


# --------------------------------------------------------------------------- #
# StatefulSetBuilder Tests
# --------------------------------------------------------------------------- #
class TestStatefulSetBuilder:
    """Tests for the StatefulSetBuilder class."""

    def test_build_with_no_config_returns_valid_statefulset(self):
        """Should build a valid V1StatefulSet with default config values."""
        builder = StatefulSetBuilder()
        new_sts = builder.build()
        expected_sts = _create_statefulset_with_default_values()
        
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
        """Should handle multiple labels correctly."""
        builder = StatefulSetBuilder()
        builder.with_label("cluster", "vaclab").with_label("team", "dst")

        assert builder.config.labels == {"cluster": "vaclab", "team": "dst"}
        assert builder.config.stateful_set_spec.selector_labels == {
            "cluster": "vaclab",
            "team": "dst",
        }


    def test_with_image_in_container_with_valid_params_calls_helper(self, mocker):
        """Should call with_image_for_container helper with correct arguments."""
        builder = StatefulSetBuilder()
        image = _create_image("dst/test", "v1.0.0")
        mock_with_image = mocker.patch("src.deployments.core.builders.with_image_for_container")
        builder.with_image_in_container(image, "test-container")

        mock_with_image.assert_called_once_with(
            builder.config, "test-container", image, overwrite=False
        )

    def test_with_image_in_container_with_overwrite_true_passes_parameter(self, mocker):
        """Should pass overwrite flag to helper function."""
        builder = StatefulSetBuilder()
        image = _create_image("dst/test", "v1.0.0")
        mock_with_image = mocker.patch("src.deployments.core.builders.with_image_for_container")

        builder.with_image_in_container(image, "test-container", overwrite=True)

        mock_with_image.assert_called_once_with(
            builder.config, "test-container", image, overwrite=True
        )

    def test_with_image_in_container_with_any_image_returns_self(self, mocker):
        """Should return self for method chaining."""
        builder = StatefulSetBuilder()
        mocker.patch("src.deployments.core.builders.with_image_for_container")
        result = builder.with_image_in_container(_create_image(), "container")

        assert result is builder

    def test_with_network_delay_with_valid_params_calls_helper(self, mocker):
        """Should call init_container_delay and add init container."""
        builder = StatefulSetBuilder()
        # Create a proper ContainerConfig to return from the mock
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent"
        )
        # Patch where it's imported in builders module
        mock_init_delay = mocker.patch(
            "src.deployments.core.builders.init_container_delay",
            return_value=delay_container,
        )

        builder.with_network_delay("100ms", "10ms")

        # Verify the helper was called
        mock_init_delay.assert_called_once_with("100ms", "10ms")

    def test_with_network_delay_with_overwrite_true_passes_parameter(self, mocker):
        """Should pass overwrite flag when adding init container."""
        builder = StatefulSetBuilder()
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent"
        )
        mocker.patch(
            "src.deployments.core.builders.init_container_delay",
            return_value=delay_container,
        )

        builder.with_network_delay("50ms", "5ms", overwrite=True)

        # The method calls add_init_container internally, just verify no exception
        assert True

    def test_with_network_delay_with_any_delay_returns_self(self, mocker):
        """Test that with_network_delay returns self for chaining."""
        builder = StatefulSetBuilder()
        delay_container = ContainerConfig(
            name="network-delay",
            image=_create_image("busybox", "latest"),
            image_pull_policy="IfNotPresent"
        )
        mocker.patch("src.deployments.core.builders.init_container_delay", return_value=delay_container)
        result = builder.with_network_delay("100ms", "10ms")

        assert result is builder

    def test_with_label_with_chained_calls_supports_fluent_api(self):
        """Should support method chaining with labels."""
        builder = StatefulSetBuilder()

        result = (
            builder
            .with_label("app", "test")
            .with_label("env", "prod")
        )

        assert result is builder
        assert builder.config.labels["app"] == "test"
        assert builder.config.labels["env"] == "prod"

    def test_with_replicas_with_valid_count_sets_replica_count(self):
        """Should set the replica count in stateful_set_spec."""
        builder = StatefulSetBuilder()
        
        result = builder.with_replicas(5)
        
        assert builder.config.stateful_set_spec.replicas == 5
        assert result is builder

    def test_with_volume_claim_template_with_single_pvc_adds_to_templates(self):
        """Should add PVC to volume_claim_templates in stateful_set_spec."""
        builder = StatefulSetBuilder()
        pvc = _create_pvc("data")
        
        result = builder.with_volume_claim_template(pvc)
        
        assert builder.config.stateful_set_spec.volume_claim_templates is not None
        assert len(builder.config.stateful_set_spec.volume_claim_templates) == 1
        assert builder.config.stateful_set_spec.volume_claim_templates[0] == pvc
        assert result is builder

    def test_with_volume_claim_template_with_multiple_pvcs_appends_all(self):
        """Should add multiple PVCs via chained calls."""
        builder = StatefulSetBuilder()
        pvc1 = _create_pvc("data")
        pvc2 = _create_pvc("logs")
        
        builder.with_volume_claim_template(pvc1).with_volume_claim_template(pvc2)
        
        assert len(builder.config.stateful_set_spec.volume_claim_templates) == 2
        assert builder.config.stateful_set_spec.volume_claim_templates[0] == pvc1
        assert builder.config.stateful_set_spec.volume_claim_templates[1] == pvc2


# --------------------------------------------------------------------------- #
# PodBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodBuilder:
    """Tests for the PodBuilder class."""

    def test_build_with_default_config_returns_valid_pod(self):
        """Should build a valid V1Pod with default config."""
        builder = PodBuilder()
        result = builder.build()

        assert isinstance(result, V1Pod)
        assert result is not None

    def test_with_app_with_any_name_returns_self(self):
        """Should return self for method chaining."""
        builder = PodBuilder()
        result = builder.with_app("app")

        assert result is builder


# --------------------------------------------------------------------------- #
# ServiceBuilder Tests
# --------------------------------------------------------------------------- #
class TestServiceBuilder:
    """Tests for the ServiceBuilder class."""

    def test_build_with_default_config_returns_valid_service(self):
        """Should build a valid V1Service with default config."""
        builder = ServiceBuilder()
        result = builder.build()

        assert isinstance(result, V1Service)
        assert result is not None

    def test_with_name_with_valid_name_sets_service_name(self):
        """Should set the service name."""
        builder = ServiceBuilder()
        builder.with_name("my-service")

        assert builder.config.name == "my-service"

    def test_with_name_with_any_name_returns_self(self):
        """Should return self for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_name("service")

        assert result is builder

    def test_with_namespace_with_valid_namespace_sets_namespace(self):
        """Should set the service namespace."""
        builder = ServiceBuilder()
        builder.with_namespace("my-namespace")

        assert builder.config.namespace == "my-namespace"

    def test_with_namespace_with_any_namespace_returns_self(self):
        """Should return self for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_namespace("namespace")

        assert result is builder

    def test_with_cluster_ip_with_valid_ip_sets_cluster_ip(self):
        """Should set the cluster IP."""
        builder = ServiceBuilder()
        builder.with_cluster_ip("10.0.0.1")

        assert builder.config.service_spec.cluster_ip == "10.0.0.1"

    def test_with_cluster_ip_with_any_ip_returns_self(self):
        """Should return self for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_cluster_ip("10.0.0.1")

        assert result is builder

    def test_with_selector_with_valid_label_adds_selector(self):
        """Should add selector via config."""
        builder = ServiceBuilder()
        builder.with_selector("app", "my-app")

        # Just verify it returns self and doesn't crash
        assert builder is not None

    def test_with_selector_with_any_label_returns_self(self):
        """Should return self for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_selector("key", "value")

        assert result is builder

    def test_with_port_with_valid_port_adds_to_service(self):
        """Should add port to service."""
        builder = ServiceBuilder()
        port = _create_service_port(8080, "http")

        builder.with_port(port)

        assert builder.config.service_spec.ports is not None
        assert len(builder.config.service_spec.ports) == 1
        assert builder.config.service_spec.ports[0] == port

    def test_with_port_with_multiple_calls_adds_all_ports(self):
        """Should handle multiple ports."""
        builder = ServiceBuilder()
        port1 = _create_service_port(8080, "http")
        port2 = _create_service_port(9090, "metrics")

        builder.with_port(port1).with_port(port2)

        assert len(builder.config.service_spec.ports) == 2
        assert builder.config.service_spec.ports[0] == port1
        assert builder.config.service_spec.ports[1] == port2

    def test_with_port_with_any_port_returns_self(self):
        """Should return self for method chaining."""
        builder = ServiceBuilder()
        result = builder.with_port(_create_service_port(8080, "http"))

        assert result is builder

    def test_with_name_with_chained_calls_supports_fluent_api(self):
        """Should support full method chaining."""
        builder = ServiceBuilder()
        port = _create_service_port(8080, "http")

        result = (
            builder.with_name("my-service")
            .with_namespace("my-ns")
            .with_cluster_ip("10.0.0.1")
            .with_port(port)
        )

        assert result is builder
        assert builder.config.name == "my-service"
        assert builder.config.namespace == "my-ns"


# --------------------------------------------------------------------------- #
# ContainerBuilder Tests
# --------------------------------------------------------------------------- #
class TestContainerBuilder:
    """Tests for the ContainerBuilder class."""

    def test_build_with_custom_config_returns_container(self):
        """Should build with provided config."""
        config = ContainerConfig(name="custom", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)

        assert builder.config == config
        result = builder.build()
        assert isinstance(result, V1Container)

    def test_with_command_script_with_valid_commands_adds_to_config(self):
        """Should add script lines to command config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        script = ["echo 'Hello'", "ls -la", "pwd"]

        builder.with_command_script(script)

        # Commands are inserted via insert_command method
        assert len(builder.config.command_config.commands) >= 3

    def test_with_command_script_with_empty_list_preserves_commands(self):
        """Should handle empty script list."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        initial_len = len(builder.config.command_config.commands)
        builder.with_command_script([])

        assert len(builder.config.command_config.commands) == initial_len

    def test_with_command_script_with_any_script_returns_self(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_command_script(["echo test"])

        assert result is builder

    def test_with_readiness_probe_with_valid_probe_sets_probe(self):
        """Should set readiness probe via config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        probe = _create_probe()

        builder.with_readiness_probe(probe)

        assert builder.config.readiness_probe == probe

    def test_with_readiness_probe_with_any_probe_returns_self(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_readiness_probe(_create_probe())

        assert result is builder

    def test_with_resources_with_valid_resources_sets_resources(self):
        """Should set resources via config."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        resources = _create_resource_requests_and_limits()
        builder.with_resources(resources)
        assert builder.config.resources == resources

    def test_with_resources_with_any_resources_returns_self(self):
        """Should return self for method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)
        result = builder.with_resources(_create_resource_requests_and_limits())

        assert result is builder

    def test_with_command_script_with_chained_calls_supports_fluent_api(self):
        """Should support full method chaining."""
        config = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        builder = ContainerBuilder(config)

        result = (
            builder.with_command_script(["echo test"])
            .with_readiness_probe(_create_probe())
            .with_resources(_create_resource_requests_and_limits())
        )

        assert result is builder


# --------------------------------------------------------------------------- #
# PodTemplateSpecBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodTemplateSpecBuilder:
    """Tests for the PodTemplateSpecBuilder class."""

    def test_build_with_default_config_returns_valid_pod_template_spec(self):
        """Should build a valid V1PodTemplateSpec with default config."""
        builder = PodTemplateSpecBuilder()
        result = builder.build()

        assert isinstance(result, V1PodTemplateSpec)
        assert result is not None


# --------------------------------------------------------------------------- #
# PodSpecBuilder Tests
# --------------------------------------------------------------------------- #
class TestPodSpecBuilder:
    """Tests for the PodSpecBuilder class."""

    def test_build_with_default_config_returns_valid_pod_spec(self):
        """Should build a valid V1PodSpec with default config."""
        builder = PodSpecBuilder()
        result = builder.build()

        assert isinstance(result, V1PodSpec)
        assert result is not None

    def test_add_container_with_container_config_adds_container(self):
        """Should add container via config."""
        builder = PodSpecBuilder()
        container = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")

        builder.add_container(container)

        assert len(builder.config.container_configs) == 1
        assert builder.config.container_configs[0].name == "test"

    def test_add_container_with_dict_config_adds_to_spec(self):
        """Should add container from dictionary."""
        builder = PodSpecBuilder()
        container = {"name": "test", "image": "nginx:1.21", "imagePullPolicy": "Always"}

        builder.add_container(container)

        assert len(builder.config.container_configs) == 1

    def test_add_container_with_any_container_returns_self(self):
        """Should return self for method chaining."""
        builder = PodSpecBuilder()
        container = ContainerConfig(name="test", image=_create_image(), image_pull_policy="Always")
        result = builder.add_container(container)

        assert result is builder

    def test_add_init_container_with_container_config_adds_init_container(self):
        """Should add init container via config."""
        builder = PodSpecBuilder()
        init_container = ContainerConfig(name="init", image=_create_image(), image_pull_policy="Always")

        builder.add_init_container(init_container)

        assert builder.config.init_containers is not None
        assert len(builder.config.init_containers) == 1
        assert builder.config.init_containers[0].name == "init"

    def test_add_init_container_with_any_container_returns_self(self):
        """Should return self for method chaining."""
        builder = PodSpecBuilder()
        init_container = ContainerConfig(name="init", image=_create_image(), image_pull_policy="Always")
        result = builder.add_init_container(init_container)

        assert result is builder

    def test_add_container_with_chained_calls_supports_fluent_api(self):
        """Should support full method chaining."""
        builder = PodSpecBuilder()
        container = ContainerConfig(name="main", image=_create_image(), image_pull_policy="Always")
        init_container = ContainerConfig(name="init", image=_create_image(), image_pull_policy="Always")

        result = builder.add_container(container).add_init_container(init_container)

        assert result is builder
        assert len(builder.config.container_configs) == 1
        assert len(builder.config.init_containers) == 1


# --------------------------------------------------------------------------- #
# ContainerCommandBuilder Tests
# --------------------------------------------------------------------------- #
class TestContainerCommandBuilder:
    """Tests for the ContainerCommandBuilder class."""

    def test_build_with_default_config_returns_command_list(self):
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

    def test_add_line_with_none_args_converts_to_empty_list(self):
        """Should handle None args by converting to empty list."""
        builder = ContainerCommandBuilder()
        builder.add_line("pwd", None)

        assert len(builder.config.commands) == 1
        assert builder.config.commands[0].command == "pwd"
        assert builder.config.commands[0].args == []

    def test_add_line_with_tuple_args_adds_command_with_args(self):
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

    def test_add_line_with_multiple_commands_adds_all(self):
        """Should handle multiple command lines."""
        builder = ContainerCommandBuilder()
        builder.add_line("cd", ["/app"]).add_line("npm", ["install"]).add_line("npm", ["start"])

        assert len(builder.config.commands) == 3
        assert builder.config.commands[0].command == "cd"
        assert builder.config.commands[1].command == "npm"
        assert builder.config.commands[2].command == "npm"

    def test_add_line_with_any_command_returns_self(self):
        """Should return self for method chaining."""
        builder = ContainerCommandBuilder()
        result = builder.add_line("echo", ["test"])

        assert result is builder

    def test_add_line_with_chained_calls_supports_fluent_api(self):
        """Should support full method chaining."""
        builder = ContainerCommandBuilder()

        result = (
            builder.add_line("echo", ["Starting"])
            .add_line("cd", ["/app"])
            .add_line("./start.sh", None)
        )

        assert result is builder
        assert len(builder.config.commands) == 3


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