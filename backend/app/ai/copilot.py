"""Blueprint alias for the grounded copilot engine."""

from app.ai.copilot_engine import CopilotEngineError, answer_copilot

__all__ = ["CopilotEngineError", "answer_copilot"]
