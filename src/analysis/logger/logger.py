# Python Imports
import logging.config
import pathlib
import yaml

# Project Imports


with open(pathlib.Path(__file__).parent.resolve() / "logger_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
