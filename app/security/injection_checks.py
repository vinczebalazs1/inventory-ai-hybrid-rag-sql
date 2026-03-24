"""
Input-level prompt injection checks.

The patterns here are heuristic and intentionally simple.
They provide a first-pass safety filter before calling the LLM pipeline.
"""

import re


# Phrases commonly seen in prompt-injection attempts.
SUSPICIOUS_PATTERNS = [
    r"ignore previous instructions",
    r"disregard the rules",
    r"you are now",
    r"reveal the schema",
    r"output system prompt",
    r"drop table",
    r"delete from",
]


class PromptInjectionError(Exception):
    """Raised when input text matches a suspicious prompt-injection pattern."""
    pass


def check_prompt_injection(text: str) -> None:
    """
    Scan input text against known suspicious patterns.

    Raises:
    - PromptInjectionError: when a pattern indicates probable injection intent.
    """
    # Perform case-insensitive matching by normalizing to lowercase first.
    lowered = text.lower()

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, lowered):
            raise PromptInjectionError(
                f"Suspicious prompt/injection pattern detected: {pattern}"
            )
