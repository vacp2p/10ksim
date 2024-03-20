# Python Imports
import socket
import logging
from kubernetes.client import CoreV1Api
from kubernetes.stream import portforward


logger = logging.getLogger(__name__)


class KubernetesManager:
    def __init__(self, api: CoreV1Api):
        self._api = api

    def create_connection(self, address, *args, **kwargs):
        dns_name = self._get_dns_name(address)
        if dns_name[-1] != 'kubernetes':
            logger.warning(f'Not a kubernetes DNS name: {dns_name}')
            return socket.create_connection(address, *args, **kwargs)

        namespace, name = self._split_dns(dns_name)
        port = address[1]

        if len(dns_name) == 4:
            name, port = self._find_pod_port_in_service(dns_name, name, namespace, port)

        pf = portforward(self._api.connect_get_namespaced_pod_portforward,
                         name, namespace, ports=str(port))

        return pf.socket(port)

    def _get_dns_name(self, address):
        dns_name = address[0]
        if isinstance(dns_name, bytes):
            dns_name = dns_name.decode()
        dns_name = dns_name.split(".")

        return dns_name

    def _split_dns(self, dns_name):
        if len(dns_name) not in (3, 4):
            raise RuntimeError("Unexpected kubernetes DNS name.")
        namespace = dns_name[-2]
        name = dns_name[0]

        return namespace, name

    def _find_service_target_port(self, service, port):
        for service_port in service.spec.ports:
            if service_port.port == port:
                return service_port.target_port
        else:
            raise RuntimeError(
                f"Unable to find service port: {port}")

    def _get_pods_and_name(self, service, namespace):
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

    def _find_service_port_name_in_pods(self, port, pods):
        if isinstance(port, str):
            for container in pods.items[0].spec.containers:
                for container_port in container.ports:
                    if container_port.name == port:
                        port = container_port.container_port
                        break
                else:
                    continue
                break
            else:
                raise RuntimeError(
                    f"Unable to find service port name: {port}")

        return port

    def _find_pod_port_in_service(self, dns_name, name, namespace, port):
        if dns_name[1] in ('svc', 'service'):
            service = self._api.read_namespaced_service(name, namespace)
            port = self._find_service_target_port(service, port)
            pods, name = self._get_pods_and_name(service, namespace)
            port = self._find_service_port_name_in_pods(port, pods)

            return name, port
        elif dns_name[1] != 'pod':
            raise RuntimeError(
                f"Unsupported resource type: {dns_name[1]}")
