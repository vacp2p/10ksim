from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig

def network_delay_init_container(
    delay_ms: int = 100,
    jitter_ms: int = 30,
    distribution: str = "normal",
) -> dict:
    """
    Create init container (adds network delay using tc).
    :param delay_ms: Base delay in milliseconds
    :param jitter_ms: Jitter/variation in milliseconds
    :param distribution: Distribution types
    """
    command = (
        f"tc qdisc add dev eth0 root netem delay {delay_ms}ms {jitter_ms}ms "
        f"distribution {distribution}"
    )

    return {
        "name": "slowyourroll",
        "image": "soutullostatus/tc-container:1",
        "imagePullPolicy": "IfNotPresent",
        "securityContext": {
            "capabilities": {
                "add": ["NET_ADMIN"],
            },
        },
        "command": ["sh", "-c", command],
    }

def apply_network_delay_pod_spec(
    config: PodSpecConfig,
    delay_ms: int = 100,
    jitter_ms: int = 30,
    distribution: str = "normal",
):
    config.add_init_container(
        network_delay_init_container(delay_ms, jitter_ms, distribution)
    )

def apply_network_delay_pod_template(
    config: PodTemplateSpecConfig,
    delay_ms: int = 100,
    jitter_ms: int = 30,
    distribution: str = "normal",
):
    apply_network_delay_pod_spec(
        config.pod_spec_config, delay_ms, jitter_ms, distribution
    )

def apply_network_delay_statefulset_spec(
    config: StatefulSetSpecConfig,
    delay_ms: int = 100,
    jitter_ms: int = 30,
    distribution: str = "normal",
):
    apply_network_delay_pod_template(
        config.pod_template_spec_config, delay_ms, jitter_ms, distribution
    )

def apply_network_delay_statefulset(
    config: StatefulSetConfig,
    delay_ms: int = 100,
    jitter_ms: int = 30,
    distribution: str = "normal",
):
    apply_network_delay_statefulset_spec(
        config.stateful_set_spec, delay_ms, jitter_ms, distribution
    )
