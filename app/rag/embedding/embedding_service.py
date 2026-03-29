import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")


def embed_text(text: str) -> list[float]:
    """
    Convert text into embedding vector.
    """
    response = client.embeddings.create(
        model=MODEL,
        input=text
    )
    return response.data[0].embedding