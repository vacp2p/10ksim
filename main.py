# Python Imports
import src.logging.logger
from kubernetes import client, config

# Project Imports
from src.metrics.scrapper import Scrapper


def main():
    namespace = "'zerotesting'"
    metrics = ["container_network_receive_bytes_total", "container_network_transmit_bytes_total"]
    scrape_config = "scrape.yaml"

    v1 = client.CoreV1Api()

    scrapper = Scrapper(url, scrape_config, "test/")
    scrapper.query_and_dump_metrics()


if __name__ == '__main__':
    main()
