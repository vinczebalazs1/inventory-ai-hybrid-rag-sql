"""Validate then transactionally seed inventory_ai_clean; never replace data."""
from app.test_data.cli import main

if __name__ == "__main__":
    raise SystemExit(main("load"))
