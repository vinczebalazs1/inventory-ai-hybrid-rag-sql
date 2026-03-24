import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from `.env` as soon as this module is imported.
# This ensures DB connection parameters are available before `get_connection` is called.
load_dotenv()


def get_connection():
    """
    Create and return a new PostgreSQL connection using environment variables.

    Expected environment variables:
    - DB_NAME: database name
    - DB_USER: database user
    - DB_PASSWORD: database password
    - DB_HOST: database host
    - DB_PORT: database port

    The function returns a fresh connection object for each call.
    Connection lifecycle (opening/closing) is handled by the caller.
    """
    return psycopg2.connect(
        # Database name to connect to.
        dbname=os.getenv("DB_NAME"),
        # Username used for authentication.
        user=os.getenv("DB_USER"),
        # Password used for authentication.
        password=os.getenv("DB_PASSWORD"),
        # Host or IP where PostgreSQL is running.
        host=os.getenv("DB_HOST"),
        # TCP port exposed by PostgreSQL (usually 5432).
        port=os.getenv("DB_PORT"),
    )
