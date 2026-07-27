"""Governed tool contracts for the RPA automation pack."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from activegraph.packs import tool

ReadProbeAdapter = Callable[[str], dict[str, Any]]


class ReadProbeInput(BaseModel):
    target: str = Field(description="Logical target identifier to inspect")


class ReadProbeOutput(BaseModel):
    value: str
    observed_at: str
    redacted_snippet: str = ""


def make_read_probe_tool(adapter: ReadProbeAdapter):
    """Build a pack tool closed over an injected adapter."""

    @tool(
        name="read_probe",
        description="Read-only probe of a target value through a governed adapter.",
        input_schema=ReadProbeInput,
        output_schema=ReadProbeOutput,
        deterministic=True,
        timeout_seconds=30.0,
    )
    def read_probe(args: ReadProbeInput, ctx: Any) -> ReadProbeOutput:
        raw = adapter(args.target)
        if not isinstance(raw, dict):
            raise TypeError("read_probe adapter must return a dict")
        return ReadProbeOutput.model_validate(raw)

    return read_probe
