"""
Input-szintű prompt injection ellenőrzések.

Az itt szereplő minták heurisztikusak és szándékosan egyszerűek.
Első körös biztonsági szűrőt adnak az LLM feldolgozási lánc meghívása előtt.
"""

import re # reguláris kifejezések


# Prompt-injection próbálkozásokban gyakran előforduló kifejezések.
SUSPICIOUS_PATTERNS = [

    # Prompt injection, azaz utasításmanipuláció
    r"ignore (all )?(previous )?instructions",
    r"disregard (the )?rules",
    r"forget (everything|all)",
    r"you are now",
    r"act as",
    r"pretend to be",

    # System prompt / séma kinyerési próbálkozások
    r"reveal (the )?schema",
    r"show (me )?(the )?(database )?schema",
    r"output (the )?system prompt",
    r"print (the )?system prompt",
    r"what is your system prompt",
    r"show hidden instructions",

    # SQL injection / adatbázis-manipulációs próbálkozások
    r"drop table",
    r"delete from",
    r"insert into",
    r"update .* set",
    r"alter table",
    r"truncate table",

    # Elrejtett vagy láncolt SQL injection minták
    r";\s*drop",
    r";\s*delete",
    r"--",
    r"/\*.*\*/",

    # Adatkiszivárogtatási próbálkozások
    r"dump (the )?database",
    r"export (all )?data",
    r"show all tables",
    r"list all tables",
    r"select \* from",

    # Jogosultságnövelés / szerepmanipuláció
    r"you are an admin",
    r"grant me access",
    r"bypass security",
    r"ignore security",

    # LLM jailbreak / biztonsági megkerülési próbálkozások
    r"do anything now",
    r"jailbreak",
    r"override restrictions",
    r"no restrictions",

]


class PromptInjectionError(Exception):
    """Akkor dobjuk, ha az input gyanús prompt-injection mintára illeszkedik."""
    pass


def check_prompt_injection(text: str) -> None:
    """
    Input szöveg ellenőrzése ismert gyanús minták ellen.

    Kivétel:
    - PromptInjectionError: ha egy minta valószínű injection szándékot jelez.
    """
    # Kis-nagybetű független kereséshez először kisbetűsítünk.
    lowered = text.lower()

    # Ez szándékosan első körös heurisztikus szűrő. Gyakori veszélyes
    # kifejezéseket fog meg, mielőtt a kérdés eljutna az útvonalválasztó LLM-hez.
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, lowered):
            raise PromptInjectionError(
                f"Suspicious prompt/injection pattern detected: {pattern}"
            )
