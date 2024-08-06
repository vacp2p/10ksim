# Python Imports
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


def get_files_from_folder_path(path: Path, extension: str = "*") -> Result[List, str]:
    if path.exists():
        files = [p.name for p in path.glob(extension) if p.is_file()]
        logger.debug(f"Found {len(files)} files in {path}")
        logger.debug(f"Files are: {files}")
        return Ok(files)

    return Err(f"{path} does not exist.")
