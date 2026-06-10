# Python Imports
import re
from typing import List, Optional


def get_flag_value(flag: str, command: List[str]) -> Optional[int]:
    for node in command:
        matches = re.search(f"--{flag}=(?P<numMessages>\\d+)", node)
        try:
            return int(matches["numMessages"])
        except (TypeError, IndexError):
            pass
    return None
