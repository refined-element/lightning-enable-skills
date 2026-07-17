#!/usr/bin/env python3
"""
standing_orders.py — a local ledger of recurring Lightning restock orders.

There is NO server-side auto-charge and no card on file. This just remembers
WHAT you reorder and HOW OFTEN, and tells you which items are DUE. The agent
then runs the normal restock flow (catalog -> checkout -> confirm -> pay ->
complete) for each due item, and you confirm every cycle. That's the point:
recurring commerce with a human yes each time, Lightning per cycle.

State: JSON file (default ./.le-standing-orders.json; override with
L402_STANDING_ORDERS_FILE). No secrets.

  standing_orders.py add <slug> <variantId> <cadenceDays> <buyerLocation> <label...>
  standing_orders.py list
  standing_orders.py due
  standing_orders.py mark-ordered <id>
  standing_orders.py remove <id>
"""
import datetime
import json
import os
import sys

STATE = os.environ.get("L402_STANDING_ORDERS_FILE", ".le-standing-orders.json")


def _today():
    return datetime.date.today().isoformat()


class OrdersUnreadable(Exception):
    """The file exists but can't be trusted — order history is UNKNOWN, not empty."""


def _load():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        # No file yet: genuinely no standing orders.
        return {"orders": [], "next_id": 1}
    except (json.JSONDecodeError, OSError) as e:
        # The file exists but won't parse/read. Returning empty here would still
        # fail closed on money (no orders -> nothing due -> no spend), but the
        # next _save() would overwrite real order history with a blank file.
        raise OrdersUnreadable(str(e)) from e
    if not isinstance(d, dict) or not isinstance(d.get("orders"), list):
        raise OrdersUnreadable('malformed file: expected {"orders": [...], "next_id": N}')
    return d


def _save(d):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def _days_since(iso_date):
    if not iso_date:
        return None
    d = datetime.date.fromisoformat(iso_date)
    return (datetime.date.today() - d).days


def add(slug, variant_id, cadence_days, buyer_location, label):
    d = _load()
    oid = d["next_id"]
    d["orders"].append({
        "id": oid,
        "slug": slug,
        "variantId": int(variant_id),
        "cadenceDays": int(cadence_days),
        "buyerLocation": buyer_location,
        "label": label,
        "lastOrdered": None,
    })
    d["next_id"] = oid + 1
    _save(d)
    print(f"added standing order #{oid}: {label} - {slug} every {cadence_days}d")


def _is_due(o):
    since = _days_since(o.get("lastOrdered"))
    return since is None or since >= int(o["cadenceDays"])


def list_orders():
    d = _load()
    if not d["orders"]:
        print("no standing orders.")
        return
    for o in d["orders"]:
        since = _days_since(o.get("lastOrdered"))
        when = "never ordered" if since is None else f"{since}d ago"
        flag = "DUE" if _is_due(o) else "ok"
        print(f"#{o['id']} [{flag}] {o['label']} - {o['slug']} variant {o['variantId']} "
              f"every {o['cadenceDays']}d (last: {when})")


def due():
    d = _load()
    due_orders = [o for o in d["orders"] if _is_due(o)]
    if not due_orders:
        print(json.dumps({"due": []}, indent=2))
        return
    print(json.dumps({"due": due_orders}, indent=2))


def mark_ordered(oid):
    d = _load()
    for o in d["orders"]:
        if o["id"] == int(oid):
            o["lastOrdered"] = _today()
            _save(d)
            print(f"marked #{oid} ordered today ({_today()}).")
            return
    print(f"no standing order #{oid}.")


def remove(oid):
    d = _load()
    before = len(d["orders"])
    d["orders"] = [o for o in d["orders"] if o["id"] != int(oid)]
    _save(d)
    print("removed." if len(d["orders"]) < before else f"no standing order #{oid}.")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "add" and len(argv) >= 7:
            add(argv[2], argv[3], argv[4], argv[5], " ".join(argv[6:]))
        elif cmd == "list":
            list_orders()
        elif cmd == "due":
            due()
        elif cmd == "mark-ordered" and len(argv) == 3:
            mark_ordered(argv[2])
        elif cmd == "remove" and len(argv) == 3:
            remove(argv[2])
        else:
            print(__doc__)
            return 1
    except OrdersUnreadable as e:
        print(json.dumps({
            "error": f"standing-orders file unreadable: {e}",
            "file": STATE,
            "meaning": "order history is UNKNOWN, not empty - nothing was read, nothing due, nothing written",
            "fix": "repair the file by hand; do not re-add orders (a write would overwrite the history)",
        }, indent=2))
        return 2
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
