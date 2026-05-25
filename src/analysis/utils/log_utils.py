import argparse
import atexit
import logging
import os
import random
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, tzinfo
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Queue
from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


@contextmanager
def extra_log_handler(logger, handler, level=logging.INFO):
    logging.getLogger().setLevel(level)
    logger.addHandler(handler)
    try:
        yield
    finally:
        for handler in logger.handlers:
            handler.flush()
        logger.removeHandler(handler)
        handler.close()


@contextmanager
def log_to_path(log_path):
    """
    Warning: Removes previous log.
    """
    try:
        os.makedirs(log_path.parent, exist_ok=True)
        os.remove(log_path)
    except Exception:
        pass

    file_handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    current_level = logger.getEffectiveLevel()
    with extra_log_handler(logging.getLogger(), file_handler, current_level):
        yield


def get_log_level(verbosity: Union[str, int]) -> int:
    """
    Convert a verbosity value (int or str) to a logging level.

    :param verbosity: Verbosity as an integer (0-4) or log level name as a string (e.g., 'INFO').
    :type verbosity: Union[str, int]
    :return: Corresponding logging level for `logger.setLevel`.
    :rtype: int
    :raises ValueError: If the string is not a valid log level name.
    :raises TypeError: If verbosity is not int or str.
    """
    if isinstance(verbosity, int):
        if verbosity >= 4:
            return logging.NOTSET
        elif verbosity == 3:
            return logging.DEBUG
        elif verbosity == 2:
            return logging.INFO
        elif verbosity == 1:
            return logging.WARNING
        else:
            return logging.ERROR
    elif isinstance(verbosity, str):
        level = getattr(logging, verbosity.upper(), None)
        if isinstance(level, int):
            return level
        else:
            raise ValueError(f"Unknown log level name: `{verbosity}`")
    else:
        raise TypeError(
            f"Param `verbosity` must be a string or an int. Instead, given: `{type(verbosity)}`"
        )


class Config(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    logger_name: str = ""
    level: int
    fmt: str
    handlers: List[tuple[Path, int]] = []
    tz_offset_hours: float


class ISOFormatter(logging.Formatter):
    def __init__(self, fmt: str, tz: tzinfo):
        super().__init__(fmt, None)
        self.tz = tz

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        return dt.isoformat()


def make_formatter(config: Config) -> logging.Formatter:
    tz = timezone(timedelta(hours=config.tz_offset_hours))
    return ISOFormatter(fmt=config.fmt, tz=tz)


def apply_config(config: Config, log_queue=None):
    global _log_queue, _listener

    root = logging.getLogger()

    if log_queue:
        root.addHandler(QueueHandler(log_queue))
    else:
        if not _log_queue:
            atexit.register(ensure_listener_stopped)
            _log_queue = Queue(-1)

        ensure_listener_stopped()

        root.handlers.clear()

        formatter = make_formatter(config)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        sh.setLevel(config.level)
        root.addHandler(sh)

        for logger_name in list(logging.Logger.manager.loggerDict):
            if logger_name != "root":
                child_logger = logging.getLogger(logger_name)
                child_logger.handlers.clear()
                child_logger.propagate = True

        for path, level in config.handlers:
            fh = logging.FileHandler(path.as_posix())
            fh.setLevel(level)
            fh.setFormatter(formatter)
            root.addHandler(fh)

        _listener = QueueListener(_log_queue, *root.handlers)
        _listener.start()

    root.setLevel(config.level)
    return logging.getLogger(config.logger_name)


def capture_current_logging() -> Config:
    """Get a snapshot current logging config state"""
    root = logging.getLogger()
    # fmt = root.handlers[0].formatter._fmt if root.handlers else "%(levelname)s:%(name)s:%(message)s"

    formatter = root.handlers[0].formatter
    fmt = formatter._fmt

    tz_offset_hours = 0.0
    if hasattr(formatter, "tz") and formatter.tz:
        offset = formatter.tz.utcoffset(None)
        tz_offset_hours = offset.total_seconds() / 3600 if offset else 0.0

    level = root.level
    extra_handlers = [
        (handler.baseFilename, handler.level)
        for handler in root.handlers
        if isinstance(handler, logging.FileHandler)
    ]
    return Config(level=level, fmt=fmt, handlers=extra_handlers, tz_offset_hours=tz_offset_hours)


def init_logger(
    logger: logging.Logger, verbosity: Union[str, int], log_path: Optional[Path | str] = None
):
    level = get_log_level(verbosity)
    config = Config(
        logger_name=logger.name,
        level=level,
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[(Path(log_path), level)] if log_path else [],
        tz_offset_hours=0,
    )
    configured = apply_config(config)
    configured.info(f"Logging level set to: `{logging.getLevelName(level)}`")
    return configured


_log_queue = None
_listener = None


def get_log_queue():
    global _log_queue, _listener
    if _log_queue is None:
        raise ValueError("Logger not initialized")
    return _log_queue


def ensure_listener_stopped():
    global _listener
    if _listener:
        _listener.stop()


def setup_output_folder(args: argparse.Namespace) -> Path:
    base_out_dir = Path(__file__).parent / "out"
    if args.out_folder is not None:
        out_dir = (
            args.out_folder if args.out_folder.is_absolute() else base_out_dir / args.out_folder
        )
    else:
        # Adding a random number helps distinguish experiments.
        random_number = random.randint(1000, 9999)
        datetime_str = datetime.now().strftime("%Y.%m.%d_%H.%M.%f")[:-3]
        out_dir = base_out_dir / f"{datetime_str}_{random_number}"

    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir
