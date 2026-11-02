"""Check that the CI workflow only names files that exist.

This exists because of a real failure. The workflow for this repository was adapted from a
sibling's, and its last step still ran that sibling's diagram renderer and diffed the
diagram it produced - neither of which exists here. Every other check passed, locally and
in CI, and the build failed on the one step nothing had ever run.

`make verify` could not have caught it: the gate runs the same *checks* as CI but not the
same *file*, so a workflow that referred to a script that had never existed was invisible
until it ran on a push. The fix for a gate that cannot see itself is to have it read the
thing that runs it.

Deliberately a text scan rather than a YAML parse. It needs no dependency, it cannot be
confused by a step whose shell is doing something clever, and the failure it guards against
is a path that does not exist on disk - which is a question about disk, not about YAML.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# `python tools/thing.py`, with or without a -m, and any interpreter spelling.
SCRIPT = re.compile(r"\bpython[0-9.]*\s+((?:tools|experiments)/[\w./-]+\.py)")
# `git diff --exit-code a/b.md c/d.svg`, up to the end of the line.
GIT_DIFF = re.compile(r"\bgit\s+diff\s+--exit-code\s+([^\n|&;]+)")


def check(path: Path, problems: list[str]) -> None:
    text = path.read_text()
    name = path.relative_to(ROOT)

    for script in sorted(set(SCRIPT.findall(text))):
        if not (ROOT / script).exists():
            problems.append(
                f"{name} runs `{script}`, which does not exist in this repository"
            )

    for group in GIT_DIFF.findall(text):
        for target in group.split():
            if target.startswith("-"):
                continue
            if not (ROOT / target).exists():
                problems.append(
                    f"{name} diffs `{target}`, which does not exist in this repository"
                )


def main() -> int:
    if not WORKFLOWS.is_dir():
        print(f"no workflows directory at {WORKFLOWS.relative_to(ROOT)}",
              file=sys.stderr)
        return 1

    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not files:
        print("no workflow files found; the gate has nothing to check itself against",
              file=sys.stderr)
        return 1

    problems: list[str] = []
    for path in files:
        check(path, problems)

    if problems:
        print("workflow check failed:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f"\n{len(problems)} problem(s). The workflow names a file that is not here, "
            "so the build will fail on a step nothing local ever runs.",
            file=sys.stderr,
        )
        return 1

    checked = ", ".join(str(p.relative_to(WORKFLOWS)) for p in files)
    print(f"workflow check passed: every path named in {checked} exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
