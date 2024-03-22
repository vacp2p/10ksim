# Python Imports
import os
import yaml
import logging
from pathlib import Path
from typing import List, Dict
from result import Result, Err, Ok

# Project Imports


logger = logging.getLogger(__name__)


def read_yaml_file(file_path: str) -> Dict:
    path = Path(file_path)

    with open(path, 'r') as file:
        data = yaml.safe_load(file)

    return data


def get_files_from_folder_path(path: str) -> List:
    return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]


def get_file_name_from_path(file_path: str) -> str:
    return file_path.split("/")[-1]


def check_if_file_exists(file_path: str) -> Result[bool, bool]:
    if not os.path.exists(file_path):
        logger.error(f"{file_path} does not exists.")
        return Err(False)

    return Ok(True)
