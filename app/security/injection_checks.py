"""
Input-level prompt injection checks.

The patterns here are heuristic and intentionally simple.
They provide a first-pass safety filter before calling the LLM pipeline.
"""

import re #regular expression


# Phrases commonly seen in prompt-injection attempts.
SUSPICIOUS_PATTERNS = [

    # Prompt injection (instruction manipulation)
    r"ignore (all )?(previous )?instructions",
    r"disregard (the )?rules",
    r"forget (everything|all)",
    r"you are now",
    r"act as",
    r"pretend to be",

    # System prompt / schema extraction attempts
    r"reveal (the )?schema",
    r"show (me )?(the )?(database )?schema",
    r"output (the )?system prompt",
    r"print (the )?system prompt",
    r"what is your system prompt",
    r"show hidden instructions",

    # SQL injection / database manipulation attempts
    r"drop table",
    r"delete from",
    r"insert into",
    r"update .* set",
    r"alter table",
    r"truncate table",

    # Obfuscated or chained SQL injection patterns
    r";\s*drop",
    r";\s*delete",
    r"--",
    r"/\*.*\*/",

    # Data exfiltration attempts
    r"dump (the )?database",
    r"export (all )?data",
    r"show all tables",
    r"list all tables",
    r"select \* from",

    # Privilege escalation / role manipulation
    r"you are an admin",
    r"grant me access",
    r"bypass security",
    r"ignore security",

    # LLM jailbreak / safety bypass attempts
    r"do anything now",
    r"jailbreak",
    r"override restrictions",
    r"no restrictions",

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
