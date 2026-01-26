from dataclasses import dataclass
from typing import Optional

from core.configs.pod import PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig


@dataclass
class OvnConfig:
    """OVN configuration for bandwidth shaping and subnet attachment."""
    # Bandwidth shaping (in Mbps)
    ingress_rate: Optional[int] = None
    egress_rate: Optional[int] = None
    # Subnet attachment
    logical_switch: Optional[str] = None
    
    def to_annotations(self) -> dict:
        """Convert configuration to OVN annotations dict."""
        annotations = {}
        
        if self.ingress_rate is not None:
            annotations["ovn.kubernetes.io/ingress_rate"] = str(self.ingress_rate)
        if self.egress_rate is not None:
            annotations["ovn.kubernetes.io/egress_rate"] = str(self.egress_rate)
        if self.logical_switch is not None:
            annotations["ovn.kubernetes.io/logical_switch"] = self.logical_switch
        
        return annotations


def apply_ovn_pod_template(
    config: PodTemplateSpecConfig,
    ovn_config: OvnConfig,
):
    """Apply OVN annotations to PodTemplateSpecConfig."""
    for key, value in ovn_config.to_annotations().items():
        config.with_annotation(key, value, overwrite=True)


def apply_ovn_statefulset_spec(
    config: StatefulSetSpecConfig,
    ovn_config: OvnConfig,
):
    """Apply OVN annotations to StatefulSetSpecConfig."""
    apply_ovn_pod_template(config.pod_template_spec_config, ovn_config)


def apply_ovn_statefulset(
    config: StatefulSetConfig,
    ovn_config: OvnConfig,
):
    """Apply OVN annotations to StatefulSetConfig."""
    apply_ovn_statefulset_spec(config.stateful_set_spec, ovn_config)


#bandwidth configurations
def apply_bandwidth_limit(
    config: StatefulSetConfig | StatefulSetSpecConfig | PodTemplateSpecConfig,
    ingress_mbps: int,
    egress_mbps: Optional[int] = None,
):
    if egress_mbps is None:
        egress_mbps = ingress_mbps
    
    ovn_config = OvnConfig(ingress_rate=ingress_mbps, egress_rate=egress_mbps)
    
    if isinstance(config, StatefulSetConfig):
        apply_ovn_statefulset(config, ovn_config)
    elif isinstance(config, StatefulSetSpecConfig):
        apply_ovn_statefulset_spec(config, ovn_config)
    elif isinstance(config, PodTemplateSpecConfig):
        apply_ovn_pod_template(config, ovn_config)
    else:
        raise TypeError(f"Unsupported config type: {type(config)}")


def apply_logical_switch(
    config: StatefulSetConfig | StatefulSetSpecConfig | PodTemplateSpecConfig,
    logical_switch: str,
):
    ovn_config = OvnConfig(logical_switch=logical_switch)
    
    if isinstance(config, StatefulSetConfig):
        apply_ovn_statefulset(config, ovn_config)
    elif isinstance(config, StatefulSetSpecConfig):
        apply_ovn_statefulset_spec(config, ovn_config)
    elif isinstance(config, PodTemplateSpecConfig):
        apply_ovn_pod_template(config, ovn_config)
    else:
        raise TypeError(f"Unsupported config type: {type(config)}")
