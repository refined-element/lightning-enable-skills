"""Guardrail tests for skills/standing-order/scripts/standing_orders.py.

Pins the "fail loud on unknown state" behavior from PR #3 for the standing-order
ledger, plus the ledger P5 fix: ``next_id`` is validated/repaired in ``_load()``
so a colliding or stale counter can never write a duplicate order id.

Money-safety property under test: an unknown / unusable order file must never
silently proceed to write (which would overwrite real order history) or add an
order the code can't give a valid, unique id. It must fail closed -- exit 2, no
write -- and a recoverable counter must be repaired, never reused.
"""
import json


# --------------------------------------------------------------------------- #
# Corrupt vs missing: unknown history must fail loud, not read as "no orders".
# --------------------------------------------------------------------------- #

def test_corrupt_orders_file_fails_loud(run_standing, tmp_path):
    orders = tmp_path / "corrupt.json"
    original = "NOT JSON -- but real order history lived here"
    orders.write_text(original, encoding="utf-8")

    result = run_standing("list", orders_file=orders)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "unreadable" in payload["error"].lower()
    assert "UNKNOWN" in payload["meaning"]
    # A read of a corrupt file must not rewrite it.
    assert orders.read_text(encoding="utf-8") == original


def test_missing_orders_file_is_empty_not_error(run_standing, tmp_path):
    orders = tmp_path / "missing.json"
    result = run_standing("list", orders_file=orders)
    assert result.returncode == 0
    assert "no standing orders" in result.stdout.lower()


def test_corrupt_file_due_reports_no_spend_but_fails_closed(run_standing, tmp_path):
    """`due` drives the reorder/spend loop -- on a corrupt file it must fail
    closed (exit 2), never emit an empty due-list that reads as 'nothing due'."""
    orders = tmp_path / "corrupt_due.json"
    orders.write_text("{ broken", encoding="utf-8")
    result = run_standing("due", orders_file=orders)
    assert result.returncode == 2
    assert '"due": []' not in result.stdout


# --------------------------------------------------------------------------- #
# P5: next_id is not validated. Missing / non-numeric next_id must fail closed
# (exit 2, no order added, file not overwritten) rather than silently proceed.
# --------------------------------------------------------------------------- #

_ONE_ORDER = {
    "orders": [
        {
            "id": 1,
            "slug": "x",
            "variantId": 1,
            "cadenceDays": 7,
            "buyerLocation": "US",
            "label": "Existing",
            "lastOrdered": None,
        }
    ]
}


def test_missing_next_id_fails_closed_without_writing(run_standing, tmp_path):
    orders = tmp_path / "no_next_id.json"
    # Structurally valid ('orders' is a list) but 'next_id' absent.
    original = json.dumps(_ONE_ORDER)
    orders.write_text(original, encoding="utf-8")

    result = run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)

    assert result.returncode == 2, "add with no next_id must fail closed"
    # A missing counter is a malformed file -> a clean OrdersUnreadable, not a raw
    # KeyError leaking through the generic handler.
    assert "next_id" in json.loads(result.stdout)["error"]
    # No order was appended and the existing history was not overwritten.
    assert orders.read_text(encoding="utf-8") == original
    after = json.loads(orders.read_text(encoding="utf-8"))
    assert len(after["orders"]) == 1


def test_nonnumeric_next_id_fails_closed_without_writing(run_standing, tmp_path):
    orders = tmp_path / "str_next_id.json"
    original = json.dumps({"orders": [], "next_id": "abc"})
    orders.write_text(original, encoding="utf-8")

    result = run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)

    assert result.returncode == 2, "add with a non-numeric next_id must fail closed"
    # Rejected loud in _load() before any _save(), so the file is untouched.
    assert "next_id" in json.loads(result.stdout)["error"]
    assert orders.read_text(encoding="utf-8") == original


