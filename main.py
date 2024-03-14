# Python Imports
import socket
import six.moves.urllib.request as urllib_request
from kubernetes import client, config
from kubernetes.stream import portforward

# Project Imports
import src.logger.logger
from src.utils import file_utils
from src.plotting.plotter import Plotter
from src.metrics.scrapper import Scrapper

def portforward_commands(api_instance):
    # Monkey patch socket.create_connection which is used by http.client and urllib.request
    socket_create_connection = socket.create_connection

    def kubernetes_create_connection(address, *args, **kwargs):
        dns_name = address[0]
        if isinstance(dns_name, bytes):
            dns_name = dns_name.decode()
        dns_name = dns_name.split(".")
        if dns_name[-1] != 'kubernetes':
            return socket_create_connection(address, *args, **kwargs)
        if len(dns_name) not in (3, 4):
            raise RuntimeError("Unexpected kubernetes DNS name.")
        namespace = dns_name[-2]
        name = dns_name[0]
        port = address[1]
        if len(dns_name) == 4:
            if dns_name[1] in ('svc', 'service'):
                service = api_instance.read_namespaced_service(name, namespace)
                for service_port in service.spec.ports:
                    if service_port.port == port:
                        port = service_port.target_port
                        break
                else:
                    raise RuntimeError(
                        f"Unable to find service port: {port}")
                label_selector = []
                for key, value in service.spec.selector.items():
                    label_selector.append(f"{key}={value}")
                pods = api_instance.list_namespaced_pod(
                    namespace, label_selector=",".join(label_selector)
                )
                if not pods.items:
                    raise RuntimeError("Unable to find service pods.")
                name = pods.items[0].metadata.name
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
            elif dns_name[1] != 'pod':
                raise RuntimeError(
                    f"Unsupported resource type: {dns_name[1]}")
        pf = portforward(api_instance.connect_get_namespaced_pod_portforward,
                         name, namespace, ports=str(port))
        return pf.socket(port)
    socket.create_connection = kubernetes_create_connection

    response = urllib_request.urlopen(
        f'http://thanos-query-frontend.svc.thanos.kubernetes/api/v1')
    html = response.read().decode('utf-8')
    response.close()
    print(f'Status Code: {response.code}')
    print(html)


def main():
    config.load_kube_config("opal.yaml")
    url = "http://thanosquery.riff.cc:9090/api/v1/"
    scrape_config = "scrape.yaml"

    v1 = client.CoreV1Api()

    # scrapper = Scrapper(url, scrape_config, "test/")
    # scrapper.query_and_dump_metrics()

    # config_dict = file_utils.read_yaml_file("scrape.yaml")
    # plotter = Plotter(config_dict["plotting"])
    # plotter.create_plots()
    portforward_commands(v1)


if __name__ == '__main__':
    main()
