from typing import Any, Iterable, List, Optional

from pydantic import BaseModel

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment


def shallow_merge(a: BaseModel, b: BaseModel):
    data = {**a.model_dump(), **b.model_dump()}
    return a.__class__.model_validate(data)


@experiment(name="multi_nimlibp2p")
class MultiNimlibp2p(Multiple):

    def model_post_init(self, __context: Any) -> None:
        self.config.name = NimLibp2pExperiment.name
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run nimlibp2p multiple times with different parameters."
        )
        Multiple.add_args(subparser)
        BaseExperiment.add_args(subparser)

    def get_params_paths(self) -> Optional[dict]:
        """Return dict mapping keys to values.yaml paths"""
        return None

    def exp_params(self) -> Iterable[dict]:
        images = {
            "1.16.0": Image(
                repo="pearsonwhite/dst-nimlibp2p-logging",
                tag="wip-4.1-1.16.0",
            ),
            "2.0.0": Image(
                repo="soutullostatus/nimlibp2p",
                tag="v2.0.0",
            ),
             "1.16.0": Image(
                 repo="soutullostatus/nimlibp2p",
                 tag="v1.16.0",
             ),
             "1.15.0": Image(
                 repo="pearsonwhite/dst-nimlibp2p-logging",
                 tag="wip-5-v1.15.0",
             ),
        }
        base = {
            "delay_after_publish": 1,
            "start_sleep": 1 * 60,
            "message_size_bytes": 1000,  # 1kb
            "num_messages": 600,
            "num_nodes": 1000,
            "connect_to": 20
        }

        for version, image in images.items():
            for muxer in ["mplex", "yamux", "quic"]:
                yield {
                    **base,
                    "image": image,
                    "version": version,
                    "muxer": muxer,
                }

    def get_params_list(self) -> List[dict]:
        return [item for item in self.exp_params()]

    def get_name_from_params(self, params: dict) -> str:
        version = params["version"]
        keys = ["num_nodes", "num_messages", "muxer"]
        used_keys = filter(lambda item: item in keys, params.items())
        param_list = [f"{key}_{value}" for key, value in used_keys]
        param_list.append(f"version_{version}")
        return "__".join(param_list)
