# Six green tests that verified nothing

*The afternoon that produced firedrill.*

## The setup

I operate a production system for hostel volunteer scheduling — five
repositories, a Python + SQLite engine, a Telegram bot, a web board, all of it
built by directing coding agents rather than typing the code myself. That last
part matters: when you didn't hand-write the implementation, the test suite is
not a convenience. It is the only pair of eyes you have.

The suite was large — thousands of tests — and green. The project also keeps an
explicit list of requirements — 23 statements of what the system must
guarantee — and one afternoon I decided to audit the wiring: *for each
requirement, which test would go red if the requirement broke?*

Eight requirements had no test at all. Expected; orphans are easy to find.

The uncomfortable discovery was different: **six requirements had tests, the
tests passed, and the tests verified nothing.** They fell into three patterns.

## The three patterns

**1. Tautology.** The test computed its expected value using the same logic it
was supposed to check. Schematically:

```python
def test_totals_add_up():
    expected = sum(row.amount for row in rows)   # same formula as the code
    assert compute_total(rows) == expected        # can never disagree
```

Whatever bug the formula has, the expectation has it too. This test has no
failure mode short of a crash.

**2. Empty haystack.** The test asserted a property over every element of a
collection — and the collection was empty in the fixture, so the assertion
was vacuously true:

```python
def test_restock_never_negative():
    order = restock_order(items)          # items: nothing below threshold
    assert all(v > 0 for v in order.values())   # all() over {} is True
```

The code could return negative quantities, garbage, anything. The test scans
an empty set and reports victory.

**3. Circularity.** The test read its expected value from the same artifact
the code under test produced — comparing a thing to itself through a longer
pipe. A change that corrupted both sides equally stayed green.

## Why "run the tests" could never find this

Every one of these six was *green*. Coverage tools loved them — the lines
were executed. Review had passed them — each one looks reasonable in
isolation; the tautology in particular looks like a *thorough* test.

The only question that exposes them is: **what would have to break for this
test to fail?** If you cannot name a concrete breakage that flips it red, you
do not have a test; you have scenery.

And the only way to make that question routine instead of heroic is to ask it
mechanically: apply a named breakage, run the gates, and compare the measured
color against a declared one — in both directions, with `==`.

## What changed

The six tests were rewritten so each has a nameable failure mode. The eight
orphaned requirements got tests. And the question itself became an
executable: a battery of curated mutations that runs as a merge precondition,
where every cell's expected color lives in version control and is derived
from the project's risk register — so a known blind spot is *documented* as a
green cell, and fixing it forces the cell to flip RED in the same commit.

That battery, generalized and stripped of everything specific to my system,
is [firedrill](../README.md).

## The part I keep

Half the value of that afternoon was not the six fixes. It was the
refutation itself: the session set out to confirm the suite was sound and
proved its own premise wrong. A verification harness you have never managed
to fool is not a harness you can trust — it is a harness you have not tested.
