# Python Imports
import logging
from functools import wraps
from pathlib import Path
from typing import Union, Callable
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


def check_params_path_exists_by_position(arg_position: int = 0) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            param = args[arg_position]
            error = _validate_path(param)
            if error:
                return error
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def check_params_path_exists_by_position_or_kwargs(arg_position: int, karg_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            param = None
            if arg_position < len(args):
                param = args[arg_position]
            elif karg_name in kwargs:
                param = kwargs[karg_name]

            error = _validate_path(param)
            if error:
                return error
            return func(self, *args, **kwargs)
        return wrapper

    return decorator
