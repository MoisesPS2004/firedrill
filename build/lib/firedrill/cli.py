"""Command-line interface.

Exit codes: 0 = every measurement matched its declaration;
1 = drift (a barrier appeared or disappeared without being recorded);
2 = the drill could not run at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, ConfigError, load_config
from .engine import (DrillError, GateResult, run_baseline, run_drill,
                     verify_anchors, verify_tree_clean)


def _fail(msg: str) -> int:
    print(f"firedrill: {msg}", file=sys.stderr)
    return 2


def _load(args: argparse.Namespace) -> Config:
    return load_config(Path(args.config))


def _preflight(cfg: Config, *, guard_tree: bool = True) -> list[str]:
    problems = verify_anchors(cfg)
    if guard_tree:
        problems += verify_tree_clean(cfg)
    return problems


def _print_table(rows: list[tuple[str, ...]], header: tuple[str, ...]) -> None:
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))


def cmd_check(args: argparse.Namespace) -> int:
    """Cheap static check, meant to run inside the target project's own CI:
    anchors still exist, are still unique, and every gate has a declaration."""
    try:
        cfg = _load(args)
    except ConfigError as exc:
        return _fail(str(exc))
    problems = verify_anchors(cfg)
    if problems:
        for p in problems:
            print(f"CHECK FAILED: {p}", file=sys.stderr)
        return 2
    print(f"check ok: {len(cfg.mutations)} mutations, "
          f"{len(cfg.gates)} gates, all anchors unique")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        cfg = _load(args)
    except ConfigError as exc:
        return _fail(str(exc))
    rows = []
    for m in cfg.mutations:
        for gate, color in m.expect.items():
            blind = "  (known blind spot)" if color == "green" else ""
            rows.append((m.name, gate, color + blind))
    _print_table(rows, ("mutation", "gate", "expected"))
    return 0


def _run_measured(args: argparse.Namespace, judge: bool) -> int:
    try:
        cfg = _load(args)
    except ConfigError as exc:
        return _fail(str(exc))

    problems = _preflight(cfg)
    if problems:
        for p in problems:
            print(f"REFUSING TO RUN: {p}", file=sys.stderr)
        return 2

    if not args.no_baseline:
        baseline = run_baseline(cfg)
        red = [r for r in baseline if r.measured == "RED"]
        if red:
            names = ", ".join(r.gate for r in red)
            return _fail(f"baseline is already RED ({names}). A drill on a "
                         "broken instrument measures nothing — fix the gates "
                         "first, or pass --no-baseline if that red is the "
                         "thing you are studying.")

    try:
        reports = run_drill(cfg)
    except DrillError as exc:
        return _fail(str(exc))

    rows: list[tuple[str, ...]] = []
    drift = 0
    for rep in reports:
        for res in rep.results:
            expected = rep.mutation.expect[res.gate]
            if judge:
                verdict = "MATCH" if res.measured == expected else "DRIFT"
                if verdict == "DRIFT":
                    drift += 1
                elif expected == "green":
                    verdict = "MATCH (known blind spot)"
                rows.append((rep.mutation.name, res.gate, expected,
                             res.measured, verdict))
            else:
                rows.append((rep.mutation.name, res.gate, res.measured,
                             f"{res.seconds:.1f}s"))

    if judge:
        _print_table(rows, ("mutation", "gate", "expected", "measured",
                            "verdict"))
        if drift:
            print(f"\n{drift} drifted cell(s). A green that turned RED is a "
                  "new barrier nobody recorded; a RED that turned green is a "
                  "barrier somebody tore down. Update the declaration in the "
                  "same commit as the change that moved it — or revert the "
                  "change.", file=sys.stderr)
            return 1
        print(f"\nall {len(rows)} cells match their declaration.")
        return 0

    _print_table(rows, ("mutation", "gate", "measured", "time"))
    print("\nraw measurements only — copy expectations from HERE, "
          "never from memory.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _run_measured(args, judge=True)


def cmd_discover(args: argparse.Namespace) -> int:
    return _run_measured(args, judge=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="firedrill",
        description="Planned sabotage drills for your test harness: break "
                    "things on purpose and verify the alarm actually rings.")
    parser.add_argument("-c", "--config", default="firedrill.toml",
                        help="path to firedrill.toml (default: ./firedrill.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="apply, measure, judge against "
                                       "declarations (exit 1 on drift)")
    p_run.add_argument("--no-baseline", action="store_true",
                       help="skip the all-green baseline requirement")
    p_run.set_defaults(func=cmd_run)

    p_disc = sub.add_parser("discover", help="apply and measure, print raw "
                                             "colors without judging")
    p_disc.add_argument("--no-baseline", action="store_true")
    p_disc.set_defaults(func=cmd_discover)

    p_list = sub.add_parser("list", help="print the declared table without "
                                         "touching anything")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check", help="static check: anchors exist and "
                                           "are unique (run this in CI)")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
