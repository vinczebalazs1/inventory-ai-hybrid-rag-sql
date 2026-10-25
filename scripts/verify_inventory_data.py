"""Read-only clean-database schema, constraint, quality and content verification."""
from app.test_data.cli import main

if __name__ == "__main__":
    raise SystemExit(main("verify"))
