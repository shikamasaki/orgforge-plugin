#!/usr/bin/env python3
"""Minimal deterministic fake backend contract.

This is deliberately not a scheduler or admission engine.  It exists so
integrations can test lifecycle/error handling before a second real backend is
available.
"""
from dataclasses import dataclass, field


class BackendError(RuntimeError):
    pass


@dataclass
class FakeBackend:
    state: dict[str, str] = field(default_factory=dict)
    observations: list[dict] = field(default_factory=list)

    def submit(self, work_id: str, payload: dict) -> dict:
        if not work_id or work_id in self.state:
            raise BackendError("duplicate or empty work_id")
        self.state[work_id] = "submitted"
        self.observations.append({"work_id": work_id, "event": "submitted", "payload": payload})
        return {"work_id": work_id, "state": "submitted"}

    def observe(self, work_id: str) -> dict:
        if work_id not in self.state:
            raise BackendError("unknown work_id")
        return {"work_id": work_id, "state": self.state[work_id]}

    def complete(self, work_id: str, result: dict) -> dict:
        if work_id not in self.state:
            raise BackendError("unknown work_id")
        if self.state[work_id] != "submitted":
            raise BackendError("work is not submitted")
        self.state[work_id] = "completed"
        self.observations.append({"work_id": work_id, "event": "completed", "result": result})
        return {"work_id": work_id, "state": "completed"}

