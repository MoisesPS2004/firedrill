"""Engine tests. Each one builds a real git repo in tmp_path, because the
engine refuses to run without version control underneath — and that refusal
is itself under test."""

import subprocess
import textwrap
from pathlib import Path

import pytest

from firedrill.cli import main

GATE = textwrap.dedent("""\
    import pathlib, sys
    sys.exit(0 if "GOOD" in pathlib.Path("app.txt").read_text() else 1)
    """)

CONFIG = textwrap.dedent("""\
    [settings]
    timeout = {timeout}

    [gates]
    check = "python3 gate.py"

    [[mutation]]
    name = "M1"
    file = "app.txt"
    find = "{find}"
    replace = "{replace}"
    [mutation.expect]
    check = "{expect}"
    """)


def make_repo(tmp_path: Path, *, app="GOOD\n", find="GOOD", replace="BAD",
              expect="RED", gate=GATE, timeout=60, commit=True) -> Path:
    (tmp_path / "app.txt").write_text(app)
    (tmp_path / "gate.py").write_text(gate)
    (tmp_path / "firedrill.toml").write_text(
        CONFIG.format(find=find, replace=replace, expect=expect,
                      timeout=timeout))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    if commit:
        subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c",
             "user.name=t", "commit", "-qm", "init"], check=True)
    return tmp_path


def run_cli(repo: Path, *argv: str) -> int:
    return main(["-c", str(repo / "firedrill.toml"), *argv])


def test_match_exits_zero_and_restores(tmp_path):
    repo = make_repo(tmp_path)  # breaking GOOD -> BAD must go RED: declared RED
    assert run_cli(repo, "run") == 0
    assert (repo / "app.txt").read_text() == "GOOD\n"


def test_drift_exits_one(tmp_path):
    # Declared green, but the gate DOES notice the sabotage -> drift.
    repo = make_repo(tmp_path, expect="green")
    assert run_cli(repo, "run") == 1
    assert (repo / "app.txt").read_text() == "GOOD\n"


def test_known_blind_spot_matches(tmp_path):
    # Mutate something the gate never looks at; declared green -> MATCH.
    repo = make_repo(tmp_path, app="GOOD extra\n", find="extra",
                     replace="EXTRA", expect="green")
    assert run_cli(repo, "run") == 0


def test_ambiguous_anchor_refuses_before_touching(tmp_path):
    repo = make_repo(tmp_path, app="GOOD GOOD\n")
    assert run_cli(repo, "run") == 2
    assert (repo / "app.txt").read_text() == "GOOD GOOD\n"


def test_dirty_tree_refuses(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "app.txt").write_text("GOOD uncommitted\n")
    assert run_cli(repo, "run") == 2
    assert (repo / "app.txt").read_text() == "GOOD uncommitted\n"


def test_no_git_refuses(tmp_path):
    (tmp_path / "app.txt").write_text("GOOD\n")
    (tmp_path / "gate.py").write_text(GATE)
    (tmp_path / "firedrill.toml").write_text(
        CONFIG.format(find="GOOD", replace="BAD", expect="RED", timeout=60))
    assert run_cli(tmp_path, "run") == 2


def test_red_baseline_aborts(tmp_path):
    repo = make_repo(tmp_path, app="BROKEN\n", find="BROKEN", replace="WORSE")
    assert run_cli(repo, "run") == 2


def test_timeout_counts_as_red_and_restores(tmp_path):
    hang = "import time; time.sleep(30)\n"
    repo = make_repo(tmp_path, gate=hang, timeout=1)
    # Baseline itself hangs -> RED baseline -> operational abort; the point
    # here is that a hung gate is treated as a failing gate, not a crash.
    assert run_cli(repo, "run") == 2
    assert (repo / "app.txt").read_text() == "GOOD\n"


def test_check_passes_and_fails(tmp_path):
    repo = make_repo(tmp_path)
    assert run_cli(repo, "check") == 0
    (repo / "app.txt").write_text("NOTHING HERE\n")
    assert run_cli(repo, "check") == 2


def test_expect_must_cover_every_gate(tmp_path):
    # A second gate appears and the mutation never declares a color for it:
    # the config loader must refuse — both directions matter.
    repo = make_repo(tmp_path)
    cfg = repo / "firedrill.toml"
    cfg.write_text(cfg.read_text().replace(
        '[gates]\ncheck = "python3 gate.py"',
        '[gates]\ncheck = "python3 gate.py"\nsecond = "python3 gate.py"'))
    assert run_cli(repo, "run") == 2


def test_same_second_writes_get_distinct_integer_mtimes(tmp_path):
    """CPython's bytecode cache keys on (size, integer mtime). Two same-size
    writes inside one second would execute stale code; the engine must bump
    the clock so every write is distinguishable."""
    from firedrill import engine
    from firedrill.config import load_config

    repo = make_repo(tmp_path, replace="GOOX")  # same length as GOOD
    cfg = load_config(repo / "firedrill.toml")
    m = cfg.mutations[0]
    path = repo / "app.txt"
    original = engine._apply(cfg, m)
    t_applied = int(path.stat().st_mtime)
    engine._restore(cfg, m, original)
    t_restored = int(path.stat().st_mtime)
    assert t_restored > t_applied
    assert path.read_text() == "GOOD\n"
