# Python Imports
from kubernetes import client, config

# Project Imports
import src.logger.logger
from src.utils import file_utils
from src.plotting.plotter import Plotter
from src.metrics.scrapper import Scrapper


def main():
    config.load_kube_config("your_kubeconfig.yaml")
    url = "your_url"
    scrape_config = "scrape.yaml"

    v1 = client.CoreV1Api()

    # scrapper = Scrapper(url, scrape_config, "test/")
    # scrapper.query_and_dump_metrics()

    config_dict = file_utils.read_yaml_file("scrape.yaml")
    plotter = Plotter(config_dict["plotting"])
    plotter.create_plots()


if __name__ == '__main__':
    main()
