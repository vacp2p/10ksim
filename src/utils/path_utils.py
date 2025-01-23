# Python Imports
import logging
from pathlib import Path
from typing import Union
from result import Result, Err, Ok


logger = logging.getLogger(__name__)


def prepare_path_for_file(file_location: Union[str, Path]) -> Result[Path, str]:
    if type(file_location) is str:
        file_location = Path(file_location)

    if file_location.exists():
        logger.warning(f'{file_location} is already existing. File will be overwritten.')

    try:
        file_location.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(f'Error creating {file_location.parent}. {e}')

    return Ok(file_location)


def prepare_path_for_folder(folder_location: Union[str, Path]) -> Result[Path, str]:
    if type(folder_location) is str:
        folder_location = Path(folder_location)

    if folder_location.exists():
        return Ok(folder_location)

    try:
        folder_location.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(f'Error creating {folder_location.parent}. {e}')

    return Ok(folder_location)


def check_path_exists(func):
    def wrapper(self, path: Path, *args, **kwargs):
        if not path.exists():
            error = f'Path {args[0]} does not exist'
def _validate_path(param):
    if isinstance(param, Path):
        if not param.exists():
            error = f'Path {param} does not exist'
            logger.error(error)
            return Err(error)
    elif isinstance(param, list):
        if not all(isinstance(p, Path) for p in param):
            error = 'All elements in the list must be Path objects'
            logger.error(error)
            return Err(error)
        if not all(p.exists() for p in param):
            non_existing = [str(p) for p in param if not p.exists()]
            error = f'The following paths do not exist: {", ".join(non_existing)}'
            logger.error(error)
            return Err(error)
    return None

    return wrapper

        return wrapper

    return decorator
