# Python Imports
import argparse
import re
from typing import List, Optional


def gen_argparse(arg_defs):
    parser = argparse.ArgumentParser(description="Args generated from template.")
    # TODO [mutually exclusive args]: add logic here
    for arg in arg_defs:
        kwargs = {key: value for key, value in arg.items() if key != "name"}
        parser.add_argument(arg["name"], **kwargs)
    raise NotImplementedError()


def get_flag_value(flag: str, command: List[str]) -> Optional[int]:
    for node in command:
        matches = re.search(f"--{flag}=(?P<numMessages>\\d+)", node)
        try:
            return int(matches["numMessages"])
        except (TypeError, IndexError):
            pass
    return None


def assert_equals(obj_1, obj_2):
    assert obj_1 == obj_2, f"Assertion failed: `{obj_1}` == `{obj_2}`"
