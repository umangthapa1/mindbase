#!/usr/bin/env python3
"""Mindbase All-Features Test Runner

Runs comprehensive automated tests across all Mindbase features:
- Tasks (add task, change priority, mark complete, status, due dates, delete)
- Notes & Memory Sync
- Calendar & Natural Language Scheduling
- ChromaDB Long-Term Memory
- Documents & RAG
- Chat & Intelligence
- Email & Automations
- System Health, Settings & Workspace Reset Protection
- Frontend UI Assets Integrity

Usage:
    python run_all_tests.py
"""
import os
import sys
import time
import subprocess
from pathlib import Path

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    banner = f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════════╗
║               MINDBASE FULL FEATURES TEST SUITE                  ║
║         Automated Testing of All Backend & UI Features           ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def run_test_group(title: str, pytest_filter: str) -> tuple[bool, str]:
    root_dir = Path(__file__).resolve().parent
    pytest_bin = root_dir / "venv" / "bin" / "pytest"
    if not pytest_bin.exists():
        pytest_bin = Path("pytest")

    cmd = [
        str(pytest_bin),
        "backend/tests/",
        "-k", pytest_filter,
        "-q",
        "--tb=short"
    ]
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True)
    duration = time.perf_counter() - start

    passed = proc.returncode == 0
    return passed, f"{duration:.2f}s"


def main():
    print_banner()

    features = [
        ("Task Operations (Create, Priority, Status, Complete, Delete)", "test_task"),
        ("Natural Language Scheduling & Due Dates", "test_parse_natural_due or test_scheduling"),
        ("Notes & Markdown Auto-Sync", "test_note or test_memory_upsert"),
        ("Calendar & Event Management", "test_calendar"),
        ("Long-Term Vector Memory (ChromaDB)", "test_memory"),
        ("Documents Management & RAG Upload", "test_document"),
        ("Chat, Conversations & Context Retrieval", "test_chat or test_intelligence"),
        ("Email Sync, Inbox & Automation Rules", "test_email or test_automations"),
        ("Health Checks, Ollama Models & Reset Token", "test_health or test_reset"),
        ("Frontend Templates & Static Assets Integrity", "test_frontend"),
    ]

    results = []
    print(f"{BOLD}{'Feature Area':<50} {'Status':<12} {'Duration':<10}{RESET}")
    print("─" * 74)

    all_passed = True
    for name, query in features:
        passed, duration = run_test_group(name, query)
        status_str = f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"
        if not passed:
            all_passed = False
        print(f"{name:<50} {status_str:<21} {duration:<10}")
        results.append((name, passed, duration))

    print("─" * 74)
    print("\nRunning complete regression test session...")
    root_dir = Path(__file__).resolve().parent
    pytest_bin = root_dir / "venv" / "bin" / "pytest"
    cmd = [str(pytest_bin), "backend/tests/", "-q"]
    full_run = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True)
    full_output = full_run.stdout.strip()

    print("\n" + "=" * 74)
    if all_passed and full_run.returncode == 0:
        print(f"{GREEN}{BOLD}🎉 ALL MINDBASE FEATURES TESTED AND PASSED SUCCESSFULLY!{RESET}")
        print(f"{CYAN}Pytest summary: {full_output}{RESET}")
        print("=" * 74 + "\n")
        return 0
    else:
        print(f"{RED}{BOLD}❌ SOME FEATURE TESTS FAILED:{RESET}")
        print(full_run.stdout)
        print(full_run.stderr)
        print("=" * 74 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
