# Python Imports
import src.logging.logger
from kubernetes import client, config

# Project Imports
from src.metrics.scrapper import Scrapper


def main():
    config.load_kube_config("your_kubeconfig.yaml")
    url = "your_url"
    scrape_config = "scrape.yaml"

    v1 = client.CoreV1Api()

    scrapper = Scrapper(url, scrape_config, "test/")
    scrapper.query_and_dump_metrics()


if __name__ == '__main__':
    main()
