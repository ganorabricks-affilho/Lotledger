import calendar
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "lotledger.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    purchased_on TEXT NOT NULL,
    source TEXT NOT NULL,
    cost_cents INTEGER NOT NULL,
    shipping_cents INTEGER NOT NULL DEFAULT 0,
    tax_cents INTEGER NOT NULL DEFAULT 0,
    handling_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    details_filename TEXT NOT NULL DEFAULT '',
    details_imported_at TEXT,
    details_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listing_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT 'P',
    color TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    qty INTEGER NOT NULL,
    price_cents INTEGER NOT NULL DEFAULT 0,
    sale_rate INTEGER NOT NULL DEFAULT 0,
    condition TEXT NOT NULL DEFAULT 'U',
    remarks TEXT NOT NULL DEFAULT '',
    bl_lot_id TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    matched INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_listing_items_lot_id ON listing_items(lot_id);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sold_on TEXT NOT NULL,
    platform TEXT NOT NULL,
    order_ref TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    gross_cents INTEGER NOT NULL,
    fees_cents INTEGER NOT NULL DEFAULT 0,
    lot_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sales_lot_id ON sales(lot_id);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sold_on TEXT NOT NULL,
    sold_at TEXT NOT NULL DEFAULT '',
    platform_key TEXT NOT NULL,
    platform TEXT NOT NULL,
    order_number TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    shipping_cents INTEGER NOT NULL DEFAULT 0,
    packing_cents INTEGER NOT NULL DEFAULT 50,
    packing_minutes INTEGER NOT NULL DEFAULT 0,
    other_costs_cents INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '',
    payment_method TEXT NOT NULL DEFAULT '',
    header_lots INTEGER NOT NULL DEFAULT 0,
    header_qty INTEGER NOT NULL DEFAULT 0,
    header_total_cents INTEGER NOT NULL DEFAULT 0,
    tax_cents INTEGER NOT NULL DEFAULT 0,
    buyer_shipping_cents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform_key, order_number)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_id TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT '',
    category_id TEXT NOT NULL DEFAULT '',
    category_name TEXT NOT NULL DEFAULT '',
    color_id TEXT NOT NULL DEFAULT '',
    color_name TEXT NOT NULL DEFAULT '',
    qty INTEGER NOT NULL,
    condition TEXT NOT NULL DEFAULT '',
    price_cents INTEGER NOT NULL DEFAULT 0,
    image_url TEXT NOT NULL DEFAULT '',
    boid TEXT NOT NULL DEFAULT '',
    owl_lot_id TEXT NOT NULL DEFAULT '',
    bl_lot_id TEXT NOT NULL DEFAULT '',
    personal_note TEXT NOT NULL DEFAULT '',
    net_gain_cents INTEGER NOT NULL DEFAULT 0,
    lot_id INTEGER,
    matched_at TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_order_lines_order_id ON order_lines(order_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_lot_id ON order_lines(lot_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    added_packing = False
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(lots)")}
        if "tax_cents" not in cols:
            conn.execute("ALTER TABLE lots ADD COLUMN tax_cents INTEGER NOT NULL DEFAULT 0")
        if "handling_cents" not in cols:
            conn.execute("ALTER TABLE lots ADD COLUMN handling_cents INTEGER NOT NULL DEFAULT 0")
        if "details_filename" not in cols:
            conn.execute("ALTER TABLE lots ADD COLUMN details_filename TEXT NOT NULL DEFAULT ''")
        if "details_imported_at" not in cols:
            conn.execute("ALTER TABLE lots ADD COLUMN details_imported_at TEXT")
        if "details_locked" not in cols:
            conn.execute("ALTER TABLE lots ADD COLUMN details_locked INTEGER NOT NULL DEFAULT 0")
        order_cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        for name, ddl in (
            ("status", "TEXT NOT NULL DEFAULT ''"),
            ("payment_method", "TEXT NOT NULL DEFAULT ''"),
            ("header_lots", "INTEGER NOT NULL DEFAULT 0"),
            ("header_qty", "INTEGER NOT NULL DEFAULT 0"),
            ("header_total_cents", "INTEGER NOT NULL DEFAULT 0"),
            ("tax_cents", "INTEGER NOT NULL DEFAULT 0"),
            ("buyer_shipping_cents", "INTEGER NOT NULL DEFAULT 0"),
            ("packing_cents", "INTEGER NOT NULL DEFAULT 50"),
            ("packing_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in order_cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")
                if name == "packing_cents":
                    added_packing = True
        line_cols = {row[1] for row in conn.execute("PRAGMA table_info(order_lines)")}
        for name in ("image_url", "boid", "owl_lot_id", "bl_lot_id", "personal_note"):
            if name not in line_cols:
                conn.execute(f"ALTER TABLE order_lines ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        if "net_gain_cents" not in line_cols:
            conn.execute("ALTER TABLE order_lines ADD COLUMN net_gain_cents INTEGER NOT NULL DEFAULT 0")
        listing_cols = {row[1] for row in conn.execute("PRAGMA table_info(listing_items)")}
        for name, ddl in (
            ("item_name", "TEXT NOT NULL DEFAULT ''"),
            ("sale_rate", "INTEGER NOT NULL DEFAULT 0"),
            ("bl_lot_id", "TEXT NOT NULL DEFAULT ''"),
            ("image_url", "TEXT NOT NULL DEFAULT ''"),
            ("matched", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in listing_cols:
                conn.execute(f"ALTER TABLE listing_items ADD COLUMN {name} {ddl}")
        if "matched_at" not in line_cols:
            conn.execute("ALTER TABLE order_lines ADD COLUMN matched_at TEXT")
        scale = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("order_line_price_scale",)
        ).fetchone()
        if not scale or scale["value"] != "milli":
            conn.execute("UPDATE order_lines SET price_cents = price_cents * 10")
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("order_line_price_scale", "milli"),
            )
    if added_packing:
        with get_conn() as conn:
            order_ids = [row["id"] for row in conn.execute("SELECT id FROM orders")]
        for order_id in order_ids:
            persist_line_net_gains(order_id)


def parse_money(value: str) -> int:
    raw = (value or "").strip().replace("$", "").replace(",", "")
    if raw == "":
        return 0
    return int(round(float(raw) * 100))


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def money3(millis: int) -> str:
    sign = "-" if millis < 0 else ""
    millis = abs(millis or 0)
    return f"{sign}${millis // 1000:,}.{millis % 1000:03d}"


def money_input(cents: int) -> str:
    cents = cents or 0
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


PACKING_LABOR_CENTS_PER_HOUR = 4000  # $40/hour


def parse_minutes(value) -> int:
    raw = str(value or "").strip()
    if raw == "":
        return 0
    try:
        return max(0, int(round(float(raw))))
    except ValueError:
        return 0


def packing_labor_cents(minutes: int) -> int:
    """Convert packing minutes to cents at $40/hour."""
    return int(round(max(0, int(minutes or 0)) * PACKING_LABOR_CENTS_PER_HOUR / 60))


def get_setting(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def has_bricklink_creds() -> bool:
    keys = (
        "bricklink_consumer_key",
        "bricklink_consumer_secret",
        "bricklink_token",
        "bricklink_token_secret",
    )
    return all(get_setting(key) for key in keys)


def existing_order_numbers(platform_key: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT order_number FROM orders WHERE platform_key = ?",
            (platform_key,),
        ).fetchall()
    return {row["order_number"] for row in rows}


def live_line_net_gains(order_ids) -> dict:
    """Net gain per order_line id using the same live math as the order page."""
    gains = {}
    for order_id in sorted({int(oid) for oid in order_ids if oid is not None}):
        order = get_order(order_id)
        if order is None:
            continue
        for line in order["lines"]:
            gains[int(line["id"])] = int(line.get("net_gain_cents") or 0)
    return gains


def list_lots():
    sql = """
        SELECT
            lots.*,
            COALESCE((SELECT SUM(net_gain_cents) FROM order_lines WHERE order_lines.lot_id = lots.id), 0) AS revenue_cents,
            0 AS fees_cents,
            COALESCE((SELECT COUNT(*) FROM order_lines WHERE order_lines.lot_id = lots.id), 0) AS sale_count,
            COALESCE((SELECT COUNT(*) FROM listing_items WHERE listing_items.lot_id = lots.id), 0) AS detail_count,
            COALESCE((SELECT SUM(qty) FROM listing_items WHERE listing_items.lot_id = lots.id), 0) AS listed_qty,
            COALESCE((SELECT SUM(qty * price_cents) FROM listing_items WHERE listing_items.lot_id = lots.id), 0) AS listed_value_cents
        FROM lots
        GROUP BY lots.id
        ORDER BY lots.purchased_on DESC, lots.id DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
        matched_rows = conn.execute(
            "SELECT id, order_id, lot_id FROM order_lines WHERE lot_id IS NOT NULL"
        ).fetchall()
    gains = live_line_net_gains(row["order_id"] for row in matched_rows)
    revenue_by_lot = {}
    for row in matched_rows:
        lot_id = row["lot_id"]
        revenue_by_lot[lot_id] = revenue_by_lot.get(lot_id, 0) + gains.get(row["id"], 0)
    lots = []
    for row in rows:
        data = dict(row)
        if data["id"] in revenue_by_lot:
            data["revenue_cents"] = revenue_by_lot[data["id"]]
        lots.append(_enrich_lot(data))
    return lots


def get_lot(lot_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
        if row is None:
            return None
        matched = conn.execute(
            """
            SELECT order_lines.*, orders.sold_on, orders.platform, orders.order_number
            FROM order_lines
            JOIN orders ON orders.id = order_lines.order_id
            WHERE order_lines.lot_id = ?
            ORDER BY orders.sold_on DESC, orders.id DESC, order_lines.id DESC
            """,
            (lot_id,),
        ).fetchall()
        items = conn.execute(
            """
            SELECT * FROM listing_items
            WHERE lot_id = ?
            ORDER BY matched DESC, item_type, item_id, color, id
            """,
            (lot_id,),
        ).fetchall()
    matched = [dict(line) for line in matched]
    gains = live_line_net_gains(line["order_id"] for line in matched)
    net_by_bl = {}
    order_by_bl = {}
    sold_qty_by_bl = {}
    for line in matched:
        line["net_gain_cents"] = gains.get(line["id"], int(line.get("net_gain_cents") or 0))
        bl_lot_id = line.get("bl_lot_id") or ""
        if bl_lot_id:
            net_by_bl[bl_lot_id] = net_by_bl.get(bl_lot_id, 0) + line["net_gain_cents"]
            order_by_bl[bl_lot_id] = line["order_id"]
            sold_qty_by_bl[bl_lot_id] = sold_qty_by_bl.get(bl_lot_id, 0) + int(line.get("qty") or 0)
    revenue = sum(int(line.get("net_gain_cents") or 0) for line in matched)
    matched_groups = []
    group_index = {}
    for line in matched:
        key = (line.get("sold_on") or "", line.get("order_id"))
        group = group_index.get(key)
        if group is None:
            group = {
                "sold_on": line.get("sold_on") or "",
                "order_id": line.get("order_id"),
                "platform": line.get("platform") or "",
                "order_number": line.get("order_number") or "",
                "lines": [],
                "qty": 0,
                "net_cents": 0,
            }
            group_index[key] = group
            matched_groups.append(group)
        group["lines"].append(line)
        group["qty"] += int(line.get("qty") or 0)
        group["net_cents"] += int(line.get("net_gain_cents") or 0)
    items = [dict(item) for item in items]
    for item in items:
        bl_lot_id = item.get("bl_lot_id") or ""
        listed_qty = int(item.get("qty") or 0)
        sold_qty = int(sold_qty_by_bl.get(bl_lot_id, 0))
        item["sale_net_gain_cents"] = net_by_bl.get(bl_lot_id, 0)
        item["matched_order_id"] = order_by_bl.get(bl_lot_id)
        item["sold_qty"] = sold_qty
        item["remaining_qty"] = max(listed_qty - sold_qty, 0)
        if sold_qty <= 0 and not int(item.get("matched") or 0):
            item["match_state"] = ""
        elif listed_qty > 0 and sold_qty < listed_qty:
            item["match_state"] = "partial"
        else:
            item["match_state"] = "full"
    lot = _enrich_lot(
        {
            **dict(row),
            "revenue_cents": revenue,
            "fees_cents": 0,
            "sale_count": len(matched),
            "detail_count": len(items),
            "listed_qty": sum(item["qty"] for item in items),
            "listed_value_cents": sum(item["qty"] * item["price_cents"] for item in items),
        }
    )
    lot["matched_lines"] = matched
    lot["matched_groups"] = matched_groups
    lot["listed_items"] = items
    lot["details_locked"] = bool(lot.get("details_locked"))
    return lot


def create_lot(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO lots (
                title, purchased_on, source, cost_cents, shipping_cents, tax_cents, handling_cents, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"],
                data["purchased_on"],
                data["source"],
                data["cost_cents"],
                data.get("shipping_cents", 0),
                data.get("tax_cents", 0),
                data.get("handling_cents", 0),
                data.get("notes", ""),
            ),
        )
        return cur.lastrowid


def update_lot(lot_id: int, data: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE lots
            SET title = ?, purchased_on = ?, source = ?, cost_cents = ?,
                shipping_cents = ?, tax_cents = ?, handling_cents = ?, notes = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["purchased_on"],
                data["source"],
                data["cost_cents"],
                data.get("shipping_cents", 0),
                data.get("tax_cents", 0),
                data.get("handling_cents", 0),
                data.get("notes", ""),
                lot_id,
            ),
        )


def replace_listing(lot_id: int, filename: str, items: list) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM listing_items WHERE lot_id = ?", (lot_id,))
    append_listing(lot_id, filename, items)


def set_lot_details_locked(lot_id: int, locked: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE lots SET details_locked = ? WHERE id = ?",
            (1 if locked else 0, lot_id),
        )


def append_listing(lot_id: int, filename: str, items: list) -> dict:
    """Add listing rows; skip inventory IDs already on this lot. Returns counts."""
    with get_conn() as conn:
        existing = {
            row["bl_lot_id"]
            for row in conn.execute(
                "SELECT bl_lot_id FROM listing_items WHERE lot_id = ? AND bl_lot_id != ''",
                (lot_id,),
            )
        }
        to_add = []
        skipped = 0
        for item in items:
            bl_lot = item.get("bl_lot_id") or ""
            if bl_lot and bl_lot in existing:
                skipped += 1
                continue
            if bl_lot:
                existing.add(bl_lot)
            to_add.append(item)
        if to_add:
            conn.executemany(
                """
                INSERT INTO listing_items (
                    lot_id, item_id, item_name, item_type, color, category, qty,
                    price_cents, sale_rate, condition, remarks, bl_lot_id, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        lot_id,
                        item.get("item_id") or "",
                        item.get("item_name") or "",
                        item.get("item_type") or "",
                        item.get("color") or "",
                        item.get("category") or "",
                        item.get("qty") or 0,
                        item.get("price_cents") or 0,
                        item.get("sale_rate") or 0,
                        item.get("condition") or "",
                        item.get("remarks") or "",
                        item.get("bl_lot_id") or "",
                        item.get("image_url") or "",
                    )
                    for item in to_add
                ],
            )
        prev = conn.execute(
            "SELECT details_filename FROM lots WHERE id = ?", (lot_id,)
        ).fetchone()
        prev_name = (prev["details_filename"] if prev else "") or ""
        parts = [p for p in prev_name.split(",") if p.strip()]
        if filename and filename not in parts:
            parts.append(filename)
        conn.execute(
            """
            UPDATE lots
            SET details_filename = ?, details_imported_at = datetime('now')
            WHERE id = ?
            """,
            (",".join(parts), lot_id),
        )
    return {"added": len(to_add), "skipped": skipped}


def clear_listing(lot_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM listing_items WHERE lot_id = ?", (lot_id,))
        conn.execute(
            """
            UPDATE lots
            SET details_filename = '', details_imported_at = NULL
            WHERE id = ?
            """,
            (lot_id,),
        )
    return cur.rowcount


def preview_listing_price_updates(bl_prices: dict) -> dict:
    """Compare listing unit prices to BrickLink inventory prices by bl_lot_id.

    Does not write. bl_prices maps inventory_id -> {price_cents, ...}.
    """
    with get_conn() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    li.id, li.lot_id, li.bl_lot_id, li.item_id, li.item_name,
                    li.qty, li.price_cents, li.sale_rate, li.matched,
                    lots.title AS lot_title
                FROM listing_items li
                JOIN lots ON lots.id = li.lot_id
                WHERE li.bl_lot_id != ''
                ORDER BY li.lot_id, li.id
                """
            )
        ]
    changes = []
    matched = 0
    unchanged = 0
    missing_on_bl = []
    missing_matched_ignored = 0
    for row in rows:
        inv = bl_prices.get(row["bl_lot_id"])
        if inv is None:
            # Sold / removed on BrickLink is expected once the listing row is matched.
            if int(row.get("matched") or 0):
                missing_matched_ignored += 1
                continue
            missing_on_bl.append(
                {
                    "listing_id": row["id"],
                    "lot_id": row["lot_id"],
                    "lot_title": row["lot_title"],
                    "bl_lot_id": row["bl_lot_id"],
                    "item_id": row["item_id"],
                    "item_name": row["item_name"],
                    "qty": row["qty"],
                    "price_cents": row["price_cents"],
                }
            )
            continue
        matched += 1
        old_cents = int(row["price_cents"] or 0)
        new_cents = int(inv.get("price_cents") or 0)
        if old_cents == new_cents:
            unchanged += 1
            continue
        qty = int(row["qty"] or 0)
        changes.append(
            {
                "listing_id": row["id"],
                "lot_id": row["lot_id"],
                "lot_title": row["lot_title"],
                "bl_lot_id": row["bl_lot_id"],
                "item_id": row["item_id"],
                "item_name": row["item_name"] or inv.get("item_name") or "",
                "qty": qty,
                "old_cents": old_cents,
                "new_cents": new_cents,
                "delta_cents": new_cents - old_cents,
                "old_line_cents": old_cents * qty,
                "new_line_cents": new_cents * qty,
                "bl_sale_rate": inv.get("sale_rate") or 0,
            }
        )
    by_lot = {}
    for change in changes:
        lot_id = change["lot_id"]
        bucket = by_lot.get(lot_id)
        if bucket is None:
            bucket = {
                "lot_id": lot_id,
                "lot_title": change["lot_title"],
                "count": 0,
                "up": 0,
                "down": 0,
                "old_line_cents": 0,
                "new_line_cents": 0,
            }
            by_lot[lot_id] = bucket
        bucket["count"] += 1
        bucket["old_line_cents"] += change["old_line_cents"]
        bucket["new_line_cents"] += change["new_line_cents"]
        if change["delta_cents"] > 0:
            bucket["up"] += 1
        elif change["delta_cents"] < 0:
            bucket["down"] += 1
    lot_summaries = sorted(by_lot.values(), key=lambda row: row["lot_id"])
    return {
        "listing_count": len(rows),
        "inventory_count": len(bl_prices),
        "matched": matched,
        "unchanged": unchanged,
        "change_count": len(changes),
        "missing_count": len(missing_on_bl),
        "missing_matched_ignored": missing_matched_ignored,
        "changes": changes,
        "missing_on_bl": missing_on_bl,
        "lot_summaries": lot_summaries,
        "old_line_cents": sum(change["old_line_cents"] for change in changes),
        "new_line_cents": sum(change["new_line_cents"] for change in changes),
    }


def apply_listing_price_updates(changes: list) -> int:
    """Apply unit price updates from a preview. Returns rows updated."""
    if not changes:
        return 0
    with get_conn() as conn:
        updated = 0
        for change in changes:
            listing_id = change.get("listing_id")
            new_cents = int(change.get("new_cents") or 0)
            bl_lot_id = change.get("bl_lot_id") or ""
            cur = conn.execute(
                """
                UPDATE listing_items
                SET price_cents = ?
                WHERE id = ? AND bl_lot_id = ?
                """,
                (new_cents, listing_id, bl_lot_id),
            )
            updated += cur.rowcount
    return updated


def delete_listing_item(lot_id: int, item_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM listing_items WHERE id = ? AND lot_id = ?",
            (item_id, lot_id),
        )
        remaining = conn.execute(
            "SELECT COUNT(*) AS c FROM listing_items WHERE lot_id = ?",
            (lot_id,),
        ).fetchone()["c"]
        if remaining == 0:
            conn.execute(
                """
                UPDATE lots
                SET details_filename = '', details_imported_at = NULL
                WHERE id = ?
                """,
                (lot_id,),
            )
    return cur.rowcount > 0


def delete_lot(lot_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM listing_items WHERE lot_id = ?", (lot_id,))
        conn.execute(
            "UPDATE order_lines SET lot_id = NULL, matched_at = NULL WHERE lot_id = ?",
            (lot_id,),
        )
        conn.execute("UPDATE sales SET lot_id = NULL WHERE lot_id = ?", (lot_id,))
        conn.execute("DELETE FROM lots WHERE id = ?", (lot_id,))


def match_sales_to_lots() -> dict:
    """Match unprocessed order lines to listing items by bl_lot_id.

    Already-matched lines (lot_id set) are skipped. On match, sets the sale
    line's lot_id, records matched_at, and marks the listing row as matched.
    Lot P&L uses the sale line's live net gain.
    """
    refresh_all_line_net_gains()
    with get_conn() as conn:
        already = conn.execute(
            "SELECT COUNT(*) AS n FROM order_lines WHERE lot_id IS NOT NULL"
        ).fetchone()["n"]
        candidates = conn.execute(
            """
            SELECT
                ol.id AS line_id,
                ol.bl_lot_id,
                li.id AS listing_id,
                li.lot_id
            FROM order_lines ol
            JOIN listing_items li
              ON li.bl_lot_id = ol.bl_lot_id
             AND ol.bl_lot_id != ''
            WHERE ol.lot_id IS NULL
              AND li.id = (
                  SELECT MIN(li2.id) FROM listing_items li2
                  WHERE li2.bl_lot_id = ol.bl_lot_id
              )
            ORDER BY ol.id
            """
        ).fetchall()
        matched = 0
        listing_ids = set()
        for row in candidates:
            conn.execute(
                """
                UPDATE order_lines
                SET lot_id = ?, matched_at = datetime('now')
                WHERE id = ? AND lot_id IS NULL
                """,
                (row["lot_id"], row["line_id"]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                matched += 1
                listing_ids.add(row["listing_id"])
        if listing_ids:
            conn.executemany(
                "UPDATE listing_items SET matched = 1 WHERE id = ?",
                [(listing_id,) for listing_id in listing_ids],
            )
        still_open = conn.execute(
            """
            SELECT COUNT(*) AS n FROM order_lines
            WHERE lot_id IS NULL AND bl_lot_id != ''
            """
        ).fetchone()["n"]
    return {
        "matched": matched,
        "already_matched": already,
        "unmatched_with_id": still_open,
    }


def import_orders(parsed_orders: list) -> dict:
    imported = 0
    skipped = 0
    line_count = 0
    imported_ids = []
    with get_conn() as conn:
        existing = {
            (row["platform_key"], row["order_number"])
            for row in conn.execute("SELECT platform_key, order_number FROM orders")
        }
        for order in parsed_orders:
            key = (order["platform_key"], order["order_number"])
            if key in existing:
                skipped += 1
                continue
            cur = conn.execute(
                """
                INSERT INTO orders (
                    sold_on, sold_at, platform_key, platform, order_number, currency,
                    status, payment_method, header_lots, header_qty, header_total_cents,
                    shipping_cents, tax_cents, buyer_shipping_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["sold_on"],
                    order["sold_at"],
                    order["platform_key"],
                    order["platform"],
                    order["order_number"],
                    order.get("currency") or "USD",
                    order.get("status") or "",
                    order.get("payment_method") or "",
                    order.get("header_lots") or 0,
                    order.get("header_qty") or 0,
                    order.get("header_total_cents") or 0,
                    order.get("shipping_cents") or 0,
                    order.get("tax_cents") or 0,
                    order.get("buyer_shipping_cents") or 0,
                ),
            )
            order_id = cur.lastrowid
            conn.executemany(
                """
                INSERT INTO order_lines (
                    order_id, item_id, item_name, item_type, category_id, category_name,
                    color_id, color_name, qty, condition, price_cents,
                    image_url, boid, owl_lot_id, bl_lot_id, personal_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        order_id,
                        line.get("item_id") or "",
                        line.get("item_name") or "",
                        line.get("item_type") or "",
                        line.get("category_id") or "",
                        line.get("category_name") or "",
                        line.get("color_id") or "",
                        line.get("color_name") or "",
                        line.get("qty") or 0,
                        line.get("condition") or "",
                        line.get("price_cents") or 0,
                        line.get("image_url") or "",
                        line.get("boid") or "",
                        line.get("owl_lot_id") or "",
                        line.get("bl_lot_id") or "",
                        line.get("personal_note") or "",
                    )
                    for line in order.get("lines") or []
                ],
            )
            existing.add(key)
            imported += 1
            line_count += len(order["lines"])
            imported_ids.append(order_id)
    for order_id in imported_ids:
        persist_line_net_gains(order_id)
    return {"imported": imported, "skipped": skipped, "lines": line_count}


def list_orders():
    sql = """
        SELECT
            orders.*,
            COUNT(order_lines.id) AS line_count,
            COALESCE(SUM(order_lines.qty), 0) AS part_count,
            COALESCE(SUM(order_lines.qty * order_lines.price_cents), 0) AS lines_cents
        FROM orders
        LEFT JOIN order_lines ON order_lines.order_id = orders.id
        GROUP BY orders.id
        ORDER BY orders.sold_on DESC, orders.id DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [_enrich_order(row) for row in rows]


def get_order(order_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        lines = conn.execute(
            """
            SELECT order_lines.*, lots.title AS lot_title
            FROM order_lines
            LEFT JOIN lots ON lots.id = order_lines.lot_id
            WHERE order_lines.order_id = ?
            ORDER BY order_lines.id
            """,
            (order_id,),
        ).fetchall()
    lines = [dict(line) for line in lines]
    order = _enrich_order(
        {
            **dict(row),
            "line_count": len(lines),
            "part_count": sum(line["qty"] for line in lines),
            "lines_cents": sum(line["qty"] * line["price_cents"] for line in lines),
        }
    )
    order["lines"] = allocate_net_gain(lines, order["net_cents"])
    return order


def allocate_net_gain(lines: list, net_cents: int) -> list:
    """Split net gain across lines by share of item cost (qty × price)."""
    weights = [max(0, int(line.get("qty") or 0) * int(line.get("price_cents") or 0)) for line in lines]
    total_weight = sum(weights)
    for line, weight in zip(lines, weights):
        line["line_total_cents"] = weight
    if not lines:
        return lines
    if total_weight <= 0 or net_cents == 0:
        for line in lines:
            line["net_gain_cents"] = 0
        return lines

    rounded = [int(round(net_cents * weight / total_weight)) for weight in weights]
    drift = net_cents - sum(rounded)
    if drift != 0 and rounded:
        idx = max(range(len(weights)), key=lambda i: weights[i])
        rounded[idx] += drift
    for line, share in zip(lines, rounded):
        line["net_gain_cents"] = share
    return lines


def persist_line_net_gains(order_id: int, conn: Optional[sqlite3.Connection] = None) -> None:
    order = get_order(order_id)
    if order is None:
        return
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    try:
        for line in order["lines"]:
            conn.execute(
                "UPDATE order_lines SET net_gain_cents = ? WHERE id = ?",
                (line.get("net_gain_cents") or 0, line["id"]),
            )
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()


def update_order_costs(
    order_id: int,
    shipping_cents: int,
    other_costs_cents: int,
    packing_cents: int,
    packing_minutes: int = 0,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE orders
            SET shipping_cents = ?, other_costs_cents = ?, packing_cents = ?, packing_minutes = ?
            WHERE id = ?
            """,
            (shipping_cents, other_costs_cents, packing_cents, max(0, int(packing_minutes or 0)), order_id),
        )
    # Recompute and store line net gains after costs are committed so get_order
    # sees the new shipping/packing when allocating shares.
    persist_line_net_gains(order_id)


def refresh_all_line_net_gains() -> int:
    """Rewrite every order line's stored net_gain_cents from current order math."""
    with get_conn() as conn:
        order_ids = [row["id"] for row in conn.execute("SELECT id FROM orders")]
    for order_id in order_ids:
        persist_line_net_gains(order_id)
    return len(order_ids)


def delete_order(order_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM order_lines WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))


def unmatched_lines():
    sql = """
        SELECT order_lines.*, orders.sold_on, orders.platform, orders.order_number
        FROM order_lines
        JOIN orders ON orders.id = order_lines.order_id
        WHERE order_lines.lot_id IS NULL
        ORDER BY orders.sold_on DESC, order_lines.id DESC
    """
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def summary():
    lots = list_lots()
    orders = list_orders()
    unmatched = unmatched_lines()
    invested = sum(lot["invested_cents"] for lot in lots)
    revenue = sum(lot["revenue_cents"] for lot in lots)
    unmatched_net = sum(int(line.get("net_gain_cents") or 0) for line in unmatched)
    order_net = sum(order["net_cents"] for order in orders)
    profit = revenue - invested
    return {
        "lot_count": len(lots),
        "invested_cents": invested,
        "revenue_cents": revenue,
        "fees_cents": 0,
        "profit_cents": profit,
        "unmatched_count": len(unmatched),
        "unmatched_net_cents": unmatched_net,
        "order_count": len(orders),
        "order_net_cents": order_net,
        "lots": lots,
        "unmatched": unmatched,
        "pending_count": sum(1 for lot in lots if not lot["has_details"]),
        "ready_lots": [lot for lot in lots if lot["has_details"]],
    }


def _sold_period(order) -> tuple:
    sold = order.get("sold_on") or ""
    if len(sold) < 7 or sold[4] != "-":
        return None, None
    try:
        year = int(sold[:4])
        month = int(sold[5:7])
    except ValueError:
        return None, None
    if not 1 <= month <= 12:
        return None, None
    return year, month


def _order_bits(order) -> dict:
    sales = int(order.get("items_cents") or 0) - int(order.get("tax_cents") or 0)
    shipping = int(order.get("shipping_cents") or 0)
    packing = int(order.get("packing_cents") or 0)
    labor = int(order.get("packing_labor_cents") or 0)
    other = int(order.get("other_costs_cents") or 0)
    payment = int(order.get("payment_fee_cents") or 0)
    freedom = int(order.get("brickfreedom_fee_cents") or 0)
    blink = int(order.get("bricklink_fee_cents") or 0)
    bowl = int(order.get("brickowl_fee_cents") or 0)
    fees = payment + freedom + blink + bowl
    return {
        "sales": sales,
        "tax": int(order.get("tax_cents") or 0),
        "gross": int(order.get("items_cents") or 0),
        "shipping": shipping,
        "packing": packing,
        "labor": labor,
        "other": other,
        "payment": payment,
        "freedom": freedom,
        "blink": blink,
        "bowl": bowl,
        "fees": fees,
        "costs": shipping + packing + labor + other + fees,
        "net": int(order.get("net_cents") or 0),
        "buyer_shipping": int(order.get("buyer_shipping_cents") or 0),
    }


def _sum_bits(pairs) -> dict:
    keys = (
        "sales",
        "tax",
        "gross",
        "shipping",
        "packing",
        "labor",
        "other",
        "payment",
        "freedom",
        "blink",
        "bowl",
        "fees",
        "costs",
        "net",
        "buyer_shipping",
    )
    total = {key: 0 for key in keys}
    for _, bits in pairs:
        for key in keys:
            total[key] += bits[key]
    total["order_count"] = len(pairs)
    return total


def _share(part: int, whole: int):
    if whole <= 0:
        return None
    return int(round(part * 100 / whole))


def _public_totals(total: dict) -> dict:
    count = total["order_count"]
    return {
        "order_count": count,
        "sales_cents": total["sales"],
        "tax_cents": total["tax"],
        "gross_cents": total["gross"],
        "shipping_cents": total["shipping"],
        "packing_cents": total["packing"],
        "packing_labor_cents": total["labor"],
        "other_cents": total["other"],
        "payment_cents": total["payment"],
        "freedom_cents": total["freedom"],
        "blink_cents": total["blink"],
        "bowl_cents": total["bowl"],
        "fee_cents": total["fees"],
        "cost_cents": total["costs"],
        "controllable_cents": total["shipping"] + total["packing"] + total["labor"] + total["other"],
        "net_cents": total["net"],
        "buyer_shipping_cents": total["buyer_shipping"],
        "margin": _share(total["net"], total["sales"]),
        "ship_share": _share(total["shipping"], total["sales"]),
        "per_order_cents": int(round(total["net"] / count)) if count else 0,
    }


def _labeled_totals(label: str, pairs, **extra) -> dict:
    row = _public_totals(_sum_bits(pairs))
    row["label"] = label
    row["unshipped_count"] = sum(1 for _, bits in pairs if bits["shipping"] <= 0 and bits["sales"] > 0)
    row.update(extra)
    return row


def _order_row(order, bits) -> dict:
    share = _share(bits["shipping"], bits["sales"])
    return {
        "id": order["id"],
        "order_number": order.get("order_number") or "",
        "platform": "BL" if order.get("is_bricklink") else "BO",
        "sold_on": order.get("sold_on") or "",
        "sales_cents": bits["sales"],
        "shipping_cents": bits["shipping"],
        "packing_cents": bits["packing"],
        "packing_labor_cents": bits["labor"],
        "fee_cents": bits["fees"],
        "net_cents": bits["net"],
        "ship_share": share,
        "thin": share is not None and share >= 25,
    }


def _lever(kicker: str, title: str, body: str, impact: int, loss: bool = False, impact_label: str = "") -> dict:
    return {
        "kicker": kicker,
        "title": title,
        "body": body,
        "impact_cents": impact,
        "impact_label": impact_label,
        "tone": "down" if loss else "up",
    }


def _profit_levers(pairs) -> list:
    """Dollar changes that would move profit: shipping, packing, and checkout fees."""
    if not pairs:
        return []
    total = _sum_bits(pairs)
    count = total["order_count"]
    levers = []

    heavy = [
        (order, bits)
        for order, bits in pairs
        if (_share(bits["shipping"], bits["sales"]) or 0) >= 25
    ]
    excess = sum(max(0, bits["shipping"] - int(round(bits["sales"] * 0.15))) for _, bits in heavy)
    if heavy and excess >= 100:
        heavy_sales = sum(bits["sales"] for _, bits in heavy)
        heavy_ship = sum(bits["shipping"] for _, bits in heavy)
        heavy_net = sum(bits["net"] for _, bits in heavy)
        share = _share(heavy_ship, heavy_sales)
        share_bit = f"{share}% of those sales" if share is not None else "those sales"
        noun = "order" if len(heavy) == 1 else "orders"
        ships = sorted(bits["shipping"] for _, bits in heavy)
        median = ships[len(ships) // 2]
        close = sum(1 for value in ships if abs(value - median) <= 100)
        flat_bit = ""
        if close >= max(3, (len(ships) * 2) // 3):
            flat_bit = f" Most labels are about {money(median)}."
        levers.append(
            _lever(
                "Shipping",
                f"{len(heavy)} {noun} where shipping takes a quarter or more",
                (
                    f"Shipping on them was {money(heavy_ship)} ({share_bit}), "
                    f"against {money(heavy_sales)} in sales and {money(heavy_net)} net."
                    f"{flat_bit} "
                    f"A cheaper label, or a higher total before you ship, is what moves this."
                ),
                excess,
                impact_label=f"About {money(excess)} if shipping were 15% of those sales",
            )
        )

    subsidized = [
        (order, bits)
        for order, bits in pairs
        if order.get("is_bricklink") and bits["shipping"] > bits["buyer_shipping"]
    ]
    gap = sum(bits["shipping"] - bits["buyer_shipping"] for _, bits in subsidized)
    if gap >= 100:
        buyer = sum(bits["buyer_shipping"] for _, bits in subsidized)
        seller = sum(bits["shipping"] for _, bits in subsidized)
        noun = "order" if len(subsidized) == 1 else "orders"
        levers.append(
            _lever(
                "Shipping price",
                f"BrickLink carrier cost more than the buyer paid on {len(subsidized)} {noun}",
                (
                    f"Buyers paid {money(buyer)} for shipping and the carrier cost {money(seller)}. "
                    f"Charging shipping closer to the carrier cost closes that gap."
                ),
                gap,
                impact_label=f"About {money(gap)} if the buyer covered the carrier",
            )
        )

    filled = {}
    for order, bits in pairs:
        if bits["shipping"] <= 0 or bits["sales"] <= 0:
            continue
        filled.setdefault(order.get("platform") or "Other", []).append((order, bits))
    eligible = [
        _labeled_totals(name, group)
        for name, group in filled.items()
        if len(group) >= 3
    ]
    eligible = [row for row in eligible if row["ship_share"] is not None]
    if len(eligible) >= 2:
        low = min(eligible, key=lambda row: row["ship_share"])
        high = max(eligible, key=lambda row: row["ship_share"])
        if high["label"] != low["label"] and high["ship_share"] - low["ship_share"] >= 5:
            target = int(round(high["sales_cents"] * low["ship_share"] / 100))
            impact = high["shipping_cents"] - target
            if impact >= 100:
                levers.append(
                    _lever(
                        "Shipping",
                        f"{high['label']} shipping is higher than {low['label']}",
                        (
                            f"On orders with a carrier cost saved, {high['label']} shipping is "
                            f"{high['ship_share']}% of sales ({money(high['shipping_cents'])}) "
                            f"and {low['label']} is {low['ship_share']}%."
                        ),
                        impact,
                        impact_label=f"About {money(impact)} if {high['label']} shipped at the {low['label']} rate",
                    )
                )

    pack_save = sum(max(0, bits["packing"] - 25) for _, bits in pairs)
    if pack_save >= 100:
        avg_pack = total["packing"] // count if count else 0
        defaults = sum(1 for _, bits in pairs if bits["packing"] == 50)
        default_bit = ""
        if defaults >= max(3, (count + 1) // 2):
            default_bit = f" {defaults} of {count} orders still use the $0.50 default."
        levers.append(
            _lever(
                "Packing",
                "Packing materials",
                (
                    f"Packing is {money(total['packing'])} ({money(avg_pack)} an order)."
                    f"{default_bit} "
                    f"At $0.25 of materials an order, the difference is the gain."
                ),
                pack_save,
                impact_label=f"About {money(pack_save)} if packing were $0.25 an order",
            )
        )

    paypal = [(order, bits) for order, bits in pairs if "paypal" in (order.get("payment_method") or "").lower()]
    if paypal:
        actual = sum(bits["payment"] for _, bits in paypal)
        alternate = sum(int(round(int(order.get("items_cents") or 0) * 0.029)) + 30 for order, _ in paypal)
        delta = actual - alternate
        if delta >= 100:
            noun = "order" if len(paypal) == 1 else "orders"
            levers.append(
                _lever(
                    "Checkout",
                    "PayPal fees versus Stripe",
                    (
                        f"{len(paypal)} PayPal {noun} paid {money(actual)} in payment fees. "
                        f"Stripe's rate on those same order totals would have been {money(alternate)}."
                    ),
                    delta,
                    impact_label=f"About {money(delta)} if those orders used Stripe's rate",
                )
            )

    losses = [(order, bits) for order, bits in pairs if bits["net"] < 0]
    drag = -sum(bits["net"] for _, bits in losses)
    if losses and drag >= 100:
        noun = "order" if len(losses) == 1 else "orders"
        levers.append(
            _lever(
                "Below zero",
                f"{len(losses)} {noun} lost money",
                (
                    f"Shipping or the price on "
                    f"{'that order' if len(losses) == 1 else 'those orders'} "
                    f"is where this period gave profit back."
                ),
                drag,
                loss=True,
            )
        )

    levers.sort(key=lambda row: row["impact_cents"], reverse=True)
    return levers


def _shipping_gaps(pairs, elsewhere_has_shipping: bool = False) -> list:
    """Orders with sales but no carrier cost, when shipping is tracked somewhere."""
    if not pairs:
        return []
    missing = [(order, bits) for order, bits in pairs if bits["shipping"] <= 0 and bits["sales"] > 0]
    if not missing:
        return []
    has_some = any(bits["shipping"] > 0 for _, bits in pairs)
    if not has_some and not elsewhere_has_shipping:
        return []
    counts = {}
    months = set()
    for order, _bits in missing:
        name = order.get("platform") or "Other"
        counts[name] = counts.get(name, 0) + 1
        sold_year, sold_month = _sold_period(order)
        if sold_year:
            months.add((sold_year, sold_month))
    parts = [f"{n} {name}" for name, n in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    if len(parts) == 1:
        mix = parts[0]
    elif len(parts) == 2:
        mix = f"{parts[0]} and {parts[1]}"
    else:
        mix = ", ".join(parts[:-1]) + f", and {parts[-1]}"
    buyer = sum(bits["buyer_shipping"] for _, bits in missing)
    buyer_bit = f" Buyers paid {money(buyer)} in shipping on these orders." if buyer else ""
    month_all_missing = True
    for order, bits in pairs:
        sold_year, sold_month = _sold_period(order)
        if (sold_year, sold_month) in months and bits["shipping"] > 0:
            month_all_missing = False
            break
    if len(months) == 1 and month_all_missing:
        sold_year, sold_month = next(iter(months))
        title = f"{calendar.month_name[sold_month]} shipping is not saved"
    else:
        noun = "order" if len(missing) == 1 else "orders"
        title = f"{len(missing)} {noun} have $0 shipping"
    noun = "order" if len(missing) == 1 else "orders"
    return [
        {
            "kicker": "Shipping not saved",
            "title": title,
            "body": (
                f"{len(missing)} {noun} ({mix}) have no carrier cost saved.{buyer_bit} "
                f"Profit on them does not include a label yet. Enter shipping on the order and this page updates."
            ),
        }
    ]


def sales_profit_report(year: Optional[int] = None, month: Optional[int] = None, all_years: bool = False) -> dict:
    """Order profit for a year or month.

    Sales are the order total after tax. Profit subtracts shipping, packing,
    other costs, and payment, BrickFreedom, BrickLink, and BrickOwl fees.
    Lot purchase cost is not included.
    """
    orders = list_orders()
    dated = []
    years = []
    seen_years = set()
    for order in orders:
        sold_year, sold_month = _sold_period(order)
        if sold_year is None:
            continue
        dated.append((order, _order_bits(order), sold_year, sold_month))
        if sold_year not in seen_years:
            seen_years.add(sold_year)
            years.append(sold_year)
    years.sort(reverse=True)

    if all_years:
        year = None
        month = None
    elif year is None and years:
        year = years[0]
    if year is None:
        month = None
    elif month is not None and not 1 <= month <= 12:
        month = None

    selected = [
        (order, bits)
        for order, bits, sold_year, sold_month in dated
        if (year is None or sold_year == year) and (month is None or sold_month == month)
    ]
    scope = "all" if year is None else "month" if month else "year"
    if year is None:
        period_label = "All years"
    elif month:
        period_label = f"{calendar.month_name[month]} {year}"
    else:
        period_label = str(year)

    month_choices = []
    if year is not None:
        counts = {}
        for _, _, sold_year, sold_month in dated:
            if sold_year == year:
                counts[sold_month] = counts.get(sold_month, 0) + 1
        month_choices = [
            {"month": sold_month, "label": calendar.month_name[sold_month], "order_count": counts[sold_month]}
            for sold_month in sorted(counts)
        ]

    buckets = []
    if scope == "year":
        by_month = {}
        for order, bits, sold_year, sold_month in dated:
            if sold_year == year:
                by_month.setdefault(sold_month, []).append((order, bits))
        for sold_month in sorted(by_month):
            buckets.append(
                _labeled_totals(
                    calendar.month_name[sold_month],
                    by_month[sold_month],
                    year=year,
                    month=sold_month,
                )
            )
    elif scope == "all":
        by_year = {}
        for order, bits, sold_year, _sold_month in dated:
            by_year.setdefault(sold_year, []).append((order, bits))
        for sold_year in sorted(by_year, reverse=True):
            buckets.append(
                _labeled_totals(str(sold_year), by_year[sold_year], year=sold_year, month=None)
            )
    peak = max((abs(bucket["net_cents"]) for bucket in buckets), default=0)
    any_shipping = any(bucket["shipping_cents"] > 0 for bucket in buckets)
    for bucket in buckets:
        bucket["bar"] = int(round(abs(bucket["net_cents"]) * 100 / peak)) if peak else 0
        bucket["shipping_missing"] = bool(
            any_shipping and bucket["order_count"] and bucket["shipping_cents"] <= 0
        )

    totals = _sum_bits(selected)
    report = _public_totals(totals)
    cost_defs = (
        ("shipping_cents", "Shipping", "You set this"),
        ("packing_cents", "Packing materials", "You set this"),
        ("packing_labor_cents", "Packing labor", "You set this"),
        ("other_cents", "Other costs", "You set this"),
        ("payment_cents", "Payment fees", "Fee"),
        ("freedom_cents", "BrickFreedom", "Fee"),
        ("blink_cents", "BrickLink fee", "Fee"),
        ("bowl_cents", "BrickOwl fee", "Fee"),
    )
    costs = []
    for key, label, kind in cost_defs:
        cents = report[key]
        if cents <= 0:
            continue
        costs.append(
            {
                "label": label,
                "kind": kind,
                "cents": cents,
                "share": _share(cents, report["sales_cents"]),
            }
        )
    costs.sort(key=lambda row: row["cents"], reverse=True)
    for row in costs:
        row["bar"] = row["share"] or 0

    by_platform = {}
    for order, bits in selected:
        by_platform.setdefault(order.get("platform") or "Other", []).append((order, bits))
    platforms = [_labeled_totals(name, pairs) for name, pairs in by_platform.items()]
    platforms.sort(key=lambda row: row["sales_cents"], reverse=True)

    rows = [_order_row(order, bits) for order, bits in selected]
    order_rows = sorted(rows, key=lambda row: (row["ship_share"] is None, -(row["ship_share"] or 0), row["net_cents"]))
    thin_rows = sorted(
        (row for row in rows if row["thin"]),
        key=lambda row: (row["ship_share"] or 0, row["shipping_cents"]),
        reverse=True,
    )
    watch_shipping = thin_rows[:15]
    watch_losses = sorted((row for row in rows if row["net_cents"] < 0), key=lambda row: row["net_cents"])[:8]

    report.update(
        {
            "years": years,
            "year": year,
            "month": month,
            "all_years": scope == "all",
            "period_label": period_label,
            "scope": scope,
            "bucket_heading": {"all": "By year", "year": "By month", "month": "Orders"}[scope],
            "month_choices": month_choices,
            "costs": costs,
            "buckets": buckets,
            "orders": order_rows if scope == "month" else [],
            "platforms": platforms,
            "levers": _profit_levers(selected),
            "gaps": _shipping_gaps(
                selected,
                elsewhere_has_shipping=any(
                    bits["shipping"] > 0
                    for _order, bits, sold_year, sold_month in dated
                    if (year is not None and sold_year != year)
                    or (month is not None and (sold_year != year or sold_month != month))
                ),
            ),
            "watch_shipping": [] if scope == "month" else watch_shipping,
            "watch_shipping_more": 0 if scope == "month" else max(0, len(thin_rows) - len(watch_shipping)),
            "watch_losses": [] if scope == "month" else watch_losses,
            "thin_count": sum(1 for row in rows if row["thin"]),
            "has_orders": bool(dated),
            "period_empty": not selected,
        }
    )
    return report


def _enrich_order(row) -> dict:
    order = dict(row)
    header_total = order.get("header_total_cents") or 0
    lines_cents = order.get("lines_cents") or 0
    items = header_total or lines_cents
    shipping = order.get("shipping_cents") or 0
    packing = order.get("packing_cents")
    packing = 50 if packing is None else int(packing)
    packing_minutes = max(0, int(order.get("packing_minutes") or 0))
    labor = packing_labor_cents(packing_minutes)
    other = order.get("other_costs_cents") or 0
    tax = order.get("tax_cents") or 0
    payment = (order.get("payment_method") or "").strip().lower()
    platform_key = (order.get("platform_key") or "").strip().lower()
    fee_cents = 0
    fee_label = ""
    fee_formula = ""
    if "paypal" in payment:
        fee_cents = int(round(items * 0.0349)) + 49
        fee_label = "PayPal fee"
        fee_formula = "(order total × 3.49%) + $0.49"
    elif "stripe" in payment:
        fee_cents = int(round(items * 0.029)) + 30
        fee_label = "Stripe fee"
        fee_formula = "(order total × 2.9%) + $0.30"
    brickfreedom_fee_cents = int(round(items * 0.01))
    brickowl_fee_cents = 0
    bricklink_fee_cents = 0
    if platform_key == "bricklink":
        buyer_shipping = order.get("buyer_shipping_cents") or 0
        item_cost_base = max(0, items - tax - buyer_shipping)
        bricklink_fee_cents = int(round(item_cost_base * 0.03))
    else:
        item_costs_cents = int(round((lines_cents or 0) / 10))
        brickowl_fee_cents = int(round(item_costs_cents * 0.0265))
    order["items_cents"] = items
    order["display_lots"] = order.get("header_lots") or order.get("line_count") or 0
    order["display_qty"] = order.get("header_qty") or order.get("part_count") or 0
    order["payment_fee_cents"] = fee_cents
    order["payment_fee_label"] = fee_label
    order["payment_fee_formula"] = fee_formula
    order["has_payment_fee"] = fee_cents > 0
    order["tax_cents"] = tax
    order["has_tax"] = tax > 0
    order["buyer_shipping_cents"] = order.get("buyer_shipping_cents") or 0
    order["packing_cents"] = packing
    order["packing_minutes"] = packing_minutes
    order["packing_labor_cents"] = labor
    order["brickfreedom_fee_cents"] = brickfreedom_fee_cents
    order["brickowl_fee_cents"] = brickowl_fee_cents
    order["bricklink_fee_cents"] = bricklink_fee_cents
    order["bricklink_fee_base_cents"] = (
        max(0, items - tax - (order.get("buyer_shipping_cents") or 0))
        if platform_key == "bricklink"
        else 0
    )
    order["is_bricklink"] = platform_key == "bricklink"
    order["is_brickowl"] = platform_key != "bricklink"
    order["net_cents"] = (
        items
        - tax
        - shipping
        - packing
        - labor
        - other
        - fee_cents
        - brickfreedom_fee_cents
        - brickowl_fee_cents
        - bricklink_fee_cents
    )
    return order


def _enrich_lot(row) -> dict:
    lot = dict(row)
    invested = (
        lot.get("cost_cents", 0)
        + lot.get("shipping_cents", 0)
        + lot.get("tax_cents", 0)
        + lot.get("handling_cents", 0)
    )
    net = lot["revenue_cents"] - lot["fees_cents"]
    profit = net - invested
    recovered = 0 if invested == 0 else min(100, int(round((net / invested) * 100)))
    has_details = int(lot.get("detail_count") or 0) > 0
    if not has_details:
        status = "Pending details"
    elif lot["sale_count"] == 0:
        status = "Unsold"
    elif profit >= 0:
        status = "Profit"
    else:
        status = "Selling"
    lot.update(
        {
            "invested_cents": invested,
            "net_cents": net,
            "profit_cents": profit,
            "recovered": recovered,
            "status": status,
            "has_details": has_details,
        }
    )
    return lot
