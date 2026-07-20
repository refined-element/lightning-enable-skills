"""Guardrail tests for skills/standing-order/scripts/standing_orders.py.

Pins the "fail loud on unknown state" behavior from PR #3 for the standing-order
ledger, plus the ledger P5 note: ``next_id`` is not validated in ``_load()``.

Money-safety property under test: an unknown / unusable order file must never
silently proceed to write (which would overwrite real order history) or add an
order the code can't give a valid id. It must fail closed -- exit 2, no write.
"""
import json

import pytest


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
    # The TypeError happens before _save, so the file is untouched.
    assert orders.read_text(encoding="utf-8") == original


@pytest.mark.xfail(
    reason="P5 residual gap: next_id is not validated against existing ids, so a "
    "colliding next_id writes duplicate order ids. Not fixed in PR #3. This test "
    "asserts the SAFE behavior (unique ids) so it flips to XPASS when fixed.",
    strict=False,
)
def test_colliding_next_id_should_not_create_duplicate_ids(run_standing, tmp_path):
    orders = tmp_path / "collide.json"
    # next_id (1) collides with the existing order's id (1).
    orders.write_text(json.dumps({**_ONE_ORDER, "next_id": 1}), encoding="utf-8")

    result = run_standing("add", "coffee", "42", "30", "US", "New", orders_file=orders)
    assert result.returncode == 0

    ids = [o["id"] for o in json.loads(orders.read_text(encoding="utf-8"))["orders"]]
    # SAFE expectation: ids stay unique. (Currently produces [1, 1] -> xfail.)
    assert len(ids) == len(set(ids)), f"duplicate order ids created: {ids}"


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
