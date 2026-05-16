"""Seed fake subagents into an existing session for UI testing.

Usage:
  .venv/bin/python seed_subagents.py <session_id>

The session_id must already exist in the DB.
"""

import sqlite3
import sys
from datetime import datetime, timezone

db_path = "claude_chat.db"


def now():
    return datetime.now(timezone.utc).isoformat()


def seed(session_id: str):
    con = sqlite3.connect(db_path)
    try:
        # Verify session exists
        row = con.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            print(f"session {session_id!r} not found in DB")
            sys.exit(1)

        subagents = [
            {
                "session_id": session_id,
                "tool_use_id": "toolu_test_001",
                "name": "Count Python files",
                "subagent_type": "general-purpose",
                "prompt": "Count all `.py` files in the current directory recursively and return the total.",
                "result": "Found **42** Python files across 7 directories.",
                "status": "done",
                "created_at": now(),
                "completed_at": now(),
            },
            {
                "session_id": session_id,
                "tool_use_id": "toolu_test_002",
                "name": "Find TODO comments",
                "subagent_type": "general-purpose",
                "prompt": "Search for all `TODO` comments in the codebase and summarize them.",
                "result": "",
                "status": "running",
                "created_at": now(),
                "completed_at": None,
            },
            {
                "session_id": session_id,
                "tool_use_id": "toolu_test_003",
                "name": "Check dependencies",
                "subagent_type": "general-purpose",
                "prompt": "List all outdated npm packages and suggest upgrades.",
                "result": "Error: could not parse package-lock.json — file not found.",
                "status": "failed",
                "created_at": now(),
                "completed_at": now(),
            },
        ]

        for s in subagents:
            con.execute(
                """
                INSERT OR IGNORE INTO subagents
                  (session_id, tool_use_id, name, subagent_type, prompt, result, status, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["session_id"],
                    s["tool_use_id"],
                    s["name"],
                    s["subagent_type"],
                    s["prompt"],
                    s["result"],
                    s["status"],
                    s["created_at"],
                    s["completed_at"],
                ),
            )
            print(f"  inserted: {s['name']} ({s['status']})")

        con.commit()
        print(f"\nDone. Reload the session {session_id[:8]}… in the UI to see the tabs.")
    finally:
        con.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    seed(sys.argv[1])
