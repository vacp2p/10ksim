# Python Imports
import pandas as pd
import yaml
import logging
from pathlib import Path
from typing import List, Dict
from result import Result, Err, Ok
from src.utils import path_utils

# Project Imports


logger = logging.getLogger(__name__)


def read_yaml_file(file_path: str) -> Dict:
    path = Path(file_path)

    with open(path, 'r') as file:
        data = yaml.safe_load(file)

    return data


def get_files_from_folder_path(path: Path, extension: str = '*') -> Result[List[str], str]:
    if not path.exists():
        return Err(f"{path} does not exist.")

    if not extension.startswith('*'):
        extension = '*.' + extension

    files = [p.name for p in path.glob(extension) if p.is_file()]
    logger.debug(f"Found {len(files)} files in {path}")
    logger.debug(f"Files are: {files}")

    return Ok(files)


def dump_df_as_csv(df: pd.DataFrame, file_location: Path, with_index: bool = True) -> Result[pd.DataFrame, str]:
    result = path_utils.prepare_path_for_file(file_location)
    if result.is_ok():
        df.to_csv(result.ok_value, index=with_index)
        logger.info(f'Dumped {file_location}')
        return Ok(df)

    return Err(f'{file_location} failed to dump.')
