import logging.config
import yaml
import pathlib


with open(pathlib.Path(__file__).parent.resolve() / 'logger_config.yaml', 'r') as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
