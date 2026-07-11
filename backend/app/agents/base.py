"""
Base agent infrastructure for the Russian Trademark Registration System.

All domain agents inherit from BaseAgent and produce StructuredAgentOutput.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage
from app.infrastructure.llm.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass
class StructuredAgentOutput:
    """
    Unified output produced by every agent in the system.

    Fields
    ------
    summary         : Human-readable summary of what the agent did/found
    findings        : Domain-specific findings dict (agent-dependent schema)
    evidence        : Source data / excerpts supporting the findings
    missing_info    : Information the agent needs but couldn't find
    confidence      : [0.0, 1.0] how confident the agent is in its output
    next_actions    : Suggested follow-up steps
    human_review_required : Whether a human must review before proceeding
    raw_llm_output  : Raw LLM response for debugging/audit
    error           : If set, the agent failed and this explains why
    """

    summary: str = ""
    findings: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    missing_info: list[dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    next_actions: list[str] = field(default_factory=list)
    human_review_required: bool = False
    raw_llm_output: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "findings": self.findings,
            "evidence": self.evidence,
            "missing_info": self.missing_info,
            "confidence": self.confidence,
            "next_actions": self.next_actions,
            "human_review_required": self.human_review_required,
            "raw_llm_output": self.raw_llm_output,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# AgentRun log record (stored in DB by _log_run)
# ---------------------------------------------------------------------------


@dataclass
class AgentRunRecord:
    agent_type: str
    application_id: str | None
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    duration_ms: int
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------


class BaseAgent:
    """
    Abstract base class for all trademark system agents.

    Subclasses must implement:
        execute(input_data: dict) -> StructuredAgentOutput

    They may also override:
        input_schema  (class-level dict) — JSON Schema for expected inputs
        output_schema (class-level dict) — JSON Schema for produced outputs
    """

    agent_type: str = "base"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}

    def __init__(
        self,
        prompt_registry: PromptRegistry,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.prompt_registry = prompt_registry
        self.llm_provider = llm_provider
        self._run_log: list[AgentRunRecord] = []

    # ------------------------------------------------------------------
    # Core execution (must override)
    # ------------------------------------------------------------------

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        raise NotImplementedError(f"{self.agent_type}.execute() must be implemented")

    # ------------------------------------------------------------------
    # Prompt rendering helpers
    # ------------------------------------------------------------------

    def _render_prompt(self, prompt_id: str, variables: dict) -> str:
        """Render the user_template for a given prompt with Jinja2 variables."""
        return self.prompt_registry.render(prompt_id, variables)

    def _get_prompt_system(self, prompt_id: str) -> str:
        """Return the system message for a prompt."""
        return self.prompt_registry.get(prompt_id).system

    def _build_llm_messages(
        self, prompt_id: str, variables: dict
    ) -> list[LLMMessage]:
        """Build the full [system, user] message list for the LLM."""
        defn = self.prompt_registry.get(prompt_id)
        rendered_user = self._render_prompt(prompt_id, variables)
        return [
            LLMMessage(role="system", content=defn.system),
            LLMMessage(role="user", content=rendered_user),
        ]

    # ------------------------------------------------------------------
    # LLM call helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        prompt_id: str,
        variables: dict,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Call LLM and return the raw text content."""
        messages = self._build_llm_messages(prompt_id, variables)
        response = await self.llm_provider.generate(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.content

    async def _call_llm_structured(
        self,
        prompt_id: str,
        variables: dict,
        temperature: float = 0.1,
    ) -> dict:
        """Call LLM with structured JSON output expected."""
        defn = self.prompt_registry.get(prompt_id)
        messages = self._build_llm_messages(prompt_id, variables)
        return await self.llm_provider.generate_structured(
            messages,
            output_schema=defn.output_schema,
            temperature=temperature,
        )

    # ------------------------------------------------------------------
    # Run logging
    # ------------------------------------------------------------------

    def _log_run(
        self,
        application_id: str | None,
        input_data: dict,
        output: StructuredAgentOutput,
        duration_ms: int,
    ) -> AgentRunRecord:
        """
        Creates and stores an AgentRunRecord. In production this would be
        persisted to the database via a repository. Here we keep an in-memory
        log and emit to the logger.
        """
        record = AgentRunRecord(
            agent_type=self.agent_type,
            application_id=application_id,
            input_data=input_data,
            output_data=output.to_dict(),
            duration_ms=duration_ms,
            success=output.error is None,
            error=output.error,
        )
        self._run_log.append(record)
        logger.info(
            "AgentRun | agent=%s | app=%s | ok=%s | ms=%d | confidence=%.2f",
            self.agent_type,
            application_id or "—",
            record.success,
            duration_ms,
            output.confidence,
        )
        return record

    # ------------------------------------------------------------------
    # Validated execute wrapper
    # ------------------------------------------------------------------

    async def run(
        self, input_data: dict, application_id: str | None = None
    ) -> StructuredAgentOutput:
        """
        Public entry point. Wraps execute() with timing and run logging.
        Catches unexpected exceptions and converts them to error outputs.
        """
        t0 = time.time()
        output = StructuredAgentOutput()
        try:
            output = await self.execute(input_data)
        except Exception as exc:
            logger.exception("Agent %s failed: %s", self.agent_type, exc)
            output = StructuredAgentOutput(
                error=str(exc),
                human_review_required=True,
                summary=f"Агент {self.agent_type} завершился с ошибкой: {exc}",
            )
        finally:
            duration_ms = int((time.time() - t0) * 1000)
            self._log_run(application_id, input_data, output, duration_ms)

        return output
