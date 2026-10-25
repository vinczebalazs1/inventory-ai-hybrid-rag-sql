"""Separate create/migrate stages; dry-run unless explicitly confirmed."""
from app.test_data.cli import main

if __name__ == "__main__":
    raise SystemExit(main("prepare"))
