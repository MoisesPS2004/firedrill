"""The drill engine: apply a declared breakage, run the gates, compare with ==.

Design rules, learned the hard way operating a production harness:

* **Refuse to start on a dirty tree.** The engine reverts by content in
  ``finally``, but a Ctrl-C in the worst microsecond must not be able to
  destroy anyone's uncommitted work.
* **Anchors must match exactly once.** A find-string that matches twice is
  applied nowhere; the run aborts before touching any file.
* **Expectations are compared with ``==``, in both directions.** A green that
  turns RED is a new barrier nobody recorded; a RED that turns green is a
  barrier somebody tore down. Both are findings.
* **Restore is verified.** After every mutation the file is written back and
  compared byte-for-byte against the original; a failed restore is a loud
  exit, never a silent one.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, Mutation

GREEN = "green"
RED = "RED"


class DrillError(Exception):
    """Operational error: the drill could not run at all (exit code 2)."""


@dataclass
class GateResult:
    gate: str
    measured: str          # GREEN | RED
    exit_code: int | None  # None on timeout
    seconds: float


@dataclass
class MutationReport:
    mutation: Mutation
    results: list[GateResult] = field(default_factory=list)

    @property
    def drifted(self) -> list[GateResult]:
        return [r for r in self.results
                if r.measured != self.mutation.expect[r.gate]]


# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #

def verify_anchors(cfg: Config) -> list[str]:
    """Every mutation's file must exist and its anchor must match exactly once."""
    problems: list[str] = []
    for m in cfg.mutations:
        path = cfg.root / m.file
        if not path.is_file():
            problems.append(f"{m.name}: file not found: {m.file}")
            continue
        count = path.read_text(encoding="utf-8").count(m.find)
        if count == 0:
            problems.append(f"{m.name}: anchor not found in {m.file}")
        elif count > 1:
            problems.append(
                f"{m.name}: anchor matches {count} times in {m.file} "
                "(must be unique)")
    return problems


def verify_tree_clean(cfg: Config) -> list[str]:
    """The files this drill will touch must have no uncommitted changes."""
    files = sorted({m.file for m in cfg.mutations})
    proc = subprocess.run(
        ["git", "-C", str(cfg.root), "status", "--porcelain", "--", *files],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return [f"not a git repository (or git failed): {cfg.root}. "
                "The drill edits real files; it refuses to run without "
                "version control underneath."]
    dirty = [line for line in proc.stdout.splitlines() if line.strip()]
    return [f"uncommitted changes in files the drill would touch:\n  "
            + "\n  ".join(dirty)] if dirty else []


# --------------------------------------------------------------------------- #
# gates
# --------------------------------------------------------------------------- #

def run_gate(cfg: Config, gate: str) -> GateResult:
    import os
    import sys
    import time
    cmd = shlex.split(cfg.gates[gate])
    # Gates inherit the environment, with the directory of the Python that
    # runs firedrill prepended to PATH — so "python3 -m pytest" means the
    # same interpreter you installed firedrill into, activated venv or not.
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + \
        env.get("PATH", "")
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cfg.root, capture_output=True,
                              timeout=cfg.timeout, env=env)
        code: int | None = proc.returncode
    except subprocess.TimeoutExpired:
        code = None  # a hung gate is a failing gate
    except FileNotFoundError as exc:
        raise DrillError(f"gate '{gate}': command not found: {cmd[0]}") from exc
    seconds = time.monotonic() - start
    measured = GREEN if code == 0 else RED
    return GateResult(gate=gate, measured=measured, exit_code=code,
                      seconds=seconds)


def run_all_gates(cfg: Config) -> list[GateResult]:
    return [run_gate(cfg, gate) for gate in cfg.gates]


# --------------------------------------------------------------------------- #
# the drill itself
# --------------------------------------------------------------------------- #

def _write_bumped(path: Path, text: str) -> None:
    """Write, then force the integer-seconds mtime to move forward.

    CPython's bytecode cache validates .pyc files against (size, mtime in
    whole seconds). A sabotage of the same byte length applied and reverted
    within one second would execute STALE code — the drill's own first run
    caught exactly that bug, in itself. Bumping mtime past the previous
    value closes it.
    """
    import os
    before = int(path.stat().st_mtime) if path.exists() else 0
    path.write_text(text, encoding="utf-8")
    st = path.stat()
    if int(st.st_mtime) <= before:
        os.utime(path, (st.st_atime, before + 1))


def _apply(cfg: Config, m: Mutation) -> str:
    path = cfg.root / m.file
    original = path.read_text(encoding="utf-8")
    if original.count(m.find) != 1:  # re-checked at the last moment
        raise DrillError(f"{m.name}: anchor no longer unique at apply time")
    _write_bumped(path, original.replace(m.find, m.replace, 1))
    return original


def _restore(cfg: Config, m: Mutation, original: str) -> None:
    path = cfg.root / m.file
    _write_bumped(path, original)
    if path.read_text(encoding="utf-8") != original:
        raise DrillError(
            f"{m.name}: RESTORE VERIFICATION FAILED for {m.file} — "
            "the working tree may be altered. Check `git diff` before "
            "doing anything else.")


def run_drill(cfg: Config) -> list[MutationReport]:
    """Apply each mutation in turn, measure every gate, always restore."""
    reports: list[MutationReport] = []
    for m in cfg.mutations:
        report = MutationReport(mutation=m)
        original = _apply(cfg, m)
        try:
            report.results = run_all_gates(cfg)
        finally:
            _restore(cfg, m, original)
        reports.append(report)
    return reports


def run_baseline(cfg: Config) -> list[GateResult]:
    """All gates must be green before the first mutation is applied.

    A drill on an instrument that is already red measures nothing.
    """
    return run_all_gates(cfg)
