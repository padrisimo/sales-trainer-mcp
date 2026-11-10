"""Sales Trainer MCP package."""

from pathlib import Path

from dotenv import load_dotenv

# Real environment variables always win; .env is only a convenience for local runs.
# shortcut: .env is looked up next to the source tree, so an installed wheel just skips it.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
