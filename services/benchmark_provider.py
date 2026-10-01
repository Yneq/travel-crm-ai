"""Benchmark adapters around the application's existing workflow providers.

Add a new model runtime here without changing fixture scoring or the CLI.
"""

from dataclasses import dataclass
from typing import Protocol

from services.followup_provider import get_followup_provider
from services.operations_agent_provider import get_operations_agent_provider
from services.planning_provider import get_planning_provider


@dataclass(frozen=True)
class BenchmarkTarget:
    provider: str
    model: str | None = None

    def __post_init__(self):
        if self.provider not in ("local", "gemini"):
            raise ValueError(f"Unsupported benchmark provider: {self.provider}")
        if self.provider == "local" and self.model:
            raise ValueError("The deterministic local provider has no model")

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider


class BenchmarkAdapter(Protocol):
    target: BenchmarkTarget

    def planning(self): ...
    def followup(self): ...
    def operations(self): ...


class ApplicationBenchmarkAdapter:
    def __init__(self, target: BenchmarkTarget):
        self.target = target

    def planning(self):
        return get_planning_provider(self.target.provider, model=self.target.model)

    def followup(self):
        return get_followup_provider(self.target.provider, model=self.target.model)

    def operations(self):
        if self.target.provider == "local":
            return None
        return get_operations_agent_provider(self.target.provider, model=self.target.model)


def make_benchmark_adapter(target: BenchmarkTarget) -> BenchmarkAdapter:
    return ApplicationBenchmarkAdapter(target)
