"""
Thin wrapper around the OpenAI client for text generation tasks.

The helper function centralizes model invocation parameters so all services can
reuse a single call pattern.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

# Load API credentials and related runtime configuration.
load_dotenv()

# Initialize a reusable OpenAI client once at import time.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def ask_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Send a single user prompt to the selected model and return text content.

    Parameters:
    - prompt: full prompt string to send as a user message.
    - model: model identifier, defaults to a lightweight general-purpose model.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        # Use deterministic output for stable SQL and answer generation.
        temperature=0
    )
    return response.choices[0].message.content or ""
