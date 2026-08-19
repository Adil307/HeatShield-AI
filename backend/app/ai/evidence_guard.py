"""Blueprint alias for the structured evidence/claim guard."""

from app.ai.claim_guard import evaluate_structured_claim, screen_natural_language

__all__ = ["evaluate_structured_claim", "screen_natural_language"]
