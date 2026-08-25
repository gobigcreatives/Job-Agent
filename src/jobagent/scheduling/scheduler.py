"""Search frequency configuration (requirement #6). Two ways to use this:

1. Recommended: point OS cron / systemd timer / a hosting platform's
   scheduler at `jobagent run` using the cron expression `cron_expression()`
   produces for the configured frequency. A single-shot command invoked on
   a schedule survives restarts and doesn't depend on a long-lived process.
2. `run_forever()` is a minimal built-in loop for local/always-on use where
   an external scheduler isn't available.
"""
from __future__ import annotations

import time as time_module
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from jobagent.config import ScheduleConfig


def _parse_run_time(run_time: str) -> tuple[int, int]:
    hour_str, minute_str = run_time.split(":")
    return int(hour_str), int(minute_str)


def next_run_time(schedule: ScheduleConfig, now: Optional[datetime] = None) -> Optional[datetime]:
    """Returns the next run time in UTC, or None for manual scheduling."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if schedule.frequency == "manual":
        return None

    if schedule.frequency == "hourly":
        return (now.replace(minute=0, second=0, microsecond=0)) + timedelta(hours=1)

    if schedule.frequency == "every_6_hours":
        next_block = (now.hour // 6 + 1) * 6
        base = now.replace(minute=0, second=0, microsecond=0)
        if next_block >= 24:
            return base.replace(hour=0) + timedelta(days=1)
        return base.replace(hour=next_block)

    if schedule.frequency == "daily_morning":
        tz = ZoneInfo(schedule.timezone)
        local_now = now.astimezone(tz)
        hour, minute = _parse_run_time(schedule.run_time)
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    raise ValueError(f"Unknown schedule frequency: {schedule.frequency}")


def cron_expression(schedule: ScheduleConfig) -> Optional[str]:
    """A standard 5-field cron expression, in UTC, for the configured
    frequency — or None for manual (don't schedule anything)."""
    if schedule.frequency == "manual":
        return None
    if schedule.frequency == "hourly":
        return "0 * * * *"
    if schedule.frequency == "every_6_hours":
        return "0 */6 * * *"
    if schedule.frequency == "daily_morning":
        tz = ZoneInfo(schedule.timezone)
        hour, minute = _parse_run_time(schedule.run_time)
        local_dt = datetime.now(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
        utc_dt = local_dt.astimezone(timezone.utc)
        return f"{utc_dt.minute} {utc_dt.hour} * * *"
    raise ValueError(f"Unknown schedule frequency: {schedule.frequency}")


def run_forever(callback: Callable[[], None], schedule: ScheduleConfig, sleep_fn: Callable[[float], None] = time_module.sleep) -> None:
    """Blocking loop: runs `callback` immediately, then again at each
    scheduled time, forever. For `manual` frequency, runs once and returns
    — there is nothing to wait for."""
    callback()
    if schedule.frequency == "manual":
        return
    while True:
        target = next_run_time(schedule)
        delay = max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        sleep_fn(delay)
        callback()
