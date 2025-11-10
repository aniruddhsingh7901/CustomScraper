from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_JOBS_JSON = os.getenv("REDDIT_JOBS_JSON", "storage/reddit/jobs.json")


@dataclass
class Job:
    id: str
    weight: float
    payload: Dict[str, Any]
    attempts: int = 0
    enqueued_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # keep stable order for readability
        return {
            "id": d["id"],
            "weight": d["weight"],
            "payload": d["payload"],
            "attempts": d["attempts"],
            "enqueued_at": d["enqueued_at"],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Job":
        return Job(
            id=d["id"],
            weight=float(d.get("weight", 1.0)),
            payload=d.get("payload", {}),
            attempts=int(d.get("attempts", 0)),
            enqueued_at=float(d.get("enqueued_at", 0.0)),
        )


class JobQueue:
    """
    JSON-backed job queue with weighted scheduling and basic retry semantics.

    File format:
    {
      "queue": [ {job}, ... ],
      "inflight": { "job_id": {job}, ... }
    }
    """

    def __init__(self, path: str = DEFAULT_JOBS_JSON):
        self.path = path
        self._lock = asyncio.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({"queue": [], "inflight": {}}, f)

    async def _load(self) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: json.load(open(self.path, "r")))

    async def _save(self, data: Dict[str, Any]) -> None:
        def _write():
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        await asyncio.to_thread(_write)

    async def enqueue(self, job: Job) -> None:
        async with self._lock:
            data = await self._load()
            job.enqueued_at = time.time()
            data["queue"].append(job.to_dict())
            await self._save(data)

    async def reprioritize(self, job_id: str, new_weight: float) -> bool:
        async with self._lock:
            data = await self._load()
            for j in data["queue"]:
                if j["id"] == job_id:
                    j["weight"] = float(new_weight)
                    await self._save(data)
                    return True
            # also check inflight
            if job_id in data.get("inflight", {}):
                data["inflight"][job_id]["weight"] = float(new_weight)
                await self._save(data)
                return True
            return False

    def _weighted_pick_index(self, jobs: List[Dict[str, Any]]) -> int:
        # pick higher weight preferentially, with slight aging by enqueued_at
        if not jobs:
            return -1
        total = 0.0
        weights = []
        now = time.time()
        for j in jobs:
            w = float(j.get("weight", 1.0))
            age = max(1.0, (now - float(j.get("enqueued_at", now))) / 60.0)
            score = max(0.0, w * age)
            weights.append(score)
            total += score
        if total <= 0.0:
            return 0
        import random
        r = random.uniform(0, total)
        upto = 0.0
        for idx, w in enumerate(weights):
            if upto + w >= r:
                return idx
            upto += w
        return len(jobs) - 1

    async def dequeue(self) -> Optional[Job]:
        async with self._lock:
            data = await self._load()
            q: List[Dict[str, Any]] = data.get("queue", [])
            if not q:
                return None
            idx = self._weighted_pick_index(q)
            job_dict = q.pop(idx)
            job = Job.from_dict(job_dict)
            # place into inflight
            inflight = data.get("inflight", {})
            inflight[job.id] = job.to_dict()
            data["inflight"] = inflight
            await self._save(data)
            return job

    async def ack(self, job_id: str) -> bool:
        async with self._lock:
            data = await self._load()
            if job_id in data.get("inflight", {}):
                del data["inflight"][job_id]
                await self._save(data)
                return True
            return False

    async def nack(self, job_id: str, requeue: bool = True, backoff_seconds: int = 5) -> bool:
        async with self._lock:
            data = await self._load()
            inflight = data.get("inflight", {})
            if job_id not in inflight:
                return False
            job = inflight[job_id]
            del inflight[job_id]
            if requeue:
                job["attempts"] = int(job.get("attempts", 0)) + 1
                job["enqueued_at"] = time.time() + max(0, backoff_seconds)
                data["queue"].append(job)
            data["inflight"] = inflight
            await self._save(data)
            return True

    async def size(self) -> Tuple[int, int]:
        async with self._lock:
            data = await self._load()
            return len(data.get("queue", [])), len(data.get("inflight", {}))
