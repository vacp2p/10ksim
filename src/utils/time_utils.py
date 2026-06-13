# Python Imports
import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Optional

import dateparser


def get_future_time(delay: timedelta, timezone: Optional[dt_timezone] = None) -> datetime:
    """
    Get the time it will be in `timezone` after `delay`.

    :param delay: The delay from current time.
    :param timezone: The timezone of the future time.
    :return: datetime in `timezone` of the now + `delay`.
    :rtype: datetime
    """
    timezone = timezone if timezone else dt_timezone.utc
    current_time_utc = datetime.now(timezone)
    return current_time_utc + delay


def wait_for_time(target_dt: datetime):
    """
    Wait until the specified target datetime.

    This function sleeps until the current UTC time reaches or surpasses
    the given `target_dt`.

    :param target_dt: The target datetime to wait for. Must be timezone-aware.
    :type target_dt: datetime.datetime

    :raises ValueError: If `target_dt` is not timezone-aware.
    """
    if target_dt.tzinfo is None or target_dt.tzinfo.utcoffset(target_dt) is None:
        raise ValueError("target_dt must be timezone-aware")

    now = datetime.now(dt_timezone.utc)
    seconds = (target_dt - now).total_seconds()
    if seconds > 0:
        time.sleep(seconds)


def timedelta_until(hours: int, minutes: int) -> timedelta:
    """Get the timedelta for the next UTC time represented by the given `hours` and `minutes`."""
    now = datetime.now(dt_timezone.utc)
    target = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    # If target is in the past, add 1 day to get the next occurrence.
    if target <= now:
        target += timedelta(days=1)

    return target - now


def str_to_timedelta(duration: str):
    utc_now = datetime.now(dt_timezone.utc)
    parsed_date = dateparser.parse(
        duration,
        settings={
            "RELATIVE_BASE": utc_now,
            "TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    if parsed_date is None:
        raise ValueError(f"Failed to parse duration: `{duration}`")
    return utc_now - parsed_date