def test_colliding_next_id_does_not_create_duplicate_ids(run_standing, tmp_path):
    """The P5 fail-open bug, now fixed: a next_id that collides with an existing
    order id must never write a duplicate id. _load() repairs the stale counter
    upward, so add() allocates a guaranteed-free id."""
    orders = tmp_path / "collide.json"
    # next_id (1) collides with the existing order's id (1).
    orders.write_text(json.dumps({**_ONE_ORDER, "next_id": 1}), encoding="utf-8")

    result = run_standing("add", "coffee", "42", "30", "US", "New", orders_file=orders)
    assert result.returncode == 0, result.stdout

    saved = json.loads(orders.read_text(encoding="utf-8"))
    ids = [o["id"] for o in saved["orders"]]
    assert len(ids) == len(set(ids)), f"duplicate order ids created: {ids}"
    assert ids == [1, 2], f"the new order must get a fresh id, got {ids}"
    # The counter is left ahead of every live id.
    assert saved["next_id"] > max(ids)


def test_colliding_id_is_addressable_after_fix(run_standing, tmp_path):
    """Because ids stay unique, `remove`/`mark-ordered` address exactly one order
    (the pre-fix duplicate-id state broke both)."""
    orders = tmp_path / "collide2.json"
    orders.write_text(json.dumps({**_ONE_ORDER, "next_id": 1}), encoding="utf-8")
    run_standing("add", "coffee", "42", "30", "US", "New", orders_file=orders)

    # Remove the newly added order (#2); the original (#1) must survive.
    rm = run_standing("remove", "2", orders_file=orders)
    assert rm.returncode == 0
    remaining = [o["id"] for o in json.loads(orders.read_text(encoding="utf-8"))["orders"]]
    assert remaining == [1], f"remove hit the wrong/both orders: {remaining}"


def test_behind_counter_does_not_reuse_or_collide(run_standing, tmp_path):
    """A counter that has fallen behind a live id (id 3, next_id 1) must be
    repaired so the new order neither reuses nor eventually collides with id 3."""
    orders = tmp_path / "behind.json"
    behind = {
        "orders": [{**_ONE_ORDER["orders"][0], "id": 3}],
        "next_id": 1,
    }
    orders.write_text(json.dumps(behind), encoding="utf-8")

    result = run_standing("add", "coffee", "42", "30", "US", "New", orders_file=orders)
    assert result.returncode == 0, result.stdout
    ids = [o["id"] for o in json.loads(orders.read_text(encoding="utf-8"))["orders"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert 3 in ids and ids != [3, 3]
    assert max(ids) >= 4, f"new id must clear the existing max, got {ids}"


# --------------------------------------------------------------------------- #
# Happy path sanity: add / list / due / mark-ordered / remove.
# --------------------------------------------------------------------------- #

def test_add_then_list(run_standing, tmp_path):
    orders = tmp_path / "s.json"
    add = run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)
    assert add.returncode == 0
    listed = run_standing("list", orders_file=orders)
    assert listed.returncode == 0
    assert "Coffee beans" in listed.stdout


def test_new_order_is_due(run_standing, tmp_path):
    orders = tmp_path / "s.json"
    run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)
    due = run_standing("due", orders_file=orders)
    assert due.returncode == 0
    payload = json.loads(due.stdout)
    assert len(payload["due"]) == 1
    assert payload["due"][0]["slug"] == "coffee"


def test_mark_ordered_clears_due(run_standing, tmp_path):
    orders = tmp_path / "s.json"
    run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)
    assert run_standing("mark-ordered", "1", orders_file=orders).returncode == 0
    due = run_standing("due", orders_file=orders)
    assert json.loads(due.stdout)["due"] == []


def test_remove_order(run_standing, tmp_path):
    orders = tmp_path / "s.json"
    run_standing("add", "coffee", "42", "30", "US", "Coffee beans", orders_file=orders)
    rm = run_standing("remove", "1", orders_file=orders)
    assert rm.returncode == 0
    assert "removed" in rm.stdout.lower()
    listed = run_standing("list", orders_file=orders)
    assert "no standing orders" in listed.stdout.lower()
