"""Track Claude API costs per pipeline run and per agent."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from src.observability.logging import get_logger

log = get_logger("cost_tracker")

# Approximate pricing per 1M tokens (USD) as of 2025
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.00},
}


@dataclass
class APICall:
    agent_id: str
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    phase: str = ""

    @property
    def input_cost(self) -> float:
        pricing = MODEL_PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        return (self.input_tokens / 1_000_000) * pricing["input"]

    @property
    def output_cost(self) -> float:
        pricing = MODEL_PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        return (self.output_tokens / 1_000_000) * pricing["output"]

    @property
    def total_cost(self) -> float:
        return self.input_cost + self.output_cost


class CostTracker:
    """Tracks API costs across a pipeline run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.calls: list[APICall] = []

    def record_call(
        self,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_seconds: float = 0.0,
        phase: str = "",
    ) -> APICall:
        call = APICall(
            agent_id=agent_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            phase=phase,
        )
        self.calls.append(call)
        log.info(
            "api_call_recorded",
            run_id=self.run_id,
            agent_id=agent_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=f"${call.total_cost:.4f}",
        )
        return call

    @property
    def total_cost(self) -> float:
        return sum(c.total_cost for c in self.calls)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def cost_by_agent(self) -> dict[str, float]:
        costs: dict[str, float] = {}
        for call in self.calls:
            costs[call.agent_id] = costs.get(call.agent_id, 0.0) + call.total_cost
        return costs

    def cost_by_phase(self) -> dict[str, float]:
        costs: dict[str, float] = {}
        for call in self.calls:
            costs[call.phase] = costs.get(call.phase, 0.0) + call.total_cost
        return costs

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_calls": len(self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "cost_by_agent": {k: round(v, 4) for k, v in self.cost_by_agent().items()},
            "cost_by_phase": {k: round(v, 4) for k, v in self.cost_by_phase().items()},
        }
