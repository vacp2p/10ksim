# Shadow GossipSub experiment.
#
# Runs N nim libp2p peers + 1 publisher host inside Shadow on a single k8s pod.
# Mirrors the smoke v3 we validated by hand: 1_gbit_switch network, peers form a
# mesh, the publisher POSTs publish commands at peer pod-N hostnames, receivers
# log timestamps.
#
# See "Shadow 10ksim Integration Plan" in Notion for the architecture.
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

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

# Repo root is six levels up from this file:
# src/deployments/experiments/libp2p/shadow_gossipsub.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]


class ExpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Sim shape
    num_nodes: NonNegativeInt = 10
    num_messages: NonNegativeInt = 5
    message_size_bytes: NonNegativeInt = 1000
    delay_seconds: NonNegativeFloat = 2.0
    connect_to: NonNegativeInt = 2
    # Timing (simulated seconds). Mesh formation under current test-node defaults
    # takes ~60s simulated; publisher starts comfortably after that.
    publisher_start_s: NonNegativeInt = 90
    sim_stop_time_s: NonNegativeInt = 180
    # storeMetrics scrape cadence (s). Short so the last scrape captures the
    # post-traffic bandwidth counter. Test node defaults to 300 (for k8s).
    metrics_interval_s: NonNegativeInt = 15
    # Job-pod resources. Defaults sized for ~10 peers; bump for bigger sims.
    cpu_request: str = "2"
    cpu_limit: str = "4"
    memory_request: str = "4Gi"
    memory_limit: str = "8Gi"
    # Images. Default to `:latest` but the experiment takes explicit tags so old
    # runs can be replayed against the image they were built against.
    test_node_image: str = "radiken/dst-test-node-shadow:latest"
    shadow_base_image: str = "radiken/dst-shadow-base:latest"
    # Where the runner Pod is pinned. Avoid node-01 (control plane).
    node_pin: Optional[str] = "node-05.ih-eu-mda1.misc.vaclab"
    # Run PVC: holds shadow.data/ so logs+metrics stay off pod stdout. ~200KB/peer,
    # so 5Gi covers well past 10k peers.
    pvc_storage: str = "5Gi"
    # Job poll
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
        # Use the output folder name so a single Multiple run's ConfigMap and Job
        # are distinguishable when scaling. Output folder names already include
        # a random suffix for uniqueness.
        run_id = self.output_folder.name.lower().replace("_", "-")[:50].strip("-")
        cm_name = f"shadow-{run_id}"
        job_name = f"shadow-{run_id}"
        pvc_name = f"shadow-{run_id}-data"

        # 1. Render shadow.yaml and build the k8s objects.
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

        # Dump for debugging / dry-run inspection.
        self.dump_yaml(pvc, f"pvc-{pvc_name}")
        self.dump_yaml(configmap, f"configmap-{cm_name}")
        self.dump_yaml(job, f"job-{job_name}")

        # 2. Apply PVC, then ConfigMap, then Job.
        # deploy_yaml expects a dict; sanitize the kubernetes-client objects first.
        pvc_dict = self.api_client.sanitize_for_serialization(pvc)
        cm_dict = self.api_client.sanitize_for_serialization(configmap)
        job_dict = self.api_client.sanitize_for_serialization(job)

        # PVC and ConfigMap have no rollout/ready state, so wait_for_ready=False.
        # PVC is deployed first so ExitStack cleanup (LIFO) deletes it last, after
        # the Job and its pod have released the claim.
        await self.deploy_yaml(deployment_yaml=pvc_dict, wait_for_ready=False)
        await self.deploy_yaml(deployment_yaml=cm_dict, wait_for_ready=False)
        # Job: BaseExperiment's wait_for_rollout doesn't handle Jobs, so we use
        # our own wait_for_job_complete below.
        await self.deploy_yaml(deployment_yaml=job_dict, wait_for_ready=False)

        if self.dry_run:
            self.log_event("dry_run_done")
            return

        # 3. Wait for Shadow to finish.
        self.log_event({"event": "wait_for_job", "job": job_name})
        state = await wait_for_job_complete(
            api_client=self.api_client,
            namespace=namespace,
            job_name=job_name,
            timeout_s=cfg.wait_timeout_s,
        )
        self.log_event({"event": "job_done", "state": state})

        # 4. Pull per-host logs before ExitStack cleanup deletes the pod.
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
            # Don't let a log-pull failure mask the underlying run state.
            logger.error(f"Failed to pull Shadow logs: {e}")
            self.log_event({"event": "logs_pull_failed", "error": str(e)})

        if state == "failed":
            raise RuntimeError(f"Shadow Job `{namespace}/{job_name}` failed")

        self.log_event("internal_run_finished")
