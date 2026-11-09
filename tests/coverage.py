#!/usr/bin/env python3
"""Run unit tests with branch coverage, print a coverage report, and enforce 90% diff coverage.

No .coverage / coverage.xml artifacts are left in the repo: both are written
to a temporary directory and deleted when the script exits.

Default: quiet — prints only the coverage and diff reports.
With -v/--verbose: also echoes commands and streams subprocess output.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

COMPARE_BRANCH = "origin/main"
DIFF_MIN = 90

VERBOSE = False


def run(cmd: list[str], *, env: dict | None = None) -> int:
    if VERBOSE:
        print("$", " ".join(cmd), flush=True)
        return subprocess.run(cmd, env=env).returncode
    # Quiet: capture output and only surface it on failure.
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
    return result.returncode


def print_total_coverage(xml_path: Path) -> None:
    """Parse the Cobertura XML and print a human-readable summary."""
    root = ET.parse(xml_path).getroot()
    line_rate = float(root.get("line-rate", 0.0)) * 100
    branch_rate = float(root.get("branch-rate", 0.0)) * 100
    lines_cov = int(root.get("lines-covered", 0))
    lines_val = int(root.get("lines-valid", 0))
    br_cov = int(root.get("branches-covered", 0))
    br_val = int(root.get("branches-valid", 0))

    print("\n=== Overall coverage ===")
    print(f"Lines:    {line_rate:6.2f}%  ({lines_cov}/{lines_val})")
    print(f"Branches: {branch_rate:6.2f}%  ({br_cov}/{br_val})")

    # Per-file breakdown: show the 5 lowest line-coverage files.
    files = []
    for cls in root.iter("class"):
        name = cls.get("filename", "?")
        fr = float(cls.get("line-rate", 0.0)) * 100
        files.append((fr, name))
    if files:
        files.sort()
        print("\nLowest-coverage files:")
        for fr, name in files[:5]:
            print(f"  {fr:6.2f}%  {name}")


def main() -> None:
    global VERBOSE
    parser = argparse.ArgumentParser(
        description="Run unit tests with branch coverage and diff-coverage gate."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="echo commands and stream subprocess output",
    )
    args = parser.parse_args()
    VERBOSE = args.verbose

    with tempfile.TemporaryDirectory(prefix="cov_") as tmpdir:
        tmp = Path(tmpdir)
        data_file = tmp / ".coverage"
        xml_file = tmp / "coverage.xml"

        # Keep coverage's data file out of the repo.
        env = os.environ.copy()
        env["COVERAGE_FILE"] = str(data_file)

        # 1) Unit tests with branch coverage -> .coverage (in temp dir)
        rc = run(
            [sys.executable, "-m", "coverage", "run",
             "--branch", "--source=src",
             "-m", "pytest", "tests/unit", "-q"],
            env=env,
        )
        if rc != 0:
            sys.exit(rc)

        # 2) XML report -> temp dir (needed by diff-cover)
        rc = run(
            [sys.executable, "-m", "coverage", "xml", "-o", str(xml_file), "-q"],
            env=env,
        )
        if rc != 0:
            sys.exit(rc)

        # 3) Parse and print overall coverage summary (the report).
        print_total_coverage(xml_file)

        # 4) Diff coverage vs main. Capture output so the report is printed on
        #    both success and failure; stream in verbose mode.
        print(f"\n=== Diff coverage vs {COMPARE_BRANCH} (min {DIFF_MIN}%) ===")
        diff_cmd = [
            "diff-cover", str(xml_file),
            f"--compare-branch={COMPARE_BRANCH}",
            f"--fail-under={DIFF_MIN}",
        ]
        if VERBOSE:
            print("$", " ".join(diff_cmd), flush=True)
            rc = subprocess.run(diff_cmd).returncode
        else:
            result = subprocess.run(diff_cmd, capture_output=True, text=True)
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            rc = result.returncode
        if rc != 0:
            print(f"\nDiff coverage below {DIFF_MIN}% or diff-cover failed.",
                  file=sys.stderr)
            sys.exit(rc)


if __name__ == "__main__":
    main()