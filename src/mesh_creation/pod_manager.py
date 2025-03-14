# Python Imports
import logging
import time
import yaml
from pathlib import Path
from typing import List, Dict, Optional

# Project Imports
from kubernetes import client, config
from kubernetes.stream import stream
from result import Result, Err, Ok
from src.mesh_creation.protocols.base_protocol import BaseProtocol
from src.mesh_creation.protocols.waku_protocol import WakuProtocol

logger = logging.getLogger("src.mesh_creation.pod_manager")


class PodManager:
    def __init__(self,
                 kube_config: str = "rubi3.yaml",
                 namespace: str = "zerotesting",
                 protocol: Optional[BaseProtocol] = None):
        self.namespace = namespace
        self.protocol = protocol or WakuProtocol()
        config.load_kube_config(config_file=kube_config)
        self.api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.deployed_pods = {}

    def execute_pod_command(self, pod_name: str, command: list, container_name: str) -> Result[str, None]:
        try:
            resp = stream(
                self.api.connect_get_namespaced_pod_exec,
                pod_name,
                self.namespace,
                container=container_name,
                command=command,
                stderr=True,
                stdin=True,
                stdout=True,
                tty=False
            )
            # If this is a curl command, try to extract only the JSON part
            if command[0] == "curl":
                try:
                    json_start = resp.find('{')
                    if json_start != -1:
                        return Ok(resp[json_start:])
                except Exception as e:
                    logger.debug(f"Failed to extract JSON from curl response: {str(e)}")
                    return Err(resp)
            return Ok(resp)
        except Exception as e:
            logger.error(f"Error executing command in pod {pod_name}: {str(e)}")
            return Err(None)

    def get_pod_identifier(self, pod_name: str, container_name: str) -> Result[str, None]:
        """Get the node identifier (ENR, peer ID, etc.) of a pod."""
        command = self.protocol.get_node_identifier()
        result = self.execute_pod_command(pod_name, command, container_name)
        if result.is_ok():
            return Ok(self.protocol.parse_identifier_response(result.ok_value))

        logger.error(f"Error getting identifier for pod {pod_name}")
        return Err(None)

    def connect_pods(self, source_pod: Dict[str, str], target_pod: Dict[str, str]) -> Result[None, None]:

        command = self.protocol.get_connection_command(target_pod["identifier"])
        result = self.execute_pod_command(
            source_pod["name"],
            command,
            self.deployed_pods['container_name']
        )
        if result.is_err():
            logger.error(f"Error connecting pods: {result.err_value}")
            return Err(None)

        logger.info(f"Connected pod {source_pod['name']} to {target_pod['name']}")
        return Ok(None)

    def configure_connections(self, node_to_pod: Dict[int, str], graph) -> Result:

        logger.info("Configuring pod connections based on topology")
        pod_lookup = {pod['name']: pod for pod in self.deployed_pods['pods']}

        for source_idx, target_idx in graph.edges():
            source_name = node_to_pod[source_idx]
            target_name = node_to_pod[target_idx]

            source_pod = pod_lookup.get(source_name)
            target_pod = pod_lookup.get(target_name)

            if not source_pod or not target_pod:
                logger.error(f"Could not find pods for nodes {source_idx} -> {target_idx} ({source_name} -> {target_name})")
                return Err(None)

            if not source_pod['identifier'] or not target_pod['identifier']:
                logger.error(f"Missing identifier for pod connection {source_name} -> {target_name}")
                return Err(None)

            logger.info(f"Establishing connection: {source_name} -> {target_name}")
            result = self.connect_pods(source_pod, target_pod)
            if result.is_err():
                return Err(result)

        logger.info("Successfully configured all pod connections")
        return Ok(None)

    def apply_yaml_file(self, yaml_path: Path) -> Result[None, str]:
        logger.info(f"Applying YAML file: {yaml_path}")

        with open(yaml_path, 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                if doc["kind"] != "StatefulSet":
                    # Only handled for StatefulSets
                    return Err(f"Yaml file is not a StatefulSet: {yaml_path}")

                ss_name = doc["metadata"]["name"]
                logger.info(f"Found StatefulSet: {ss_name}")

                # Extract container name from the StatefulSet spec
                try:
                    container_name = doc["spec"]["template"]["spec"]["containers"][0]["name"]
                    replicas = doc["spec"].get("replicas", 1)  # Default to 1 if not specified
                    logger.info(f"Found container name: {container_name} for StatefulSet {ss_name} with {replicas} replicas")
                except (KeyError, IndexError) as e:
                    logger.error(f"Failed to extract container name from StatefulSet {ss_name}: {str(e)}")
                    return Err(f"StatefulSet {ss_name} must specify a container name")

                try:
                    self.apps_api.create_namespaced_stateful_set(
                        namespace=self.namespace,
                        body=doc
                    )
                except client.exceptions.ApiException as e:
                    if e.status == 409: # Already exists
                        return Err(f"StatefulSet {ss_name} already exists")

                pods = [
                    {
                        "name": f"{ss_name}-{i}",
                        "identifier": ""  # Will be filled when pods are ready
                    }
                    for i in range(replicas)
                ]

                self.deployed_pods = {
                    'ss_name': ss_name,
                    'pods': pods,
                    'container_name': container_name
                }
                logger.debug(f"Successfully applied StatefulSet: {ss_name} with expected pods: {[p['name'] for p in pods]}")

        return Ok(None)

    def wait_for_pods_ready(self, timeout: int = 300) -> Result:
        """
        Wait for all pods in the managed StatefulSets to be ready and collect their identifiers.
        """
        start_time = time.time()
        ss_name = self.deployed_pods['ss_name']

        logger.info("Waiting for pods to be ready and collecting identifiers...")
        while time.time() - start_time < timeout:
            try:
                ss = self.apps_api.read_namespaced_stateful_set(
                    name=ss_name,
                    namespace=self.namespace
                )

                if not ss.status.ready_replicas or ss.status.ready_replicas != ss.spec.replicas:
                    logger.info(f"StatefulSet {ss_name} not ready: "
                                f"{ss.status.ready_replicas}/{ss.spec.replicas} replicas")
                    time.sleep(5)
                    continue

                selector = ss.spec.selector.match_labels
                selector_str = ",".join([f"{k}={v}" for k, v in selector.items()])
                logger.debug(f"Using selector: {selector_str} for StatefulSet {ss_name}")

                pods = self.api.list_namespaced_pod(
                    namespace=self.namespace,
                    label_selector=selector_str
                )

                if not pods.items:
                    logger.warning(f"No pods found for StatefulSet {ss_name} with selector {selector_str}")
                    break

                # Keep the existing pod list structure but update identifiers
                logger.info(f"Collecting identifiers for pods")
                for pod in pods.items:
                    pod_name = pod.metadata.name
                    for managed_pod in self.deployed_pods['pods']:
                        if managed_pod['name'] == pod_name:
                            logger.debug(f"Collecting identifier for pod: {pod_name}")
                            identifier = self.get_pod_identifier(
                                pod_name,
                                self.deployed_pods['container_name']
                            )
                            if identifier.is_err():
                                logger.debug(f"No identifier for pod: {pod_name}")
                                return Err(None)
                            managed_pod['identifier'] = identifier.ok_value
                logger.info("All pods are ready and identifiers collected!")
                return Ok(None)

            except client.exceptions.ApiException as e:
                error = f"Error checking StatefulSet {ss_name}: {str(e)}"
                logger.error(error)
                return Err(error)

        logger.error("Timeout waiting for pods to be ready")
        return Err(None)

    def get_all_pods(self) -> List[Dict[str, str]]:
        return [pod for ss_info in self.deployed_pods.values() for pod in ss_info['pods']]

    def get_pods_by_statefulset(self, statefulset_name: str) -> List[Dict[str, str]]:
        return self.deployed_pods.get(statefulset_name, {}).get('pods', [])
