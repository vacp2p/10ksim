import logging
import random
from argparse import Namespace
from asyncio import sleep
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import List, Optional

from core.kube_utils import dict_get, dict_set
from experiments.base_experiment import BaseExperiment
from helm_deployment.nimlibp2p.experiments.mix.regression import NimMixNodes
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict
from registry import experiment
from ruamel import yaml

logger = logging.getLogger(__name__)


@experiment(name="nimlibp2p-multiple-mix")
class NimMultipleRegression(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run multiple nimlibp2p mix node tests.")
        BaseExperiment.add_args(subparser)

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        logger.info("Multiple nimlibp2p regression")
        network_params = get_batch()
        for params in network_params:
            this_time = datetime.now(dt_timezone.utc)
            logger.info(f"UTC time: {this_time.hour:02d}:{this_time.minute:02d}")

            delay = params["delay"]
            jitter = params["jitter"]
            messages = params["numMessages"]
            publishers = params["publishers"]
            mix_nodes = params.get("numMix", None)
            nonmix_nodes = params.get("numGossip", None)
            image = dict_get(values_yaml, "nimlibp2p.nodes.image.tag", sep=".")

            # Adding a random number helps distinguish experiments.
            random_number = random.randint(1, 200000)
            exp_workdir = (
                Path(workdir)
                / image
                / f"delay_{delay}_jitter_{jitter}_messages_{messages}_mix_{mix_nodes}_gossip_{nonmix_nodes}_rand_{random_number}"
            )
            exp_args = deepcopy(args)
            exp_args.workdir = exp_workdir
            exp_args.delay = None
            exp_values_yaml = deepcopy(values_yaml)
            dict_set(
                exp_values_yaml, "nimlibp2p.nodes.network.delay", delay, sep=".", replace_leaf=True
            )
            dict_set(
                exp_values_yaml,
                "nimlibp2p.nodes.network.jitter",
                jitter,
                sep=".",
                replace_leaf=True,
            )
            dict_set(
                exp_values_yaml,
                "nimlibp2p.nodes.env.vars.messages",
                messages,
                sep=".",
                replace_leaf=True,
            )
            dict_set(
                exp_values_yaml,
                "nimlibp2p.nodes.env.vars.publishers",
                publishers,
                sep=".",
                replace_leaf=True,
            )

            max_connections = params.get("maxConnections", None)
            if max_connections is not None:
                dict_set(
                    exp_values_yaml,
                    "nimlibp2p.nodes.env.vars.MAXCONNECTIONS",
                    max_connections,
                    sep=".",
                    replace_leaf=True,
                )

            msgRate = params.get("msgRate", None)
            if msgRate is not None:
                dict_set(
                    exp_values_yaml,
                    "nimlibp2p.nodes.env.vars.msgRate",
                    msgRate,
                    sep=".",
                    replace_leaf=True,
                )

            if mix_nodes is not None:
                dict_set(
                    exp_values_yaml, "nimlibp2p.nodes.numMix", mix_nodes, sep=".", replace_leaf=True
                )
            if nonmix_nodes is not None:
                dict_set(
                    exp_values_yaml,
                    "nimlibp2p.nodes.numGossip",
                    nonmix_nodes,
                    sep=".",
                    replace_leaf=True,
                )

            experiment = NimMixNodes()
            logger.info(f"running wtih delay {delay} jitter {jitter}")
            experiment.run(api_client, exp_args, exp_values_yaml)

            logger.info("sleep 100")
            await sleep(100)
            logger.info("loop")


def get_batch() -> List[dict]:
    # Example batch of experiments to run.
    # Modify for your own purposes.
    batch = []
    common = {
        "msgRate": 1000,
        "delay": 0,
        "jitter": 0,
        "numMix": 5,
        "numGossip": 15,
        "publishers": 5,
    }
    updates = [
        {"msgRate": 500, "numMessages": 2, "maxConnections": 50},
        {"msgRate": 500, "numMessages": 2, "maxConnections": 25},
        {"msgRate": 500, "numMessages": 2, "maxConnections": 25},
        {"msgRate": 500, "numMessages": 2, "maxConnections": 25},
    ]
    for update_dict in updates:
        params = deepcopy(common)
        params.update(update_dict)
        batch.append(params)
    logger.info(f"batch ({len(batch)}): {batch}")
    return batch
