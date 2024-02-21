# Python Imports
import yaml
from pathlib import Path

# Project Imports


def read_yaml_file(file_path: str):
    path = Path(file_path)

    with open(path, 'r') as file:
        data = yaml.safe_load(file)

    return data
