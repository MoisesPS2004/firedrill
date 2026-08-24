"""Load and validate a ``firedrill.toml``.

Validation is strict on purpose: every mutation must declare an expected
color for **every** gate. Leaving a gate undeclared would let a barrier be
torn down without anyone noticing — and both directions matter.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

VALID_COLORS = {"green", "RED"}


class ConfigError(Exception):
    pass


@dataclass
class Mutation:
    name: str
    file: str
    find: str
    replace: str
    expect: dict[str, str]          # gate name -> "green" | "RED"
    note: str = ""


@dataclass
class Config:
    root: Path
    gates: dict[str, str]           # gate name -> shell command
    mutations: list[Mutation]
    timeout: int = 300              # seconds per gate run
    path: Path = field(default=Path("firedrill.toml"))


def _normalize_color(raw: object, where: str) -> str:
    if not isinstance(raw, str) or raw.lower() not in {"green", "red"}:
        raise ConfigError(f"{where}: expected color must be 'green' or 'RED', "
                          f"got {raw!r}")
    return "green" if raw.lower() == "green" else "RED"


def load_config(path: Path) -> Config:
    path = path.resolve()
    if not path.is_file():
        raise ConfigError(f"config not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    settings = data.get("settings", {})
    timeout = settings.get("timeout", 300)
    if not isinstance(timeout, int) or timeout <= 0:
        raise ConfigError("settings.timeout must be a positive integer")

    gates = data.get("gates", {})
    if not gates or not isinstance(gates, dict):
        raise ConfigError("at least one [gates] entry is required")
    for name, cmd in gates.items():
        if not isinstance(cmd, str) or not cmd.strip():
            raise ConfigError(f"gate '{name}' must be a non-empty command string")

    raw_mutations = data.get("mutation", [])
    if not raw_mutations:
        raise ConfigError("at least one [[mutation]] is required")

    mutations: list[Mutation] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_mutations):
        where = f"mutation[{i}]"
        for key in ("name", "file", "find", "replace", "expect"):
            if key not in raw:
                raise ConfigError(f"{where}: missing required key '{key}'")
        name = raw["name"]
        if name in seen:
            raise ConfigError(f"{where}: duplicate mutation name '{name}'")
        seen.add(name)
        if raw["find"] == raw["replace"]:
            raise ConfigError(f"{name}: find and replace are identical — "
                              "this mutation would mutate nothing")

        expect_raw = raw["expect"]
        if set(expect_raw) != set(gates):
            missing = set(gates) - set(expect_raw)
            extra = set(expect_raw) - set(gates)
            detail = []
            if missing:
                detail.append(f"missing gates: {sorted(missing)}")
            if extra:
                detail.append(f"unknown gates: {sorted(extra)}")
            raise ConfigError(
                f"{name}: expect must declare every gate, both directions "
                f"matter ({'; '.join(detail)})")
        expect = {g: _normalize_color(c, f"{name}.expect.{g}")
                  for g, c in expect_raw.items()}

        mutations.append(Mutation(
            name=name, file=raw["file"], find=raw["find"],
            replace=raw["replace"], expect=expect,
            note=raw.get("note", "")))

    return Config(root=path.parent, gates=dict(gates), mutations=mutations,
                  timeout=timeout, path=path)
