"""Tests for ResourceManager."""

import asyncio

from open_sentinel.resources import PROFILES, ResourceManager


class TestResourceManager:
    def test_default_profile(self):
        rm = ResourceManager("pi4_8gb")
        assert rm.llm_enabled() is True
        assert rm.max_reflections() == 2
        assert rm.profile.concurrent_skills == 2

    def test_pi4_4gb_no_llm(self):
        rm = ResourceManager("pi4_4gb")
        assert rm.llm_enabled() is False
        assert rm.max_reflections() == 0

    def test_hub_32gb(self):
        rm = ResourceManager("hub_32gb")
        assert rm.llm_enabled() is True
        assert rm.max_reflections() == 3
        assert rm.profile.concurrent_skills == 8
        assert rm.profile.model == "llama3.2:8b"

    def test_all_profiles_exist(self):
        expected = {"pi4_4gb", "pi4_8gb", "uconsole_8gb", "hub_16gb", "hub_32gb", "cloud"}
        assert set(PROFILES.keys()) == expected

    async def test_llm_semaphore(self):
        rm = ResourceManager("pi4_8gb")
        await rm.acquire_llm_slot()
        # Should not be able to acquire again immediately (semaphore=1)
        acquired = False
        try:
            await asyncio.wait_for(rm.acquire_llm_slot(), timeout=0.05)
            acquired = True
        except asyncio.TimeoutError:
            pass
        assert not acquired
        rm.release_llm_slot()
        # Now should be able to acquire
        await asyncio.wait_for(rm.acquire_llm_slot(), timeout=0.1)
        rm.release_llm_slot()
