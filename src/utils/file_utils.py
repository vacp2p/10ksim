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


def get_files_from_folder_path(path: Path) -> Result[List, str]:
    if path.exists():
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        logger.info(f"Found {len(files)} in {path}")
        logger.debug(f"Files are: {files}")
        return Ok(files)

    return Err(f"{path} does not exist.")
