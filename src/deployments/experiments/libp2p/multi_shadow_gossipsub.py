# Drives shadow-gossipsub across scales and/or muxers via the Multiple meta-experiment.
# Defaults give the scale sweep; env vars turn it into the muxer regression matrix, e.g.
#   SHADOW_MUXERS=mplex,yamux,quic SHADOW_SIZES=1000 SHADOW_DISCOVERY=kad-dht \
#     uv run python deployment.py multi-shadow-gossipsub --values <base.yaml> --skip-check
# The base (message count, timing, image, resources) comes from --values; the runner
# only overlays the swept dimensions on top.
import os
from typing import Any, Iterable, List

from src.deployments.experiments.libp2p.shadow_gossipsub import ShadowGossipsubExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment


def _env_list(name: str, default: str) -> list:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


SIZES = [int(x) for x in _env_list("SHADOW_SIZES", "10,30,100")]
MUXERS = _env_list("SHADOW_MUXERS", "yamux")
DISCOVERY = os.environ.get("SHADOW_DISCOVERY", "static")


@experiment(name="multi-shadow-gossipsub")
class MultiShadowGossipsub(Multiple):
    """Run shadow-gossipsub across scales and/or muxers (see env vars above)."""

    def model_post_init(self, __context: Any) -> None:
        self.config.name = ShadowGossipsubExperiment.name
        self.config.delay = 60  # Shadow runs finish in seconds; no long inter-run wait
        super().model_post_init(__context)

    def get_params_list(self) -> List[dict]:
        return list(self.exp_params())

    def exp_params(self) -> Iterable[dict]:
        for size in SIZES:
            for muxer in MUXERS:
                yield {"num_nodes": size, "muxer": muxer, "discovery": DISCOVERY}

    def get_name_from_params(self, params: dict) -> str:
        return f"nodes_{params['num_nodes']}__muxer_{params['muxer']}__disc_{params['discovery']}"
