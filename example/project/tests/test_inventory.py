import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inventory import low_stock, restock_order


def test_low_stock_flags_scarce_items():
    """A real test: it knows what the right answer looks like."""
    items = [{"name": "soap", "count": 1}, {"name": "towels", "count": 9}]
    assert low_stock(items) == ["soap"]


def test_restock_never_negative():
    """A VACUOUS test, planted on purpose.

    Nothing in `items` is below the threshold, so `order` is always {},
    and all() over an empty dict is True. This test passes no matter what
    restock_order computes — and the drill proves it (see M2).
    """
    items = [{"name": "towels", "count": 9}]
    order = restock_order(items)
    assert all(v > 0 for v in order.values())
