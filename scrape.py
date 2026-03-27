# Python Imports

# Project Imports
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.metrics_plotter import MetricsPlotter
from src.analysis.utils import file_utils


def main():
    url = "https://metrics.vaclab.org/select/0/prometheus/api/v1/"
    scrape_config = "scrape.yaml"

    scrapper = Scrapper("rubi.yaml", url, scrape_config)
    scrapper.query_and_dump_metrics()

    config_dict = file_utils.read_yaml_file("scrape.yaml")
    plotter = MetricsPlotter(config_dict["plotting"])
    plotter.create_plots()


if __name__ == "__main__":
    main()
