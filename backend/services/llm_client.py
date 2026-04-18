"""
OpenAI client wrapper with a circuit breaker and structured output support.

Design rationale:
  - LLMs fail in ways that HTTP clients don't: rate limits, schema violations,
    content refusals, and long-tail latency spikes. A circuit breaker prevents
    us from hammering the API after it's already failing, and gives operators
    a cooldown window to notice and intervene.
  - Every call returns telemetry (latency, engine used, retries) so the
    decision log can show HOW a decision was made, not just what it was.
  - Failure modes all route to the same place: the rule engine fallback.
    This keeps the system working even when OpenAI is down.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Prompts live as files next to this module. Loading them lazily + caching
# avoids re-reading from disk on every classification.
_PROMPT_CACHE: dict[str, str] = {}
_PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file by name (without extension). Cached after first read."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]

    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    _PROMPT_CACHE[name] = path.read_text(encoding="utf-8")
    return _PROMPT_CACHE[name]


class CircuitBreaker:
    """
    Minimal circuit breaker. Three states:
      - CLOSED: calls pass through
      - OPEN: calls fail fast (tripped after N consecutive failures)
      - HALF_OPEN: after cooldown, one call is allowed to probe recovery

    This is scoped to the process — a restart resets the state. For a
    multi-worker deployment you'd back it with Redis; overkill here.
    """

    def __init__(self, failure_threshold: int, cooldown_seconds: int):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.cooldown_seconds:
            # Cooldown elapsed — allow a probe call
            logger.info("Circuit breaker entering half-open state")
            return False
        return True

    def record_success(self) -> None:
        if self._consecutive_failures > 0 or self._opened_at is not None:
            logger.info("Circuit breaker: success recorded, resetting")
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures. Cooldown %ds.",
                self._consecutive_failures,
                self.cooldown_seconds,
            )

    def snapshot(self) -> dict:
        return {
            "open": self.is_open,
            "consecutive_failures": self._consecutive_failures,
            "opened_at": self._opened_at,
        }


class LLMUnavailable(Exception):
    """Raised when the LLM is unreachable or returns unusable output."""


class LLMClient:
    """
    Async wrapper around the OpenAI Responses API with structured outputs.

    Exposes a single method, `parse()`, which enforces a Pydantic schema
    on the response. On any failure (network, timeout, schema violation)
    it raises LLMUnavailable — callers handle the fallback.
    """

    def __init__(self):
        self.settings = get_settings()
        self.breaker = CircuitBreaker(
            failure_threshold=self.settings.llm_failure_threshold,
            cooldown_seconds=self.settings.llm_cooldown_seconds,
        )
        self._client = None  # lazy-init so config can be absent at import time

    def _get_client(self):
        """Lazy import + construct so the openai package is optional."""
        if self._client is None:
            if not self.settings.openai_api_key:
                raise LLMUnavailable("No OPENAI_API_KEY configured")
            try:
                from openai import AsyncOpenAI
            except ImportError as e:
                raise LLMUnavailable(f"openai package not installed: {e}")

            self._client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
                max_retries=0,  # we handle retries ourselves
            )
        return self._client

    async def parse(
        self,
        *,
        system_prompt: str,
        user_message: str,
        schema: Type[T],
    ) -> tuple[T, dict]:
        """
        Call OpenAI with structured output enforcement.

        Returns:
            (parsed_model, telemetry_dict)

        Raises:
            LLMUnavailable: breaker open, no key, or unrecoverable failure.
        """
        if not self.settings.ai_engine_active:
            raise LLMUnavailable(f"LLM not active (mode={self.settings.engine_mode})")

        if self.breaker.is_open:
            raise LLMUnavailable("circuit breaker open")

        client = self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.settings.openai_max_retries + 1):
            started = time.perf_counter()
            try:
                response = await client.responses.parse(
                    model=self.settings.openai_model,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    text_format=schema,
                    temperature=0,  # classification = deterministic
                )

                parsed = response.output_parsed
                if parsed is None:
                    # Model refused or returned empty — treat as retryable failure.
                    # We use last_error + continue so the retry loop handles it uniformly.
                    last_error = RuntimeError("model returned no parsed output")
                    logger.warning("LLM returned no parsed output on attempt %d", attempt + 1)
                else:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    self.breaker.record_success()

                    telemetry = {
                        "engine": "llm",
                        "model": self.settings.openai_model,
                        "latency_ms": latency_ms,
                        "retries": attempt,
                    }
                    return parsed, telemetry

            except ValidationError as e:
                # Schema mismatch — retry won't help, bail out immediately.
                logger.warning("LLM output failed schema validation: %s", e)
                self.breaker.record_failure()
                raise LLMUnavailable(f"schema validation: {e}") from e

            except (asyncio.TimeoutError, TimeoutError) as e:
                last_error = e
                logger.warning("LLM timeout on attempt %d", attempt + 1)

            except LLMUnavailable:
                # Explicit bail-outs (e.g., from nested calls) — don't retry.
                self.breaker.record_failure()
                raise

            except Exception as e:
                # Network errors, rate limits, 5xx — retry with backoff
                last_error = e
                logger.warning("LLM call failed on attempt %d: %s", attempt + 1, e)

            if attempt < self.settings.openai_max_retries:
                # Exponential backoff: 0.5s, 1s, 2s...
                await asyncio.sleep(0.5 * (2 ** attempt))

        # All retries exhausted
        self.breaker.record_failure()
        raise LLMUnavailable(f"exhausted retries: {last_error}") from last_error

    def health(self) -> dict:
        """Reporting hook for the /health endpoint."""
        return {
            "engine_mode": self.settings.engine_mode,
            "model": self.settings.openai_model if self.settings.ai_engine_active else None,
            "circuit_breaker": self.breaker.snapshot(),
        }


# Module-level singleton — same pattern as the orchestrator
llm_client = LLMClient()
