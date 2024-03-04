# Python Imports
import os
import yaml
from pathlib import Path
from typing import List, Dict


# Project Imports


def read_yaml_file(file_path: str) -> Dict:
    path = Path(file_path)

    with open(path, 'r') as file:
        data = yaml.safe_load(file)

    return data


def get_files_from_folder_path(path: str) -> List:
    return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]


def get_file_name_from_path(file_path: str) -> str:
    return file_path.split("/")[-1]

