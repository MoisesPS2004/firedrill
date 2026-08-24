"""A deliberately tiny inventory module for the firedrill walkthrough."""


def low_stock(items, threshold=3):
    """Names of items whose count is below the threshold."""
    return [i["name"] for i in items if i["count"] < threshold]


def restock_order(items, threshold=3, batch=10):
    """Units to order so each low-stock item reaches `batch`."""
    order = {}
    for i in items:
        if i["count"] < threshold:
            order[i["name"]] = batch - i["count"]
    return order
