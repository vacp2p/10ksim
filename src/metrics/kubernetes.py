# Python Imports
import socket
import logging
import kubernetes
import multiprocessing
from typing import List, Tuple
from kubernetes.client import V1PodList, V1Service
from kubernetes.stream import portforward

from src.utils import path

logger = logging.getLogger(__name__)


class KubernetesManager:
    def __init__(self, kube_config: str):
        self._kube_config = kube_config
        self._kube_client = kubernetes.config.new_client_from_config(self._kube_config)
        self._api = kubernetes.client.CoreV1Api(self._kube_client)

    def create_connection(self, address, *args, **kwargs) -> socket.socket:
        dns_name = self._get_dns_name(address)
        if dns_name[-1] != 'kubernetes':
            logger.warning(f'Not a kubernetes DNS name: {dns_name}')
            return socket.create_connection(address, *args, **kwargs)

        namespace, name = self._split_dns(dns_name)
        port = address[1]

        if len(dns_name) == 4:
            name, port = self._find_pod_in_service(dns_name, name, namespace, port)

        logger.info(f'Forwarding port {port} from pod {name} in namespace {namespace}')
        pf = portforward(self._api.connect_get_namespaced_pod_portforward,
                         name, namespace, ports=str(port))

        return pf.socket(port)

    @staticmethod
    def download_logs_from_pod_asyncable(kube_config: str, namespace: str, pod_name: str,
                                         location: str):
        kube_client = kubernetes.config.new_client_from_config(kube_config)
        api = kubernetes.client.CoreV1Api(kube_client)

        logs = api.read_namespaced_pod_log(pod_name, namespace=namespace)

        path_location_result = path.prepare_path(location + pod_name + ".log")

        if path_location_result.is_ok():
            with open(f"{path_location_result.ok_value}", "w") as log_file:
                log_file.write(logs)
            logger.debug(f"Logs from pod {pod_name} downloaded successfully.")
        else:
            logger.error(
                f"Unable to download logs from pod {pod_name}. Error: {path_location_result.err}")

    def download_pod_logs(self, namespace: str, location: str):
        logger.info(f"Downloading logs from namespace '{namespace}' to {location}")
        pods = self._api.list_namespaced_pod(namespace)

        pool = multiprocessing.Pool()

        for pod in pods.items:
            pod_name = pod.metadata.name
            pool.apply_async(KubernetesManager.download_logs_from_pod_asyncable,
                             args=(self._kube_config, namespace, pod_name, location))

        pool.close()
        pool.join()
        logger.info("Logs downloaded successfully.")

    def _get_dns_name(self, address: List) -> List:
        dns_name = address[0]
        if isinstance(dns_name, bytes):
            dns_name = dns_name.decode()
        dns_name = dns_name.split(".")

        return dns_name

    def _split_dns(self, dns_name: List) -> Tuple[str, str]:
        if len(dns_name) not in (3, 4):
            raise RuntimeError("Unexpected kubernetes DNS name.")
        namespace = dns_name[-2]
        name = dns_name[0]

        return namespace, name

    def _find_service_target_port(self, service: V1Service, port: int) -> str:
        for service_port in service.spec.ports:
            if service_port.port == port:
                return service_port.target_port
        else:
            raise RuntimeError(
                f"Unable to find service port: {port}")

    def _get_pods_and_name(self, service: V1Service, namespace: str) -> Tuple[V1PodList, str]:
        label_selector = []
        for key, value in service.spec.selector.items():
            label_selector.append(f"{key}={value}")
        pods = self._api.list_namespaced_pod(
            namespace, label_selector=",".join(label_selector)
        )
        if not pods.items:
            raise RuntimeError("Unable to find service pods.")
        name = pods.items[0].metadata.name

        return pods, name

    def _find_service_port_name_in_pods(self, port: str, pods: V1PodList) -> int:
        for container in pods.items[0].spec.containers:
            for container_port in container.ports:
                if container_port.name == port:
                    return container_port.container_port
        else:
            raise RuntimeError(
                f"Unable to find service port name: {port}")

    def _find_pod_in_service(self, dns_name, name, namespace, port) -> Tuple[str, int]:
        if dns_name[1] in ('svc', 'service'):
            service = self._api.read_namespaced_service(name, namespace)
            port = self._find_service_target_port(service, port)
            pods, name = self._get_pods_and_name(service, namespace)
            port = self._find_service_port_name_in_pods(port, pods)

            return name, port
        elif dns_name[1] != 'pod':
            raise RuntimeError(
                f"Unsupported resource type: {dns_name[1]}")
