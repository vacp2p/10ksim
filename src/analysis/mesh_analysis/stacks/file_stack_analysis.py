# Python Imports
import logging
from typing import List

from pydantic import BaseModel, ConfigDict

# Project Imports
from src.analysis.mesh_analysis.readers.file_reader import FileReader
from src.analysis.utils import file_utils

logger = logging.getLogger(__name__)


class FileStackAnalysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    reader: FileReader

    def get_number_nodes(self, stateful_sets: List[str]) -> List[int]:
        files = file_utils.get_files_from_folder_path(
            self.reader._folder_path, extension="*.log"
        ).ok_value

        return [
            len(list(filter(lambda item: item.startswith(stateful_set_prefix), files)))
            for stateful_set_prefix in stateful_sets
        ]
