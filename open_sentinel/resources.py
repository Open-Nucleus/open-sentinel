"""Hardware profiles and resource management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class HardwareProfile:
    name: str
    llm_enabled: bool
    concurrent_skills: int
    max_reflections: int
    model: Optional[str]


PROFILES: Dict[str, HardwareProfile] = {
    "pi4_4gb": HardwareProfile(
        "pi4_4gb", llm_enabled=False,
        concurrent_skills=4, max_reflections=0, model=None,
    ),
    "pi4_8gb": HardwareProfile(
        "pi4_8gb", llm_enabled=True,
        concurrent_skills=2, max_reflections=2, model="phi3:mini",
    ),
    "uconsole_8gb": HardwareProfile(
        "uconsole_8gb", llm_enabled=True,
        concurrent_skills=2, max_reflections=2, model="phi3:mini",
    ),
    "hub_16gb": HardwareProfile(
        "hub_16gb", llm_enabled=True,
        concurrent_skills=4, max_reflections=3, model="llama3.2:3b",
    ),
    "hub_32gb": HardwareProfile(
        "hub_32gb", llm_enabled=True,
        concurrent_skills=8, max_reflections=3, model="llama3.2:8b",
    ),
    "cloud": HardwareProfile(
        "cloud", llm_enabled=True,
        concurrent_skills=8, max_reflections=3, model="gpt-4o",
    ),
}


class ResourceManager:
    def __init__(self, profile_name: str = "pi4_8gb"):
        self._profile = PROFILES[profile_name]
        self._llm_semaphore = asyncio.Semaphore(1)
        self._skill_semaphore = asyncio.Semaphore(self._profile.concurrent_skills)

    @property
    def profile(self) -> HardwareProfile:
        return self._profile

    def llm_enabled(self) -> bool:
        return self._profile.llm_enabled

    def max_reflections(self) -> int:
        return self._profile.max_reflections

    async def acquire_llm_slot(self) -> None:
        await self._llm_semaphore.acquire()

    def release_llm_slot(self) -> None:
        self._llm_semaphore.release()

    async def acquire_skill_slot(self) -> None:
        await self._skill_semaphore.acquire()

    def release_skill_slot(self) -> None:
        self._skill_semaphore.release()
