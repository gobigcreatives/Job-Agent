from datetime import datetime, timezone

from jobagent.config import ScheduleConfig
from jobagent.scheduling.scheduler import cron_expression, next_run_time


def test_manual_has_no_schedule():
    schedule = ScheduleConfig(frequency="manual", run_time="08:00", timezone="UTC")
    assert next_run_time(schedule) is None
    assert cron_expression(schedule) is None


def test_hourly_cron_expression():
    schedule = ScheduleConfig(frequency="hourly", run_time="08:00", timezone="UTC")
    assert cron_expression(schedule) == "0 * * * *"


def test_every_6_hours_cron_expression():
    schedule = ScheduleConfig(frequency="every_6_hours", run_time="08:00", timezone="UTC")
    assert cron_expression(schedule) == "0 */6 * * *"


def test_hourly_next_run_is_within_the_hour():
    schedule = ScheduleConfig(frequency="hourly", run_time="08:00", timezone="UTC")
    now = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    nxt = next_run_time(schedule, now=now)
    assert nxt == datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)


def test_every_6_hours_rolls_to_next_day_after_18():
    schedule = ScheduleConfig(frequency="every_6_hours", run_time="08:00", timezone="UTC")
    now = datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)
    nxt = next_run_time(schedule, now=now)
    assert nxt == datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc)


def test_daily_morning_next_run_today_if_before_run_time():
    schedule = ScheduleConfig(frequency="daily_morning", run_time="08:00", timezone="UTC")
    now = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    nxt = next_run_time(schedule, now=now)
    assert nxt == datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


def test_daily_morning_next_run_tomorrow_if_after_run_time():
    schedule = ScheduleConfig(frequency="daily_morning", run_time="08:00", timezone="UTC")
    now = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    nxt = next_run_time(schedule, now=now)
    assert nxt == datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)
