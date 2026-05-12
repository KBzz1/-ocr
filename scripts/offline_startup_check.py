#!/usr/bin/env python3
"""Offline startup acceptance check.

Run after ``run.bat`` has started the backend. This script only calls the
loopback status endpoint and performs static scans for forbidden external
download/CDN/API strings in startup files.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATUS_URL = "http://127.0.0.1:8081/api/system/status"
FORBIDDEN_TOKENS = (
    "https://",
    "cdn",
    "download",
    "pip install",
    "curl ",
    "wget ",
)
SCAN_FILES = (
    "run.bat",
    "stop.bat",
    "app/backend/main.py",
    "app/backend/__init__.py",
    "app/backend/config.py",
)


def check_status() -> dict:
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"status endpoint returned {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach local backend at {STATUS_URL}") from exc

    data = payload.get("data", {})
    if data.get("status") != "running":
        raise RuntimeError(f"unexpected status payload: {payload}")
    if "lan_addresses" not in data:
        raise RuntimeError("status payload missing lan_addresses")
    return data


def check_directories() -> None:
    for relative in ("data", "exports", "logs"):
        path = PROJECT_ROOT / relative
        if not path.is_dir():
            raise RuntimeError(f"required directory missing: {relative}")


def check_forbidden_tokens() -> None:
    violations = []
    for relative in SCAN_FILES:
        path = PROJECT_ROOT / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in FORBIDDEN_TOKENS:
            if token in content:
                violations.append(f"{relative}: {token}")
    if violations:
        raise RuntimeError(
            "forbidden external startup token found: "
            + ", ".join(sorted(set(violations)))
        )


def main() -> int:
    try:
        data = check_status()
        check_directories()
        check_forbidden_tokens()
    except Exception as exc:
        print(f"OFFLINE_CHECK_FAILED: {exc}")
        return 1

    print("OFFLINE_CHECK_OK")
    print(
        json.dumps(
            {
                "status": data["status"],
                "lan_addresses_count": len(data.get("lan_addresses", [])),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
