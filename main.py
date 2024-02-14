# Python Imports
from kubernetes import client, config

# Project Imports

from src.metrics.scrapper import Scrapper


def main():
    config.load_kube_config("your_kubeconfig.yaml")
    url = "your_url"
    namespace = "'zerotesting'"
    metrics = ["container_network_receive_bytes_total", "container_network_sent_bytes_total"]

    v1 = client.CoreV1Api()

    scrapper = Scrapper(url, namespace, "test/", metrics)
    scrapper.query_and_dump_metrics()


if __name__ == '__main__':
    main()
