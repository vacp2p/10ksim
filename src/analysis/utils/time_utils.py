import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)


def to_utc_timestamp(dt: datetime) -> Optional[float]:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


class TimeInterval(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    start: datetime
    end: datetime


class TimeRange(BaseModel):
    """Time range.
    - Parses time str to remove the "T"
    - Assumes UTC
    - Requires that start <= end
    """

    _start: Optional[datetime] = None
    _end: Optional[datetime] = None

    @property
    def start(self) -> Optional[datetime]:
        return self._start

    @start.setter
    def start(self, value: Any) -> None:
        self._start = self._parse_start_end(value)
        self._ensure_end_after_start()

    @property
    def end(self) -> Optional[datetime]:
        return self._end

    @end.setter
    def end(self, value: Any) -> None:
        self._end = self._parse_start_end(value)
        self._ensure_end_after_start()

    @classmethod
    def _parse_start_end(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                logger.warning("Naive datetime passed for start/end; assuming UTC")
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        if isinstance(value, str):
            normalized_string = value.replace("T", " ")

            # Try timezone-aware formats first
            timezone_formats = [
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f%z",
            ]
            for format_string in timezone_formats:
                try:
                    dt = datetime.strptime(normalized_string, format_string)
                    return dt.astimezone(timezone.utc)
                except ValueError:
                    pass

            # Assume UTC
            naive_formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ]
            for format_string in naive_formats:
                try:
                    logger.warning(
                        f"Datetime string has no timezone; assuming UTC. Value: {value!r}"
                    )
                    return datetime.strptime(normalized_string, format_string).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass

            raise ValueError(f"Invalid datetime string: {value}")

        raise TypeError("start/end must be datetime, str, or None")

    @model_validator(mode="after")
    def _ensure_end_after_start(self) -> "TimeRange":
        if self._start is not None and self._end is not None and self._end < self._start:
            raise ValueError("end must be after start")
        return self

    def __str__(self) -> str:
        start_s = (
            self._start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if self._start
            else None
        )
        end_s = (
            self._end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if self._end
            else None
        )
        return f"TimeRange(start={start_s!r}, end={end_s!r})"
