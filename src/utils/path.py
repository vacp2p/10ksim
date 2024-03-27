# Python Imports
import os
import logging
from pathlib import Path
from typing import List
from result import Result, Err, Ok


logger = logging.getLogger(__name__)


def prepare_path(file_location: str) -> Result[Path, str]:
    file_location_path = Path(file_location)

    if file_location_path.exists():
        logger.warning(f'{file_location_path} is already existing. File will be overwritten.')

    try:
        file_location_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(f'Error creating {file_location_path.parent}. {e}')

    return Ok(file_location_path)


def get_files_from_folder_path(path: Path) -> Result[List, str]:
    if path.exists():
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        logger.info(f"Found {len(files)} in {path}")
        logger.debug(f"Files are: {files}")
        return Ok(files)

    return Err(f"{path} does not exist.")
