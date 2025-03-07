# Python Imports
import logging
import time
import yaml
from pathlib import Path
from typing import List, Dict, Optional

# Project Imports
from kubernetes import client, config, utils
from kubernetes.stream import stream
from src.mesh_creation.protocols.base_protocol import BaseProtocol
from src.mesh_creation.protocols.waku_protocol import WakuProtocol

logger = logging.getLogger(__name__)


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
        # Store pod information: {statefulset_name: [{name: pod_name, identifier: node_id}]}
        self.deployed_pods = {}

    def execute_pod_command(self, pod_name: str, command: list, container_name: str) -> str:
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
                        return resp[json_start:]
                except Exception as e:
                    logger.debug(f"Failed to extract JSON from curl response: {str(e)}")
                    return resp
            return resp
        except Exception as e:
            logger.error(f"Error executing command in pod {pod_name}: {str(e)}")
            raise

    def get_pod_identifier(self, pod_name: str) -> str:
        """Get the node identifier (ENR, peer ID, etc.) of a pod."""
        try:
            command = self.protocol.get_node_identifier()
            response = self.execute_pod_command(pod_name, command)
            return self.protocol.parse_identifier_response(response)
        except Exception as e:
            logger.error(f"Error getting identifier for pod {pod_name}: {str(e)}")
            return ""

    def connect_pods(self, source_pod: Dict[str, str], target_pod: Dict[str, str]) -> bool:
        """Connect one pod to another using the configured protocol."""
        try:
            command = self.protocol.get_connection_command(target_pod["identifier"])
            self.execute_pod_command(source_pod["name"], command)
            logger.info(f"Connected pod {source_pod['name']} to {target_pod['name']}")
            return True
        except Exception as e:
            logger.error(f"Error connecting pods: {str(e)}")
            return False

    def apply_yaml_files(self, yaml_paths: List[str]) -> None:
        for yaml_path in yaml_paths:
            self.apply_yaml_file(yaml_path)

    def apply_yaml_file(self, yaml_path: str) -> None:
        logger.info(f"Applying YAML file: {yaml_path}")

        with open(yaml_path, 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                if doc["kind"] == "StatefulSet":
                    name = doc["metadata"]["name"]
                    logger.info(f"Found StatefulSet: {name}")

                    try:
                        # Check if StatefulSet already exists
                        existing_ss = self.apps_api.read_namespaced_stateful_set(
                            name=name,
                            namespace=self.namespace
                        )

                        # If it exists, patch it
                        logger.info(f"StatefulSet {name} exists, updating it")
                        self.apps_api.patch_namespaced_stateful_set(
                            name=name,
                            namespace=self.namespace,
                            body=doc
                        )
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            # If it doesn't exist, create it
                            logger.info(f"Creating new StatefulSet: {name}")
                            self.apps_api.create_namespaced_stateful_set(
                                namespace=self.namespace,
                                body=doc
                            )
                        else:
                            raise

                    self.deployed_pods[name] = []
                    logger.info(f"Successfully applied StatefulSet: {name}")
                else:
                    # For other kinds of resources (Services, ConfigMaps, etc.)
                    logger.info(f"Applying {doc['kind']}: {doc['metadata']['name']}")
                    utils.create_from_dict(
                        k8s_client=client,
                        data=doc,
                        namespace=self.namespace
                    )

    def wait_for_pods_ready(self, timeout: int = 300) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            all_ready = True
            statefulsets = self.apps_api.list_namespaced_stateful_set(self.namespace)

            for ss in statefulsets.items:
                if ss.metadata.name in self.deployed_pods:
                    if not ss.status.ready_replicas or ss.status.ready_replicas != ss.spec.replicas:
                        logger.info(
                            f"StatefulSet {ss.metadata.name} not ready: {ss.status.ready_replicas}/{ss.spec.replicas} replicas")
                        all_ready = False
                        break

                    selector = ss.spec.selector.match_labels
                    selector_str = ",".join([f"{k}={v}" for k, v in selector.items()])
                    logger.debug(f"Using selector: {selector_str} for StatefulSet {ss.metadata.name}")

                    pods = self.api.list_namespaced_pod(
                        namespace=self.namespace,
                        label_selector=selector_str
                    )

                    if not pods.items:
                        logger.warning(f"No pods found for StatefulSet {ss.metadata.name} with selector {selector_str}")
                        all_ready = False
                        break

                    self.deployed_pods[ss.metadata.name] = []

                    for pod in pods.items:
                        pod_name = pod.metadata.name
                        logger.info(f"Found pod: {pod_name} for StatefulSet {ss.metadata.name}")
                        identifier = self.get_pod_identifier(pod_name)
                        if not identifier:
                            all_ready = False
                            break

                        self.deployed_pods[ss.metadata.name].append({
                            "name": pod_name,
                            "identifier": identifier
                        })

            if all_ready:
                logger.info("All pods are ready and identifiers collected!")
                return True

            logger.info("Waiting for pods to be ready and collecting identifiers...")
            time.sleep(5)

        logger.error("Timeout waiting for pods to be ready")
        return False

    def get_all_pods(self) -> List[Dict[str, str]]:
        return [pod for pods in self.deployed_pods.values() for pod in pods]

    def get_pods_by_statefulset(self, statefulset_name: str) -> List[Dict[str, str]]:
        return self.deployed_pods.get(statefulset_name, [])
