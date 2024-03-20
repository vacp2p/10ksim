# Python Imports
from pathlib import Path
from result import Result, Err, Ok


def prepare_path(folder_location: str, file_name: str) -> Result[Path, str]:
    output_dir = Path(folder_location)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(f'Error creating {output_dir}. {e}')

    return Ok(output_dir / file_name)
