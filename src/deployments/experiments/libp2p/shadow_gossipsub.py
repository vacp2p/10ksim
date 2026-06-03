# Shadow GossipSub experiment: N nim libp2p peers + 1 publisher inside Shadow on a
# single k8s pod. See the "Using Shadow at DST" runbook in Notion.
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.analysis.metrics.shadow_metrics import scrape_run_metrics
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.registry import experiment
from src.deployments.shadow.builders import (
    TRAFFIC_SYNC_REPO_PATH,
    build_configmap,
    build_pvc,
    build_shadow_job,
    render_shadow_yaml,
)
from src.deployments.shadow.runtime import pull_shadow_logs, wait_for_job_complete

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Sim shape
    num_nodes: NonNegativeInt = 10
    num_messages: NonNegativeInt = 5
    message_size_bytes: NonNegativeInt = 1000
    delay_seconds: NonNegativeFloat = 2.0
    connect_to: NonNegativeInt = 2
    # Timing (simulated seconds). Publisher starts after the mesh forms (~60s).
    publisher_start_s: NonNegativeInt = 90
    sim_stop_time_s: NonNegativeInt = 180
    # storeMetrics scrape cadence (s); short so the last scrape is post-traffic.
    metrics_interval_s: NonNegativeInt = 15
    # Job-pod resources, sized for ~10 peers; bump for bigger sims.
    cpu_request: str = "2"
    cpu_limit: str = "4"
    memory_request: str = "4Gi"
    memory_limit: str = "8Gi"
    # Images (explicit tags let old runs be replayed).
    test_node_image: str = "radiken/dst-test-node-shadow:latest"
    shadow_base_image: str = "radiken/dst-shadow-base:latest"
    node_pin: Optional[str] = "node-05.ih-eu-mda1.misc.vaclab"  # avoid node-01 (control plane)
    pvc_storage: str = "5Gi"  # run PVC for shadow.data/ (~200KB/peer)
    wait_timeout_s: NonNegativeInt = 1800


@experiment(name="shadow-gossipsub")
class ShadowGossipsubExperiment(BaseExperiment[ExpConfig]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run a GossipSub mesh + publisher inside the Shadow simulator."
        )
        BaseExperiment.add_args(subparser)
        subparser.set_defaults(namespace="zerotesting-shadow")

    async def _run(self):
        self.log_event("run_start")
        cfg = self.config
        namespace = self.namespace
        # unique per run (output folder name carries a random suffix)
        run_id = self.output_folder.name.lower().replace("_", "-")[:50].strip("-")
        cm_name = f"shadow-{run_id}"
        job_name = f"shadow-{run_id}"
        pvc_name = f"shadow-{run_id}-data"

        shadow_yaml = render_shadow_yaml(
            num_nodes=cfg.num_nodes,
            num_messages=cfg.num_messages,
            msg_size_bytes=cfg.message_size_bytes,
            delay_seconds=cfg.delay_seconds,
            sim_stop_time_s=cfg.sim_stop_time_s,
            publisher_start_s=cfg.publisher_start_s,
            connect_to=cfg.connect_to,
            metrics_interval_s=cfg.metrics_interval_s,
        )
        traffic_sync_path = _REPO_ROOT / TRAFFIC_SYNC_REPO_PATH
        if not traffic_sync_path.exists():
            raise FileNotFoundError(
                f"traffic_sync.py not found at expected path: {traffic_sync_path}"
            )

        pvc = build_pvc(namespace=namespace, name=pvc_name, storage=cfg.pvc_storage)
        configmap = build_configmap(
            namespace=namespace,
            name=cm_name,
            shadow_yaml=shadow_yaml,
            traffic_sync_path=traffic_sync_path,
        )
        job = build_shadow_job(
            namespace=namespace,
            name=job_name,
            configmap_name=cm_name,
            pvc_name=pvc_name,
            test_node_image=cfg.test_node_image,
            shadow_base_image=cfg.shadow_base_image,
            node_pin=cfg.node_pin,
            cpu_request=cfg.cpu_request,
            cpu_limit=cfg.cpu_limit,
            memory_request=cfg.memory_request,
            memory_limit=cfg.memory_limit,
        )

        self.dump_yaml(pvc, f"pvc-{pvc_name}")
        self.dump_yaml(configmap, f"configmap-{cm_name}")
        self.dump_yaml(job, f"job-{job_name}")

        # PVC first so LIFO cleanup deletes it last, after the Job releases it.
        pvc_dict = self.api_client.sanitize_for_serialization(pvc)
        cm_dict = self.api_client.sanitize_for_serialization(configmap)
        job_dict = self.api_client.sanitize_for_serialization(job)

        await self.deploy_yaml(deployment_yaml=pvc_dict, wait_for_ready=False)
        await self.deploy_yaml(deployment_yaml=cm_dict, wait_for_ready=False)
        # Jobs aren't handled by wait_for_rollout; we poll with wait_for_job_complete.
        await self.deploy_yaml(deployment_yaml=job_dict, wait_for_ready=False)

        if self.dry_run:
            self.log_event("dry_run_done")
            return

        self.log_event({"event": "wait_for_job", "job": job_name})
        state = await wait_for_job_complete(
            api_client=self.api_client,
            namespace=namespace,
            job_name=job_name,
            timeout_s=cfg.wait_timeout_s,
        )
        self.log_event({"event": "job_done", "state": state})

        # Pull output before cleanup deletes the pod.
        logs_dir = self.output_folder / "shadow_logs"
        try:
            pull_shadow_logs(
                api_client=self.api_client,
                namespace=namespace,
                job_name=job_name,
                pvc_name=pvc_name,
                reader_image=cfg.shadow_base_image,
                dest_dir=logs_dir,
                node_pin=cfg.node_pin,
            )
            self.log_event({"event": "logs_pulled", "dest": str(logs_dir)})
        except Exception as e:
            # don't let a log-pull failure mask the run state
            logger.error(f"Failed to pull Shadow logs: {e}")
            self.log_event({"event": "logs_pull_failed", "error": str(e)})

        if state == "failed":
            raise RuntimeError(f"Shadow Job `{namespace}/{job_name}` failed")

        self._run_analysis()
        self.log_event("internal_run_finished")

    def _run_analysis(self) -> None:
        """Post-run analysis (best-effort; never fails the run): bandwidth CSVs via the
        ephemeral-VM metrics path + message reliability from the flattened logs."""
        cfg = self.config
        run_dir = self.output_folder
        try:
            scrape_run_metrics(
                run_dir=run_dir, namespace=self.namespace, interval_s=cfg.metrics_interval_s
            )
        except Exception as e:
            logger.error(f"Shadow metrics analysis failed: {e}")
        try:
            puller = DataPuller().with_local(run_dir / "shadow_logs" / "logs")
            (
                Nimlibp2pAnalyzer(dump_analysis_dir=str(run_dir / "analysis_data"))
                .with_data_puller(puller)
                .with_ss_check(["pod"], [cfg.num_nodes])
                .with_reliability_check(
                    stateful_sets=["pod"],
                    nodes_per_ss=[cfg.num_nodes],
                    expected_num_peers=cfg.num_nodes,
                    expected_num_messages=cfg.num_messages,
                )
                .run()
            )
        except Exception as e:
            logger.error(f"Shadow message analysis failed: {e}")
