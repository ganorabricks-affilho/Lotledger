import sqlite3
from pathlib import Path

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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listing_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'P',
    color TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    qty INTEGER NOT NULL,
    price_cents INTEGER NOT NULL DEFAULT 0,
    condition TEXT NOT NULL DEFAULT 'U',
    remarks TEXT NOT NULL DEFAULT '',
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
    other_costs_cents INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '',
    payment_method TEXT NOT NULL DEFAULT '',
    header_lots INTEGER NOT NULL DEFAULT 0,
    header_qty INTEGER NOT NULL DEFAULT 0,
    header_total_cents INTEGER NOT NULL DEFAULT 0,
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
    lot_id INTEGER,
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
        order_cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        for name, ddl in (
            ("status", "TEXT NOT NULL DEFAULT ''"),
            ("payment_method", "TEXT NOT NULL DEFAULT ''"),
            ("header_lots", "INTEGER NOT NULL DEFAULT 0"),
            ("header_qty", "INTEGER NOT NULL DEFAULT 0"),
            ("header_total_cents", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in order_cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")
        line_cols = {row[1] for row in conn.execute("PRAGMA table_info(order_lines)")}
        for name in ("image_url", "boid", "owl_lot_id", "bl_lot_id", "personal_note"):
            if name not in line_cols:
                conn.execute(f"ALTER TABLE order_lines ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        scale = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("order_line_price_scale",)
        ).fetchone()
        if not scale or scale["value"] != "milli":
            conn.execute("UPDATE order_lines SET price_cents = price_cents * 10")
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("order_line_price_scale", "milli"),
            )


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


def existing_order_numbers(platform_key: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT order_number FROM orders WHERE platform_key = ?",
            (platform_key,),
        ).fetchall()
    return {row["order_number"] for row in rows}


def list_lots():
    sql = """
        SELECT
            lots.*,
            COALESCE((SELECT SUM(qty * price_cents) FROM order_lines WHERE order_lines.lot_id = lots.id), 0) AS revenue_cents,
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
    return [_enrich_lot(row) for row in rows]


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
            ORDER BY orders.sold_on DESC, order_lines.id DESC
            """,
            (lot_id,),
        ).fetchall()
        items = conn.execute(
            """
            SELECT * FROM listing_items
            WHERE lot_id = ?
            ORDER BY item_type, item_id, color, id
            """,
            (lot_id,),
        ).fetchall()
    matched = [dict(row) for row in matched]
    revenue = sum(line["qty"] * line["price_cents"] for line in matched)
    items = [dict(item) for item in items]
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
    lot["listed_items"] = items
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
        conn.executemany(
            """
            INSERT INTO listing_items (
                lot_id, item_id, item_type, color, category, qty, price_cents, condition, remarks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    lot_id,
                    item["item_id"],
                    item["item_type"],
                    item["color"],
                    item["category"],
                    item["qty"],
                    item["price_cents"],
                    item["condition"],
                    item["remarks"],
                )
                for item in items
            ],
        )
        conn.execute(
            """
            UPDATE lots
            SET details_filename = ?, details_imported_at = datetime('now')
            WHERE id = ?
            """,
            (filename, lot_id),
        )


def delete_lot(lot_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM listing_items WHERE lot_id = ?", (lot_id,))
        conn.execute("UPDATE order_lines SET lot_id = NULL WHERE lot_id = ?", (lot_id,))
        conn.execute("UPDATE sales SET lot_id = NULL WHERE lot_id = ?", (lot_id,))
        conn.execute("DELETE FROM lots WHERE id = ?", (lot_id,))


def import_orders(parsed_orders: list) -> dict:
    imported = 0
    skipped = 0
    line_count = 0
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
                    status, payment_method, header_lots, header_qty, header_total_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    order["lines"] = lines
    return order


def update_order_costs(order_id: int, shipping_cents: int, other_costs_cents: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET shipping_cents = ?, other_costs_cents = ? WHERE id = ?",
            (shipping_cents, other_costs_cents, order_id),
        )


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
    unmatched_net = sum(line["qty"] * line["price_cents"] for line in unmatched)
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


def _enrich_order(row) -> dict:
    order = dict(row)
    header_total = order.get("header_total_cents") or 0
    lines_cents = order.get("lines_cents") or 0
    items = header_total or lines_cents
    shipping = order.get("shipping_cents") or 0
    other = order.get("other_costs_cents") or 0
    payment = (order.get("payment_method") or "").strip().lower()
    fee_cents = 0
    if "paypal" in payment:
        fee_cents = int(round(items * 0.0349)) + 49
    order["items_cents"] = items
    order["display_lots"] = order.get("header_lots") or order.get("line_count") or 0
    order["display_qty"] = order.get("header_qty") or order.get("part_count") or 0
    order["payment_fee_cents"] = fee_cents
    order["is_paypal"] = fee_cents > 0 or "paypal" in payment
    order["net_cents"] = items - shipping - other - fee_cents
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
