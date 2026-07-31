# Python Imports
import re
from typing import List, Optional


def flag_exists(parser, flag_name):
    """Check if a flag exists in the given parser."""
    for action in parser._actions:
        if flag_name in action.option_strings:
            return True
    return False


def get_flag_value(flag: str, command: List[str]) -> Optional[int]:
    for node in command:
        matches = re.search(f"--{flag}=(?P<numMessages>\\d+)", node)
        try:
            return int(matches["numMessages"])
        except (TypeError, IndexError):
            pass
    return None
