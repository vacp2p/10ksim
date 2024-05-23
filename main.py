# Python Imports

# Project Imports
import src.logger.logger
from src.metrics.scrapper import Scrapper


def main():
    config.load_kube_config("opal.yaml")
    url = "http://thanos-query.svc.thanos.kubernetes:9090/api/v1/"
    scrape_config = "scrape.yaml"

    v1 = client.CoreV1Api()

    scrapper = Scrapper(v1, url, scrape_config, "test/")
    scrapper.query_and_dump_metrics()

    # config_dict = file_utils.read_yaml_file("scrape.yaml")
    # plotter = Plotter(config_dict["plotting"])
    # plotter.create_plots()
    # portforward_commands(v1)


if __name__ == '__main__':
    main()
