# Python Imports
import logging
from pathlib import Path
from typing import Union
from result import Result, Err, Ok


logger = logging.getLogger(__name__)


def prepare_path(file_location: Union[str, Path]) -> Result[Path, str]:
    if type(file_location) is str:
        file_location = Path(file_location)

    if file_location.exists():
        logger.warning(f'{file_location} is already existing. File will be overwritten.')

    try:
        file_location.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(f'Error creating {file_location.parent}. {e}')

    return Ok(file_location)
