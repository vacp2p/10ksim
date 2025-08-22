import json
import logging
import os
import time
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from deployment.base_experiment import BaseExperiment
from deployment.builders import build_deployment
from kube_utils import (
    assert_equals,
    dict_set,
    get_cleanup,
    get_flag_value,
    kubectl_apply,
    wait_for_rollout,
)
from registry import experiment

logger = logging.getLogger(__name__)


@experiment(name="waku-regression-nodes")
class WakuRegressionNodes(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    release_name: str = Field(default="waku-regression-nodes")

    deployment_dir: str = Field(default=Path(os.path.dirname(__file__)).parent.parent)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(cls.name, help="Run a regression_nodes test using waku.")
        BaseExperiment.add_args(subparser)

    def _build(
        self,
        workdir: str,
        values_yaml: Optional[yaml.YAMLObject],
        service: str,
    ) -> yaml.YAMLObject:
        this_dir = Path(os.path.dirname(__file__))

        return build_deployment(
            deployment_dir=self.deployment_dir / service,
            workdir=os.path.join(workdir, service),
            cli_values=values_yaml,
            name="waku-regression-nodes",
            extra_values_names=[],
            extra_values_paths=[this_dir / f"{service}.values.yaml"],
        )

    def _preprocess_event(self, event: Any) -> Any:
        if isinstance(event, str):
            event = {"event": event}
        return super()._preprocess_event(event)

    def _metadata_event(self):
        metadata = {}
        events_dict = {
            "wait_for_clear_finished": ("complete.start", timedelta(seconds=0)),
            "internal_run_finished": ("complete.end", timedelta(seconds=30)),
            "publisher_deploy_start": ("stable.start", timedelta(minutes=3)),
            "publisher_messages_finished": ("stable.end", timedelta(seconds=-30)),
        }
        with open(self.events_log_path, "r") as events:
            for line in events:
                event = json.loads(line)
                for key, (path, offset) in events_dict.items():
                    try:
                        dt = datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
                        if event["event"] == key:
                            dict_set(
                                metadata,
                                path,
                                (dt, offset),
                                sep=".",
                            )
                    except KeyError:
                        pass

        # Apply time offsets unless the interval would not make sense if we did.
        for interval_type, interval in metadata.items():
            start_dt = interval["start"][0] + interval["start"][1]
            end_dt = interval["end"][0] + interval["end"][1]
            if end_dt <= start_dt:
                start_dt = interval["start"][0]
                end_dt = interval["end"][0]
            start_formatted = start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            interval["start"] = start_formatted
            end_formatted = end_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            interval["end"] = end_formatted

        # Add links.
        links = {
            "grafana": "https://grafana.vaclab.org/d/jIrqsZTIz/nwaku?orgId=1&from={start}&to={end}&timezone=utc",
            "victoria": "https://vlselect.vaclab.org/select/vmui/?#/?query=*&g0.start_input={start}&g0.end_input={end}&g0.relative_time=none",
        }
        for interval_type in metadata.keys():
            try:
                for link_type, base in links.items():
                    metadata[interval_type][link_type] = base.format(
                        start=metadata[interval_type]["start"], end=metadata[interval_type]["end"]
                    )
            except KeyError:
                pass
        self.log_event(metadata)

    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        # TODO [values param checking]: Add friendly error messages for missing/extraneous variables in values.yaml.
        logger.info("Building kubernetes configs.")
        nodes = self._build(workdir, values_yaml, "nodes")
        bootstrap = self._build(workdir, values_yaml, "bootstrap")
        publisher = self._build(workdir, values_yaml, "publisher")

        # Sanity check
        namespace = bootstrap["metadata"]["namespace"]
        logger.info(f"namespace={namespace}")
        assert_equals(nodes["metadata"]["namespace"], namespace)
        assert_equals(publisher["metadata"]["namespace"], namespace)

        # TODO [metadata output]: log start time to output file here.
        logger.info("Applying kubernetes configs.")

        cleanup = get_cleanup(
            api_client=api_client,
            namespace=namespace,
            deployments=[bootstrap, nodes, publisher],
        )
        stack.callback(cleanup)

        self._wait_until_clear(
            api_client=api_client,
            namespace=namespace,
            skip_check=args.skip_check,
        )

        self.log_event("deployments_start")

        # Apply bootstrap
        logger.info("Applying bootstrap")
        kubectl_apply(bootstrap, namespace=namespace)
        logger.info("bootstrap applied. Waiting for rollout.")
        wait_for_rollout(bootstrap["kind"], bootstrap["metadata"]["name"], namespace, 2000)

        num_nodes = nodes["spec"]["replicas"]
        messages = get_flag_value("messages", publisher["spec"]["containers"][0]["command"])
        delay_seconds = get_flag_value(
            "delay-seconds", publisher["spec"]["containers"][0]["command"]
        )

        # Apply nodes configuration
        logger.info("Applying nodes")
        kubectl_apply(nodes, namespace=namespace)
        logger.info("nodes applied. Waiting for rollout.")
        timeout = num_nodes * 3000
        wait_for_rollout(nodes["kind"], nodes["metadata"]["name"], namespace, timeout)

        self.log_event("nodes_deploy_finished")
        logger.info("nodes rolled out. wait to stablize")
        time.sleep(60)
        self.log_event("publisher_deploy_start")
        logger.info("delay over")

        # TODO [metadata output]: log publish message start time
        # Apply publisher configuration
        logger.info("applying publisher")
        kubectl_apply(publisher, namespace=namespace)
        logger.info("publisher applied. Waiting for rollout.")
        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            20,
            api_client,
            ("Ready", "True"),
            # TODO [extend condition checks] lambda cond : cond.type == "Ready" and cond.status == "True"
        )
        self.log_event("publisher_deploy_finished")
        logger.info("publisher rollout done.")

        logger.info("---publisher is up. begin messages")

        timeout = num_nodes * messages * delay_seconds * 120
        logger.info(f"Waiting for Ready=False. Timeout: {timeout}")

        wait_for_rollout(
            publisher["kind"],
            publisher["metadata"]["name"],
            namespace,
            timeout,
            api_client,
            ("Ready", "False"),
        )
        # TODO: consider state.reason == .completed
        logger.info("---publisher messages finished. wait 20 seconds")
        self.log_event("publisher_messages_finished")
        time.sleep(20)
        self.log_event("publisher_wait_finished")
        logger.info("---20seconds is over.")
        # TODO [metadata output]: log publish message end time

        logger.info("Finished waku regression test.")
        self.log_event("internal_run_finished")
        self._metadata_event()
