"""Tests for EventBus."""

from open_sentinel.events import EventBus


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        bus.subscribe("test.event", lambda e: received.append(e))
        bus.emit("test.event", data="hello")
        assert len(received) == 1
        assert received[0]["data"] == "hello"
        assert received[0]["event"] == "test.event"

    def test_pattern_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe_pattern("skill.", lambda e: received.append(e))
        bus.emit("skill.started", skill="cholera")
        bus.emit("skill.completed", skill="cholera")
        bus.emit("agent.started")
        assert len(received) == 2

    def test_history(self):
        bus = EventBus()
        bus.emit("a")
        bus.emit("b")
        bus.emit("c")
        assert len(bus.history) == 3
        assert bus.history[0]["event"] == "a"

    def test_history_bounded(self):
        bus = EventBus(history_size=5)
        for i in range(10):
            bus.emit(f"event.{i}")
        assert len(bus.history) == 5
        assert bus.history[0]["event"] == "event.5"

    def test_handler_exception_ignored(self):
        bus = EventBus()
        received = []

        def bad_handler(e):
            raise ValueError("oops")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", lambda e: received.append(e))
        bus.emit("test")
        assert len(received) == 1

    def test_clear_history(self):
        bus = EventBus()
        bus.emit("a")
        bus.clear_history()
        assert len(bus.history) == 0

    def test_multiple_subscribers(self):
        bus = EventBus()
        counts = [0, 0]
        bus.subscribe("x", lambda e: counts.__setitem__(0, counts[0] + 1))
        bus.subscribe("x", lambda e: counts.__setitem__(1, counts[1] + 1))
        bus.emit("x")
        assert counts == [1, 1]
