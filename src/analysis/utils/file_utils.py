# Python Imports
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional

import pandas as pd
import yaml
from result import Err, Ok, Result

# Project Imports
from src.analysis.utils import path_utils

logger = logging.getLogger(__name__)


def read_yaml_file(file_path: str) -> Dict:
    path = Path(file_path)

    with open(path, "r") as file:
        data = yaml.safe_load(file)

    return data


def get_files_from_folder_path(
    path: Path, include_files: Optional[List[str]] = None, extension: str = "*"
) -> Result[List[str], str]:
    if not path.exists():
        return Err(f"{path} does not exist.")

    if not extension.startswith("*"):
        extension = "*." + extension

    files = [
        p.name
        for p in path.glob(extension)
        if p.is_file() and (include_files is None or p.name in include_files)
    ]
    logger.debug(f"Found {len(files)} files in {path}")
    logger.debug(f"Files are: {files}")

    return Ok(files)


def dump_df_as_csv(
    df: pd.DataFrame, file_location: Path, with_index: bool = True
) -> Result[pd.DataFrame, str]:
    result = path_utils.prepare_path_for_file(file_location)
    if result.is_ok():
        df.to_csv(result.ok_value, index=with_index)
        logger.info(f"Dumped {file_location}")
        return Ok(df)

    return Err(f"{file_location} failed to dump.")


def get_folders(base_dir: Path, file_name: str) -> Iterator[str]:
    """Yield folders under `base_dir` containing files with the given `file_name`"""
    for dirpath, _dirnames, filenames in os.walk(base_dir):
        if file_name in filenames:
            yield os.path.relpath(dirpath, base_dir)


def extract_exps(
    folders: List[str | Path], filters: List[Callable[[dict], bool]]
) -> Iterable[dict]:
    for folder in folders:
        try:
            metadata_log_path = Path(folder) / "metadata.json"
            logger.info(f"Events log path: {metadata_log_path}")
            with open(metadata_log_path, "r", encoding="utf-8") as f:
                exp = json.load(f)
            if any(filter(exp) == False for filter in filters):
                logger.warning(
                    f"Experiment filtered out. path: `{metadata_log_path}` metadata: `{exp}`"
                )
                continue
            exp["metadata"]["path"] = metadata_log_path
            yield exp
        except Exception as e:
            full_trace = traceback.format_exc()
            logger.error(f"exception: {e}\n{full_trace}")
            raise
