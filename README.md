# firedrill

**A green test suite is a claim, not a fact. firedrill is how you check the claim.**

firedrill runs *planned sabotage drills* against your codebase: it applies a
declared breakage, runs your gates (test suites, linters, health checks),
verifies that each one turns the color you **declared** it would — and always
restores your files, byte for byte.

```
mutation                gate   expected  measured  verdict
----------------------  -----  --------  --------  ------------------------
M1-inverted-comparison  tests  RED       RED       MATCH
M2-negative-restock     tests  green     green     MATCH (known blind spot)
M3-real-test-can-fail   tests  RED       RED       MATCH
```

Read that table again. **RED means your harness noticed the sabotage. green
means it did not — and that green is the finding.** M2 documents, in an
executable file under version control, that restock quantities can go negative
today and no test will object. The day someone fixes that test, this cell
must flip to RED *in the same commit* — or the drill fails the build.

## Why not just mutation testing?

Tools like `mutmut` mutate your *product code* at scale to compute a kill
score. firedrill does something different and complementary: a **small,
curated set of named breakages with a declared expected outcome per gate** —
a positive control for your verification harness, the way a lab validates an
instrument before trusting its readings.

|                      | mutation testing        | firedrill                          |
|----------------------|-------------------------|------------------------------------|
| mutations            | generated, hundreds     | curated, a handful, named          |
| output               | a score                 | a table of declarations vs reality |
| a surviving mutant   | noise to triage         | a *documented* blind spot, in git  |
| direction checked    | tests should fail       | **both**: `==`, never "at least"   |

Both directions matter: a green that turns RED is a new barrier nobody
recorded; a RED that turns green is a barrier somebody tore down.

## Quickstart

```bash
pip install git+https://github.com/MoisesPS2004/firedrill
git clone https://github.com/MoisesPS2004/firedrill && cd firedrill/example
firedrill list        # the declared table, touches nothing
firedrill run         # apply, measure, judge — exit 1 on drift
firedrill discover    # raw measurements, no judgment
firedrill check       # static: anchors exist & are unique (put this in CI)
```

The [example](example/) is a five-minute walkthrough: a tiny inventory module,
one real test, and one **vacuous test planted on purpose** — it iterates over
an empty collection, so `all()` over nothing is `True` and it passes no matter
what the code does. The drill proves it instead of arguing about it.

## Configuration

Everything lives in a `firedrill.toml` next to your code:

```toml
[settings]
timeout = 120                      # seconds per gate run

[gates]                            # every gate runs for every mutation
tests = "python3 -m pytest -q project/tests"

[[mutation]]
name = "M1-inverted-comparison"
file = "project/inventory.py"
find = 'if i["count"] < threshold]'      # must match EXACTLY once
replace = 'if i["count"] > threshold]'
note = "Sabotage the logic the real test covers. The alarm must ring."
[mutation.expect]                  # must declare EVERY gate
tests = "RED"
```

## Design rules (each one paid for)

- **Refuses to start on a dirty tree.** It reverts by content in `finally`,
  but a Ctrl-C in the worst microsecond must not be able to destroy anyone's
  uncommitted work.
- **Anchors must match exactly once**, verified before any file is touched
  and re-verified at apply time.
- **Baseline first.** All gates must be green before the first mutation is
  applied — a drill on a broken instrument measures nothing.
- **Restore is verified**, byte for byte. A failed restore is a loud exit,
  never a silent one.
- **A hung gate is a failing gate.** Timeouts count as RED.
- **Expectations are copied from a measurement, never declared from memory.**
  That is what `firedrill discover` is for; declaring colors from memory is
  exactly how this kind of control rots.
- **Writes bump the file's integer-seconds mtime.** CPython's bytecode cache
  validates against `(size, mtime)`; a same-length sabotage applied and
  reverted within one second would execute *stale* code. The drill's very
  first run caught this bug — in itself: a cell declared green measured RED,
  and the drift turned out to be the previous mutation's cached bytecode
  still running. The tool's first finding was a defect in the tool.

## Where this comes from

firedrill is the generalized form of the "Paso 0" battery inside the
verification harness of a production hostel-operations system built almost
entirely by directing coding agents. When you didn't hand-write the code, you
need instruments you can trust — and instruments you can trust are instruments
you routinely try to fool. Seven mutations across five repositories run as a
merge precondition there; the expected color of each cell is derived from the
project's risk register, so a risk cannot be marked "closed" without the
corresponding cell flipping in the same commit.

The origin story — six passing tests that verified nothing, found in one
afternoon — is written up in [docs/CASE_STUDY.md](docs/CASE_STUDY.md).

## License

MIT — see [LICENSE](LICENSE).
