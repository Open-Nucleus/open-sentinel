"""Tests for Scheduler."""

from datetime import datetime, timezone

from open_sentinel.scheduler import ScheduleEntry, Scheduler


class TestScheduler:
    def test_register_and_next_wake(self):
        scheduler = Scheduler()

        async def noop(skill_name):
            pass

        scheduler.register("cholera", "*/5 * * * *", noop)
        scheduler.register("measles", "0 * * * *", noop)
        nxt = scheduler.next_wake_time()
        assert nxt is not None
        assert nxt > datetime.now(timezone.utc)

    def test_empty_scheduler(self):
        scheduler = Scheduler()
        assert scheduler.next_wake_time() is None

    def test_schedule_entry_next_time(self):
        async def noop(skill_name):
            pass

        entry = ScheduleEntry("test", "*/5 * * * *", noop)
        nxt = entry.next_time()
        assert isinstance(nxt, datetime)
        assert nxt.tzinfo is not None

    async def test_start_stop(self):
        scheduler = Scheduler()
        calls = []

        async def callback(skill_name):
            calls.append(skill_name)

        scheduler.register("test", "* * * * *", callback)
        await scheduler.start()
        await scheduler.stop()
        assert len(scheduler._tasks) == 0
