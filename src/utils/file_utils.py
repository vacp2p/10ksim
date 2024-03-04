# Python Imports
import os
from typing import List

# Project Imports


def get_files_from_folder_path(path: str) -> List:
    return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]


def get_file_name_from_path(file_path: str) -> str:
    return file_path.split("/")[-1]
