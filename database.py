import calendar
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "lotledger.db"
PRICE_SYNC_PREVIEW_PATH = DB_PATH.parent / "price_sync_preview.json"

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
    api_json TEXT NOT NULL DEFAULT '',
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
    api_json TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS store_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bl_inventory_id TEXT NOT NULL UNIQUE,
    item_no TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT '',
    category_id TEXT NOT NULL DEFAULT '',
    color_id TEXT NOT NULL DEFAULT '',
    color_name TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    new_or_used TEXT NOT NULL DEFAULT '',
    completeness TEXT NOT NULL DEFAULT '',
    unit_price TEXT NOT NULL DEFAULT '',
    unit_price_milli INTEGER NOT NULL DEFAULT 0,
    bind_id TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    remarks TEXT NOT NULL DEFAULT '',
    bulk INTEGER NOT NULL DEFAULT 0,
    is_retain INTEGER NOT NULL DEFAULT 0,
    is_stock_room INTEGER NOT NULL DEFAULT 0,
    stock_room_id TEXT NOT NULL DEFAULT '',
    date_created TEXT NOT NULL DEFAULT '',
    my_cost TEXT NOT NULL DEFAULT '',
    my_cost_milli INTEGER NOT NULL DEFAULT 0,
    sale_rate INTEGER NOT NULL DEFAULT 0,
    tier_quantity1 INTEGER NOT NULL DEFAULT 0,
    tier_price1 TEXT NOT NULL DEFAULT '',
    tier_quantity2 INTEGER NOT NULL DEFAULT 0,
    tier_price2 TEXT NOT NULL DEFAULT '',
    tier_quantity3 INTEGER NOT NULL DEFAULT 0,
    tier_price3 TEXT NOT NULL DEFAULT '',
    my_weight TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    api_json TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_store_inventory_item_no ON store_inventory(item_no);
CREATE INDEX IF NOT EXISTS idx_store_inventory_item_type ON store_inventory(item_type);

CREATE TABLE IF NOT EXISTS inventory_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    added INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS store_inventory_staging (
    bl_inventory_id TEXT PRIMARY KEY,
    item_no TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT '',
    category_id TEXT NOT NULL DEFAULT '',
    color_id TEXT NOT NULL DEFAULT '',
    color_name TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    new_or_used TEXT NOT NULL DEFAULT '',
    completeness TEXT NOT NULL DEFAULT '',
    unit_price TEXT NOT NULL DEFAULT '',
    unit_price_milli INTEGER NOT NULL DEFAULT 0,
    bind_id TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    remarks TEXT NOT NULL DEFAULT '',
    bulk INTEGER NOT NULL DEFAULT 0,
    is_retain INTEGER NOT NULL DEFAULT 0,
    is_stock_room INTEGER NOT NULL DEFAULT 0,
    stock_room_id TEXT NOT NULL DEFAULT '',
    date_created TEXT NOT NULL DEFAULT '',
    my_cost TEXT NOT NULL DEFAULT '',
    my_cost_milli INTEGER NOT NULL DEFAULT 0,
    sale_rate INTEGER NOT NULL DEFAULT 0,
    tier_quantity1 INTEGER NOT NULL DEFAULT 0,
    tier_price1 TEXT NOT NULL DEFAULT '',
    tier_quantity2 INTEGER NOT NULL DEFAULT 0,
    tier_price2 TEXT NOT NULL DEFAULT '',
    tier_quantity3 INTEGER NOT NULL DEFAULT 0,
    tier_price3 TEXT NOT NULL DEFAULT '',
    my_weight TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    api_json TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inventory_sync_batch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS minifig_price_guide (
    fig_id TEXT NOT NULL,
    guide_type TEXT NOT NULL,
    new_or_used TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    qty_avg_price_milli INTEGER,
    avg_price_milli INTEGER,
    min_price_milli INTEGER,
    max_price_milli INTEGER,
    unit_quantity INTEGER NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (fig_id, guide_type, new_or_used, currency_code)
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
        if "api_json" not in order_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN api_json TEXT NOT NULL DEFAULT ''")
        # Refresh line_cols after possible earlier alters; api_json is new.
        line_cols = {row[1] for row in conn.execute("PRAGMA table_info(order_lines)")}
        if "api_json" not in line_cols:
            conn.execute("ALTER TABLE order_lines ADD COLUMN api_json TEXT NOT NULL DEFAULT ''")
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
        conn.execute("DELETE FROM store_inventory WHERE is_stock_room = 1")
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


def inventory_age(date_created: str, today=None) -> dict:
    """Age of a store lot from BrickLink's date_created."""
    day = str(date_created or "").strip()[:10]
    try:
        added = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return {"age_label": "—", "added_on": ""}
    today = today or datetime.now().date()
    if added > today:
        return {"age_label": "today", "added_on": added.isoformat()}
    years = today.year - added.year
    months = today.month - added.month
    days = today.day - added.day
    if days < 0:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    if years > 0 and months > 0:
        label = f"{years}y {months}m"
    elif years > 0:
        label = f"{years}y"
    elif months > 0:
        label = f"{months}m"
    else:
        span = (today - added).days
        label = "today" if span == 0 else f"{span}d"
    return {"age_label": label, "added_on": added.isoformat()}


def money_input(cents: int) -> str:
    cents = cents or 0
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


PACKING_LABOR_CENTS_PER_HOUR = 1200  # $12/hour


def is_cancelled_status(status) -> bool:
    """Cancelled orders are treated as if they never happened."""
    return "cancel" in str(status or "").strip().lower()


def parse_minutes(value) -> int:
    raw = str(value or "").strip()
    if raw == "":
        return 0
    try:
        return max(0, int(round(float(raw))))
    except ValueError:
        return 0


def packing_labor_cents(minutes: int) -> int:
    """Convert packing minutes to cents at $12/hour."""
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
            """
            SELECT order_lines.id, order_lines.order_id, order_lines.lot_id, orders.status
            FROM order_lines
            JOIN orders ON orders.id = order_lines.order_id
            WHERE order_lines.lot_id IS NOT NULL
            """
        ).fetchall()
    active_matched = [row for row in matched_rows if not is_cancelled_status(row["status"])]
    gains = live_line_net_gains(row["order_id"] for row in active_matched)
    revenue_by_lot = {}
    for row in active_matched:
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
            SELECT order_lines.*, orders.sold_on, orders.platform, orders.order_number, orders.status
            FROM order_lines
            JOIN orders ON orders.id = order_lines.order_id
            WHERE order_lines.lot_id = ?
              AND instr(lower(coalesce(orders.status, '')), 'cancel') = 0
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


def save_price_sync_preview(preview: dict) -> None:
    """Persist preview outside the cookie session (payload can be hundreds of KB)."""
    PRICE_SYNC_PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICE_SYNC_PREVIEW_PATH.write_text(
        json.dumps(preview, ensure_ascii=False),
        encoding="utf-8",
    )


def load_price_sync_preview() -> Optional[dict]:
    if not PRICE_SYNC_PREVIEW_PATH.exists():
        return None
    try:
        data = json.loads(PRICE_SYNC_PREVIEW_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def clear_price_sync_preview() -> None:
    try:
        PRICE_SYNC_PREVIEW_PATH.unlink(missing_ok=True)
    except TypeError:
        # Python < 3.8
        if PRICE_SYNC_PREVIEW_PATH.exists():
            PRICE_SYNC_PREVIEW_PATH.unlink()


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


def unmatch_cancelled_orders() -> dict:
    """Detach cancelled order lines from lots and drop orphan history listings.

    Listing qty on real inventory rows is left unchanged. Synthetic listing rows
    that only existed for a cancelled sale are removed.
    """
    with get_conn() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ol.id AS line_id, ol.bl_lot_id, ol.lot_id, li.id AS listing_id
                FROM order_lines ol
                JOIN orders o ON o.id = ol.order_id
                LEFT JOIN listing_items li
                  ON li.bl_lot_id = ol.bl_lot_id
                 AND li.lot_id = ol.lot_id
                WHERE ol.lot_id IS NOT NULL
                  AND instr(lower(coalesce(o.status, '')), 'cancel') > 0
                """
            )
        ]
        unmatched_lines = 0
        removed_listings = 0
        touched_listings = set()
        for row in rows:
            conn.execute(
                """
                UPDATE order_lines
                SET lot_id = NULL, matched_at = NULL, net_gain_cents = 0
                WHERE id = ?
                """,
                (row["line_id"],),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                unmatched_lines += 1
            if row.get("listing_id"):
                touched_listings.add(row["listing_id"])

        for listing_id in touched_listings:
            still = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM order_lines ol
                JOIN orders o ON o.id = ol.order_id
                JOIN listing_items li ON li.id = ?
                WHERE ol.bl_lot_id = li.bl_lot_id
                  AND ol.lot_id = li.lot_id
                  AND instr(lower(coalesce(o.status, '')), 'cancel') = 0
                """,
                (listing_id,),
            ).fetchone()["n"]
            if still:
                continue
            # No active sales left on this listing — clear match; remove if it was
            # only created from sale history (remarks path is fine either way).
            other_active = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM order_lines ol
                JOIN orders o ON o.id = ol.order_id
                JOIN listing_items li ON li.id = ?
                WHERE ol.bl_lot_id = li.bl_lot_id
                  AND ol.bl_lot_id != ''
                  AND instr(lower(coalesce(o.status, '')), 'cancel') = 0
                """,
                (listing_id,),
            ).fetchone()["n"]
            if other_active == 0:
                conn.execute("DELETE FROM listing_items WHERE id = ?", (listing_id,))
                if conn.execute("SELECT changes()").fetchone()[0]:
                    removed_listings += 1
            else:
                conn.execute(
                    "UPDATE listing_items SET matched = 0 WHERE id = ?",
                    (listing_id,),
                )
    return {"unmatched_lines": unmatched_lines, "removed_listings": removed_listings}


def match_sales_to_lots() -> dict:
    """Match unprocessed order lines to listing items by bl_lot_id.

    Already-matched lines (lot_id set) are skipped. Cancelled orders are ignored
    and any prior matches on them are cleared. On match, sets the sale line's
    lot_id, records matched_at, and marks the listing row as matched.
    Lot P&L uses the sale line's live net gain.
    """
    cancelled = unmatch_cancelled_orders()
    refresh_all_line_net_gains()
    with get_conn() as conn:
        already = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM order_lines ol
            JOIN orders o ON o.id = ol.order_id
            WHERE ol.lot_id IS NOT NULL
              AND instr(lower(coalesce(o.status, '')), 'cancel') = 0
            """
        ).fetchone()["n"]
        candidates = conn.execute(
            """
            SELECT
                ol.id AS line_id,
                ol.bl_lot_id,
                li.id AS listing_id,
                li.lot_id
            FROM order_lines ol
            JOIN orders o ON o.id = ol.order_id
            JOIN listing_items li
              ON li.bl_lot_id = ol.bl_lot_id
             AND ol.bl_lot_id != ''
            WHERE ol.lot_id IS NULL
              AND instr(lower(coalesce(o.status, '')), 'cancel') = 0
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
            SELECT COUNT(*) AS n
            FROM order_lines ol
            JOIN orders o ON o.id = ol.order_id
            WHERE ol.lot_id IS NULL
              AND ol.bl_lot_id != ''
              AND instr(lower(coalesce(o.status, '')), 'cancel') = 0
            """
        ).fetchone()["n"]
    return {
        "matched": matched,
        "already_matched": already,
        "unmatched_with_id": still_open,
        "cancelled_unmatched": cancelled["unmatched_lines"],
        "cancelled_listings_removed": cancelled["removed_listings"],
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
                    shipping_cents, tax_cents, buyer_shipping_cents, api_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    order.get("api_json") or "",
                ),
            )
            order_id = cur.lastrowid
            conn.executemany(
                """
                INSERT INTO order_lines (
                    order_id, item_id, item_name, item_type, category_id, category_name,
                    color_id, color_name, qty, condition, price_cents,
                    image_url, boid, owl_lot_id, bl_lot_id, personal_note, api_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        line.get("api_json") or "",
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


def _match_line_api_payloads(existing_lines: list, api_lines: list) -> list:
    """Pair DB lines to normalized API lines without inventing new rows."""
    remaining = list(api_lines)
    matched = []
    for row in existing_lines:
        pick = None
        for idx, api_line in enumerate(remaining):
            bl = (row.get("bl_lot_id") or "").strip()
            owl = (row.get("owl_lot_id") or "").strip()
            if bl and bl == (api_line.get("bl_lot_id") or "").strip():
                pick = idx
                break
            if owl and owl == (api_line.get("owl_lot_id") or "").strip():
                pick = idx
                break
        if pick is None:
            for idx, api_line in enumerate(remaining):
                if (row.get("item_id") or "") == (api_line.get("item_id") or "") and int(
                    row.get("qty") or 0
                ) == int(api_line.get("qty") or 0):
                    pick = idx
                    break
        if pick is None:
            matched.append((row, None))
            continue
        matched.append((row, remaining.pop(pick)))
    return matched


def _status_refresh_done(platform_key: str, status: str) -> bool:
    """Terminal statuses we do not re-check on refresh."""
    platform = (platform_key or "").strip().lower()
    normalized = str(status or "").strip().lower()
    if platform == "brickowl" and normalized == "received":
        return True
    if platform == "bricklink" and normalized == "completed":
        return True
    return False


def order_status_periods() -> list:
    """Year/month choices that have orders, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT
                CAST(substr(sold_on, 1, 4) AS INTEGER) AS year,
                CAST(substr(sold_on, 6, 2) AS INTEGER) AS month
            FROM orders
            WHERE length(sold_on) >= 7 AND substr(sold_on, 5, 1) = '-'
            ORDER BY year DESC, month DESC
            """
        ).fetchall()
    periods = []
    years = []
    seen_years = set()
    for row in rows:
        year = int(row["year"])
        month = int(row["month"])
        if not (1 <= month <= 12):
            continue
        periods.append(
            {
                "year": year,
                "month": month,
                "key": f"{year}-{month:02d}",
                "label": f"{calendar.month_name[month]} {year}",
            }
        )
        if year not in seen_years:
            seen_years.add(year)
            years.append(year)
    return {"periods": periods, "years": years}


def refresh_order_statuses(year: Optional[int] = None, month: Optional[int] = None) -> dict:
    """Pull current status from BrickLink/BrickOwl for stored orders.

    Optionally limit to a sold_on year or year+month. Skips BrickOwl Received
    and BrickLink Completed. Updates status (and api_json status fields when
    present). Leaves costs, lines, matches, and other mapped fields unchanged.
    """
    import json
    import time

    import bricklink
    import brickowl

    if month is not None and year is None:
        raise ValueError("Pick a year when filtering by month.")
    if month is not None and not 1 <= int(month) <= 12:
        raise ValueError("Month must be between 1 and 12.")

    clauses = []
    params = []
    if year is not None:
        clauses.append("substr(sold_on, 1, 4) = ?")
        params.append(f"{int(year):04d}")
    if month is not None:
        clauses.append("substr(sold_on, 6, 2) = ?")
        params.append(f"{int(month):02d}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_conn() as conn:
        orders = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, platform_key, order_number, status, api_json, sold_on
                FROM orders
                {where}
                ORDER BY id
                """,
                params,
            )
        ]

    bl_creds = None
    owl_key = None
    checked = 0
    updated = 0
    unchanged = 0
    skipped = 0
    errors = []

    for order in orders:
        platform = (order.get("platform_key") or "").strip().lower()
        number = str(order.get("order_number") or "")
        stored = order.get("status") or ""
        if _status_refresh_done(platform, stored):
            skipped += 1
            continue
        checked += 1
        try:
            if platform == "bricklink":
                if bl_creds is None:
                    bl_creds = bricklink.creds_from_settings(get_setting)
                detail = bricklink.fetch_order(bl_creds, number)
                live = str(detail.get("status") or "")
            elif platform == "brickowl":
                if owl_key is None:
                    owl_key = get_setting("brickowl_api_key")
                    if not owl_key:
                        raise ValueError("Add your BrickOwl API key in Settings first.")
                view = brickowl.fetch_order_view(owl_key, number)
                live = str(view.get("status") or "")
            else:
                unchanged += 1
                continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{platform} #{number}: {exc}")
            continue
        finally:
            time.sleep(0.12)

        if live == stored:
            unchanged += 1
            continue

        api_json = order.get("api_json") or ""
        if api_json.strip():
            try:
                payload = json.loads(api_json)
                if platform == "bricklink":
                    if isinstance(payload.get("detail"), dict):
                        payload["detail"]["status"] = live
                    if isinstance(payload.get("list"), dict):
                        payload["list"]["status"] = live
                else:
                    if isinstance(payload.get("view"), dict):
                        payload["view"]["status"] = live
                    if isinstance(payload.get("list"), dict):
                        payload["list"]["status"] = live
                api_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            except json.JSONDecodeError:
                pass

        with get_conn() as conn:
            conn.execute(
                "UPDATE orders SET status = ?, api_json = ? WHERE id = ?",
                (live, api_json, order["id"]),
            )
        updated += 1

    if year is not None and month is not None:
        period_label = f"{calendar.month_name[int(month)]} {int(year)}"
    elif year is not None:
        period_label = str(int(year))
    else:
        period_label = "all orders"

    return {
        "checked": checked,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "errors": errors,
        "period_label": period_label,
        "order_count": len(orders),
    }


def backfill_order_api_json() -> dict:
    """Fetch live API payloads for existing orders and store them in api_json only.

    Does not change mapped order/line fields, shipping/packing, matches, or net gains.
    Skips orders that already have api_json.
    """
    import bricklink
    import brickowl

    with get_conn() as conn:
        orders = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, platform_key, order_number, api_json
                FROM orders
                ORDER BY id
                """
            )
        ]
        lines_by_order = {}
        for row in conn.execute(
            """
            SELECT id, order_id, item_id, qty, bl_lot_id, owl_lot_id, api_json
            FROM order_lines
            ORDER BY id
            """
        ):
            lines_by_order.setdefault(row["order_id"], []).append(dict(row))

    bl_creds = None
    owl_key = None
    updated_orders = 0
    updated_lines = 0
    skipped = 0
    errors = []

    for order in orders:
        if (order.get("api_json") or "").strip():
            # Still fill any empty line payloads from stored order items if present.
            skipped += 1
            continue
        platform = (order.get("platform_key") or "").strip().lower()
        number = str(order.get("order_number") or "")
        try:
            if platform == "bricklink":
                if bl_creds is None:
                    bl_creds = bricklink.creds_from_settings(get_setting)
                parsed = bricklink.fetch_order_bundle(bl_creds, number)
            elif platform == "brickowl":
                if owl_key is None:
                    owl_key = get_setting("brickowl_api_key")
                    if not owl_key:
                        raise ValueError("Add your BrickOwl API key in Settings first.")
                parsed = brickowl.fetch_order_bundle(owl_key, number)
            else:
                skipped += 1
                continue
        except Exception as exc:  # noqa: BLE001 - continue backfill for other orders
            errors.append(f"{platform} #{number}: {exc}")
            continue

        order_api = parsed.get("api_json") or ""
        pairs = _match_line_api_payloads(lines_by_order.get(order["id"], []), parsed.get("lines") or [])
        with get_conn() as conn:
            if order_api:
                conn.execute(
                    "UPDATE orders SET api_json = ? WHERE id = ? AND (api_json IS NULL OR api_json = '')",
                    (order_api, order["id"]),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    updated_orders += 1
            for row, api_line in pairs:
                if not api_line:
                    continue
                if (row.get("api_json") or "").strip():
                    continue
                line_api = api_line.get("api_json") or ""
                if not line_api:
                    continue
                conn.execute(
                    "UPDATE order_lines SET api_json = ? WHERE id = ? AND (api_json IS NULL OR api_json = '')",
                    (line_api, row["id"]),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    updated_lines += 1

    return {
        "updated_orders": updated_orders,
        "updated_lines": updated_lines,
        "skipped": skipped,
        "errors": errors,
    }


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
          AND instr(lower(coalesce(orders.status, '')), 'cancel') = 0
        ORDER BY orders.sold_on DESC, order_lines.id DESC
    """
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def summary():
    lots = list_lots()
    orders = [order for order in list_orders() if not order.get("is_cancelled")]
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


def _monthly_value_charts(dated, year: Optional[int] = None, highlight_month: Optional[int] = None) -> dict:
    """Build monthly avg order profit and avg lot-profit-per-order series."""
    buckets = {}
    for order, bits, sold_year, sold_month in dated:
        if year is not None and sold_year != year:
            continue
        key = (sold_year, sold_month)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "profit": 0,
                "orders": 0,
                "lots": 0,
                "lot_value_sum": 0,
                "lot_value_n": 0,
            }
            buckets[key] = bucket
        profit = int(bits.get("net") or 0)
        lots = max(0, int(order.get("display_lots") or 0))
        bucket["profit"] += profit
        bucket["orders"] += 1
        bucket["lots"] += lots
        if lots > 0:
            bucket["lot_value_sum"] += profit / lots
            bucket["lot_value_n"] += 1

    points = []
    for sold_year, sold_month in sorted(buckets):
        bucket = buckets[(sold_year, sold_month)]
        orders = bucket["orders"]
        lots = bucket["lots"]
        profit = bucket["profit"]
        lot_n = bucket["lot_value_n"]
        label = (
            calendar.month_abbr[sold_month]
            if year is not None
            else f"{calendar.month_abbr[sold_month]} {sold_year}"
        )
        points.append(
            {
                "year": sold_year,
                "month": sold_month,
                "label": label,
                "order_count": orders,
                "lot_count": lots,
                "profit_cents": profit,
                "avg_order_cents": int(round(profit / orders)) if orders else 0,
                "avg_lot_cents": int(round(bucket["lot_value_sum"] / lot_n)) if lot_n else 0,
                "highlight": bool(
                    year is not None
                    and highlight_month is not None
                    and sold_year == year
                    and sold_month == highlight_month
                ),
            }
        )

    def _chart(metric_key: str) -> dict:
        # Scale bars by absolute peak so negative months still render.
        peak = max((abs(int(point[metric_key])) for point in points), default=0)
        bars = []
        for point in points:
            value = int(point[metric_key])
            bars.append(
                {
                    **point,
                    "value_cents": value,
                    "height": int(round(abs(value) * 100 / peak)) if peak else 0,
                    "negative": value < 0,
                }
            )
        return {"bars": bars, "peak_cents": peak}

    return {
        "avg_order": _chart("avg_order_cents"),
        "avg_lot": _chart("avg_lot_cents"),
    }


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
        if order.get("is_cancelled"):
            continue
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
    lot_cost_cents = 0
    for lot in list_lots():
        purchased = lot.get("purchased_on") or ""
        invested = int(lot.get("invested_cents") or 0)
        if scope == "all":
            lot_cost_cents += invested
            continue
        if len(purchased) < 7 or purchased[4] != "-":
            continue
        try:
            purchased_year = int(purchased[:4])
            purchased_month = int(purchased[5:7])
        except ValueError:
            continue
        if purchased_year != year:
            continue
        if month is not None and purchased_month != month:
            continue
        lot_cost_cents += invested
    report["lot_cost_cents"] = lot_cost_cents
    report["profit_after_lot_cents"] = int(report["net_cents"]) - lot_cost_cents
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
    watch_losses = sorted((row for row in rows if row["net_cents"] < 0), key=lambda row: row["net_cents"])[:8]
    chart_year = None if scope == "all" else year
    charts = _monthly_value_charts(dated, year=chart_year, highlight_month=month)

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
            "watch_losses": [] if scope == "month" else watch_losses,
            "charts": charts,
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
    order["is_cancelled"] = is_cancelled_status(order.get("status"))
    if order["is_cancelled"]:
        # Cancelled orders do not contribute to any totals.
        order["net_cents"] = 0
        order["payment_fee_cents"] = 0
        order["has_payment_fee"] = False
        order["brickfreedom_fee_cents"] = 0
        order["brickowl_fee_cents"] = 0
        order["bricklink_fee_cents"] = 0
        order["packing_labor_cents"] = 0
    else:
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


STORE_INVENTORY_FIELDS = (
    "bl_inventory_id",
    "item_no",
    "item_name",
    "item_type",
    "category_id",
    "color_id",
    "color_name",
    "quantity",
    "new_or_used",
    "completeness",
    "unit_price",
    "unit_price_milli",
    "bind_id",
    "description",
    "remarks",
    "bulk",
    "is_retain",
    "is_stock_room",
    "stock_room_id",
    "date_created",
    "my_cost",
    "my_cost_milli",
    "sale_rate",
    "tier_quantity1",
    "tier_price1",
    "tier_quantity2",
    "tier_price2",
    "tier_quantity3",
    "tier_price3",
    "my_weight",
    "image_url",
    "api_json",
    "imported_at",
)


def _like_term(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def home_counts() -> dict:
    with get_conn() as conn:
        lots = conn.execute("SELECT COUNT(*) AS n FROM lots").fetchone()["n"]
        inventory = conn.execute(
            "SELECT COUNT(*) AS listings, COALESCE(SUM(quantity), 0) AS qty FROM store_inventory WHERE is_stock_room = 0"
        ).fetchone()
    return {
        "lot_count": lots,
        "listings": inventory["listings"],
        "qty": inventory["qty"],
    }


def minifig_price_fetched_at(fig_id: str, guide_type: str, new_or_used: str, currency_code: str) -> str:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT fetched_at FROM minifig_price_guide
            WHERE fig_id = ? AND guide_type = ? AND new_or_used = ? AND currency_code = ?
            """,
            (fig_id, guide_type, new_or_used, currency_code),
        ).fetchone()
    return row["fetched_at"] if row else ""


def load_minifig_prices(guide_type: str, new_or_used: str, currency_code: str) -> dict:
    """Saved BrickLink price-guide rows, keyed by minifigure id."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT fig_id, qty_avg_price_milli, unit_quantity, fetched_at
            FROM minifig_price_guide
            WHERE guide_type = ? AND new_or_used = ? AND currency_code = ?
            """,
            (guide_type, new_or_used, currency_code),
        ).fetchall()
    return {
        row["fig_id"]: {
            "price_milli": row["qty_avg_price_milli"],
            "unit_quantity": int(row["unit_quantity"] or 0),
            "fetched_at": row["fetched_at"],
        }
        for row in rows
    }


def save_minifig_price(row: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO minifig_price_guide (
                fig_id, guide_type, new_or_used, currency_code,
                qty_avg_price_milli, avg_price_milli, min_price_milli, max_price_milli,
                unit_quantity, total_quantity, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fig_id, guide_type, new_or_used, currency_code) DO UPDATE SET
                qty_avg_price_milli = excluded.qty_avg_price_milli,
                avg_price_milli = excluded.avg_price_milli,
                min_price_milli = excluded.min_price_milli,
                max_price_milli = excluded.max_price_milli,
                unit_quantity = excluded.unit_quantity,
                total_quantity = excluded.total_quantity,
                fetched_at = excluded.fetched_at
            """,
            (
                row["fig_id"],
                row["guide_type"],
                row["new_or_used"],
                row["currency_code"],
                row.get("qty_avg_price_milli"),
                row.get("avg_price_milli"),
                row.get("min_price_milli"),
                row.get("max_price_milli"),
                int(row.get("unit_quantity") or 0),
                int(row.get("total_quantity") or 0),
                row["fetched_at"],
            ),
        )


def _part_key(item_no: str, color_id) -> tuple[str, str]:
    color = str(color_id or "").strip()
    if color.isdigit():
        color = str(int(color))
    return ((item_no or "").strip(), color)


def inventory_part_quantities() -> dict[tuple[str, str], int]:
    """Part number and color id -> quantity on the local snapshot, including the stockroom."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT item_no, color_id, SUM(quantity) AS qty
            FROM store_inventory
            WHERE item_type = 'PART' AND quantity > 0
            GROUP BY item_no, color_id
            """
        ).fetchall()
    owned = {}
    for row in rows:
        key = _part_key(row["item_no"], row["color_id"])
        owned[key] = owned.get(key, 0) + int(row["qty"] or 0)
    return owned


def inventory_part_places() -> dict[tuple[str, str], list[dict]]:
    """Part number and color id -> inventory remarks and how many sit in each."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT item_no, color_id, remarks, SUM(quantity) AS qty
            FROM store_inventory
            WHERE item_type = 'PART' AND quantity > 0
            GROUP BY item_no, color_id, remarks
            """
        ).fetchall()
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = _part_key(row["item_no"], row["color_id"])
        remark = (row["remarks"] or "").strip()
        bucket = grouped.setdefault(key, {})
        bucket[remark] = bucket.get(remark, 0) + int(row["qty"] or 0)
    places = {}
    for key, bucket in grouped.items():
        places[key] = [
            {"remark": remark, "qty": qty}
            for remark, qty in sorted(bucket.items(), key=lambda item: item[0].lower())
        ]
    return places


def inventory_part_prices() -> dict[tuple[str, str], list[dict]]:
    """Part number and color id -> listed prices, cheapest first, after any sale."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT item_no, color_id, unit_price_milli, sale_rate, SUM(quantity) AS qty
            FROM store_inventory
            WHERE item_type = 'PART' AND quantity > 0
            GROUP BY item_no, color_id, unit_price_milli, sale_rate
            """
        ).fetchall()
    grouped: dict[tuple[str, str], dict[int, int]] = {}
    for row in rows:
        key = _part_key(row["item_no"], row["color_id"])
        unit = int(row["unit_price_milli"] or 0)
        sale = max(0, min(100, int(row["sale_rate"] or 0)))
        milli = int(round(unit * (100 - sale) / 100))
        bucket = grouped.setdefault(key, {})
        bucket[milli] = bucket.get(milli, 0) + int(row["qty"] or 0)
    prices = {}
    for key, bucket in grouped.items():
        prices[key] = [
            {"milli": milli, "qty": qty}
            for milli, qty in sorted(bucket.items())
        ]
    return prices


def inventory_summary() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS listings,
                COALESCE(SUM(quantity), 0) AS qty,
                COALESCE(SUM(CASE WHEN is_retain = 0 AND is_stock_room = 0 THEN 1 ELSE 0 END), 0)
                    AS for_sale_listings,
                COALESCE(SUM(CASE
                    WHEN is_retain = 0 AND is_stock_room = 0
                    THEN quantity * unit_price_milli * (100 - MIN(sale_rate, 100)) / 100
                    ELSE 0 END), 0) AS for_sale_milli
            FROM store_inventory
            WHERE is_stock_room = 0
            """
        ).fetchone()
        latest = conn.execute(
            "SELECT * FROM inventory_imports ORDER BY id DESC LIMIT 1"
        ).fetchone()
    summary = dict(row)
    summary["latest"] = dict(latest) if latest else None
    return summary


def get_store_inventory(bl_inventory_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM store_inventory WHERE bl_inventory_id = ?",
            (str(bl_inventory_id),),
        ).fetchone()
    return dict(row) if row else None


_INVENTORY_TIE = (
    "item_no COLLATE NOCASE, color_name COLLATE NOCASE, new_or_used, "
    "CAST(bl_inventory_id AS INTEGER)"
)

INVENTORY_SORTS = {
    "item": f"item_no COLLATE NOCASE {{dir}}, color_name COLLATE NOCASE, new_or_used, CAST(bl_inventory_id AS INTEGER)",
    "color": f"color_name COLLATE NOCASE {{dir}}, {_INVENTORY_TIE}",
    "cond": f"new_or_used {{dir}}, {_INVENTORY_TIE}",
    "qty": f"quantity {{dir}}, {_INVENTORY_TIE}",
    "price": (
        "CAST(ROUND(unit_price_milli * (100 - MIN(sale_rate, 100)) / 100.0) AS INTEGER) {dir}, "
        + _INVENTORY_TIE
    ),
    "age": f"CASE WHEN date_created = '' THEN 1 ELSE 0 END, date_created {{dir}}, {_INVENTORY_TIE}",
    "remarks": f"remarks COLLATE NOCASE {{dir}}, {_INVENTORY_TIE}",
}


def _inventory_order(sort: str, direction: str) -> str:
    if sort not in INVENTORY_SORTS:
        sort = "age"
    sql_dir = "DESC" if direction == "desc" else "ASC"
    return INVENTORY_SORTS[sort].format(dir=sql_dir)


def list_store_inventory(
    q: str = "",
    item_type: str = "",
    condition: str = "",
    stock: str = "",
    remark: Optional[str] = None,
    sort: str = "age",
    direction: str = "asc",
    page: int = 1,
    limit: int = 100,
) -> dict:
    clauses = ["is_stock_room = 0"]
    params = []
    text = (q or "").strip()
    if text:
        like = _like_term(text)
        clauses.append(
            "("
            "item_no LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\' "
            "OR remarks LIKE ? ESCAPE '\\' OR color_name LIKE ? ESCAPE '\\' "
            "OR bl_inventory_id LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([like, like, like, like, like])
    if item_type:
        clauses.append("item_type = ?")
        params.append(item_type)
    if condition:
        clauses.append("new_or_used = ?")
        params.append(condition)
    if remark is not None:
        clauses.append("remarks = ?")
        params.append(remark)
    if stock == "for_sale":
        clauses.append("is_retain = 0 AND is_stock_room = 0")
    elif stock == "retain":
        clauses.append("is_retain = 1")
    elif stock in {"A", "B", "C"}:
        clauses.append("is_stock_room = 1 AND stock_room_id = ?")
        params.append(stock)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = _inventory_order(sort, direction)
    limit = max(1, int(limit))
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM store_inventory {where}",
            params,
        ).fetchone()["n"]
        pages = max(1, (total + limit - 1) // limit) if total else 1
        page = min(max(1, int(page)), pages)
        offset = (page - 1) * limit
        rows = conn.execute(
            f"""
            SELECT * FROM store_inventory
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        types = [
            row["item_type"]
            for row in conn.execute(
                """
                SELECT DISTINCT item_type FROM store_inventory
                WHERE item_type != '' AND is_stock_room = 0
                ORDER BY item_type
                """
            )
        ]
    return {
        "rows": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "pages": pages,
        "types": types,
    }


STORAGE_SORTS = {
    "remark": "remarks COLLATE NOCASE {dir}",
    "lots": "lots {dir}, remarks COLLATE NOCASE",
    "pieces": "pieces {dir}, remarks COLLATE NOCASE",
}


def list_inventory_storage(q: str = "", sort: str = "remark", direction: str = "asc") -> dict:
    """Lots and pieces grouped by the BrickLink remark on the imported snapshot."""
    clauses = ["is_stock_room = 0"]
    params = []
    text = (q or "").strip()
    if text:
        clauses.append("remarks LIKE ? ESCAPE '\\'")
        params.append(_like_term(text))
    where = f"WHERE {' AND '.join(clauses)}"
    if sort not in STORAGE_SORTS:
        sort = "remark"
    sql_dir = "DESC" if direction == "desc" else "ASC"
    order = STORAGE_SORTS[sort].format(dir=sql_dir)
    with get_conn() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT remarks, COUNT(*) AS lots, COALESCE(SUM(quantity), 0) AS pieces
                FROM store_inventory
                {where}
                GROUP BY remarks
                ORDER BY {order}
                """,
                params,
            )
        ]
    return {
        "rows": rows,
        "locations": len(rows),
        "lots": sum(row["lots"] for row in rows),
        "pieces": sum(row["pieces"] for row in rows),
    }


def inventory_duplicate_summary() -> dict:
    """Lots that share item number, color, condition, and description."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS groups,
                   COALESCE(SUM(lot_count), 0) AS lots,
                   COALESCE(SUM(CASE WHEN price_count > 1 THEN 1 ELSE 0 END), 0) AS price_groups
            FROM (
                SELECT COUNT(*) AS lot_count,
                       COUNT(DISTINCT unit_price) AS price_count
                FROM store_inventory
                WHERE is_stock_room = 0
                GROUP BY item_no, color_id, new_or_used, description
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        summary = dict(row)
        pending = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM store_inventory AS lot
        JOIN (
            SELECT item_no, color_id, new_or_used, description,
                   MAX(unit_price_milli) AS target_milli
            FROM store_inventory
            WHERE is_stock_room = 0
            GROUP BY item_no, color_id, new_or_used, description
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT unit_price) > 1
        ) AS grp
          ON lot.item_no = grp.item_no
         AND lot.color_id = grp.color_id
         AND lot.new_or_used = grp.new_or_used
         AND lot.description = grp.description
        WHERE lot.is_stock_room = 0
          AND lot.unit_price_milli < grp.target_milli
        """
        ).fetchone()
    summary["lots_to_raise"] = pending["n"]
    return summary


def list_inventory_duplicates(
    q: str = "",
    price: str = "differs",
    page: int = 1,
    limit: int = 30,
) -> dict:
    if price not in {"differs", "same", "all"}:
        price = "differs"
    clauses = ["is_stock_room = 0"]
    params = []
    text = (q or "").strip()
    if text:
        like = _like_term(text)
        clauses.append(
            "("
            "item_no LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\' "
            "OR color_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    having = "COUNT(*) > 1"
    if price == "differs":
        having += " AND COUNT(DISTINCT unit_price) > 1"
    elif price == "same":
        having += " AND COUNT(DISTINCT unit_price) = 1"
    grouped_sql = f"""
        SELECT item_no, color_id, new_or_used, description,
               COUNT(*) AS lot_count,
               COUNT(DISTINCT unit_price) AS price_count,
               MIN(unit_price_milli) AS min_milli,
               MAX(unit_price_milli) AS max_milli,
               (MAX(unit_price_milli) - MIN(unit_price_milli)) AS spread_milli,
               SUM(quantity) AS qty,
               MAX(item_name) AS item_name,
               MAX(color_name) AS color_name,
               MAX(item_type) AS item_type,
               MAX(image_url) AS image_url
        FROM store_inventory
        {where}
        GROUP BY item_no, color_id, new_or_used, description
        HAVING {having}
    """
    limit = max(1, int(limit))
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM ({grouped_sql})",
            params,
        ).fetchone()["n"]
        pages = max(1, (total + limit - 1) // limit) if total else 1
        page = min(max(1, int(page)), pages)
        offset = (page - 1) * limit
        groups = [
            dict(row)
            for row in conn.execute(
                f"""
                {grouped_sql}
                ORDER BY spread_milli DESC, lot_count DESC, item_no
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            )
        ]
        lots_by_key = {}
        if groups:
            placeholders = ",".join("(?,?,?,?)" for _ in groups)
            key_params = [
                value
                for group in groups
                for value in (
                    group["item_no"],
                    group["color_id"],
                    group["new_or_used"],
                    group["description"],
                )
            ]
            lot_rows = conn.execute(
                f"""
                SELECT * FROM store_inventory
                WHERE is_stock_room = 0
                  AND (item_no, color_id, new_or_used, description) IN ({placeholders})
                ORDER BY unit_price_milli, CAST(bl_inventory_id AS INTEGER)
                """,
                key_params,
            ).fetchall()
            for row in lot_rows:
                key = (row["item_no"], row["color_id"], row["new_or_used"], row["description"])
                lots_by_key.setdefault(key, []).append(dict(row))
    for group in groups:
        key = (group["item_no"], group["color_id"], group["new_or_used"], group["description"])
        group["lots"] = lots_by_key.get(key, [])
    return {"groups": groups, "total": total, "page": page, "pages": pages}


def duplicate_price_updates(
    item_no: str = "",
    color_id: str = "",
    new_or_used: str = "",
    description: str = "",
    matched_group: bool = False,
) -> list:
    """Lots priced under the highest unit price in the same duplicate group."""
    clauses = ["is_stock_room = 0"]
    params = []
    if matched_group:
        clauses.extend(
            ["item_no = ?", "color_id = ?", "new_or_used = ?", "description = ?"]
        )
        params.extend([item_no, color_id, new_or_used, description])
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT bl_inventory_id, item_no, color_id, new_or_used, description,
                   unit_price, unit_price_milli
            FROM store_inventory
            {where}
            """,
            params,
        ).fetchall()
    buckets = {}
    for row in rows:
        key = (row["item_no"], row["color_id"], row["new_or_used"], row["description"])
        buckets.setdefault(key, []).append(dict(row))
    updates = []
    for lots in buckets.values():
        if len(lots) < 2:
            continue
        if len({lot["unit_price"] for lot in lots}) < 2:
            continue
        target_milli = max(int(lot["unit_price_milli"] or 0) for lot in lots)
        target_price = next(
            lot["unit_price"] for lot in lots if int(lot["unit_price_milli"] or 0) == target_milli
        )
        for lot in lots:
            if int(lot["unit_price_milli"] or 0) < target_milli:
                updates.append(
                    {
                        "bl_inventory_id": lot["bl_inventory_id"],
                        "item_no": lot["item_no"],
                        "from_price": lot["unit_price"],
                        "target_price": target_price,
                        "target_milli": target_milli,
                    }
                )
    return updates


def set_store_inventory_price(bl_inventory_id: str, unit_price: str, unit_price_milli: int) -> None:
    with get_conn() as conn:
        current = conn.execute(
            "SELECT api_json FROM store_inventory WHERE bl_inventory_id = ?",
            (bl_inventory_id,),
        ).fetchone()
        payload = {}
        if current and current["api_json"]:
            try:
                payload = json.loads(current["api_json"])
            except json.JSONDecodeError:
                payload = {}
        if isinstance(payload, dict):
            payload["unit_price"] = unit_price
        conn.execute(
            """
            UPDATE store_inventory
            SET unit_price = ?, unit_price_milli = ?, api_json = ?
            WHERE bl_inventory_id = ?
            """,
            (
                unit_price,
                int(unit_price_milli),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                bl_inventory_id,
            ),
        )


def replace_store_inventory(rows: list) -> dict:
    """Replace the BrickLink snapshot. An empty download does not wipe existing rows."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prepared = []
    seen = set()
    for row in rows:
        bl_id = str(row.get("bl_inventory_id") or "").strip()
        if not bl_id or bl_id in seen:
            continue
        seen.add(bl_id)
        prepared.append(row)
    columns = ", ".join(STORE_INVENTORY_FIELDS)
    placeholders = ", ".join("?" for _ in STORE_INVENTORY_FIELDS)
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in STORE_INVENTORY_FIELDS
        if field != "bl_inventory_id"
    )
    sql = (
        f"INSERT INTO store_inventory ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(bl_inventory_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        existing = {
            row["bl_inventory_id"]
            for row in conn.execute("SELECT bl_inventory_id FROM store_inventory")
        }
        if not prepared and existing:
            raise ValueError(
                "BrickLink returned no inventory lots. The local snapshot was left unchanged."
            )
        added = sum(1 for row in prepared if row["bl_inventory_id"] not in existing)
        updated = len(prepared) - added
        removed = existing - seen
        if prepared:
            conn.executemany(
                sql,
                [
                    tuple(
                        now if field == "imported_at" else row.get(field, "")
                        for field in STORE_INVENTORY_FIELDS
                    )
                    for row in prepared
                ],
            )
        if removed:
            conn.executemany(
                "DELETE FROM store_inventory WHERE bl_inventory_id = ?",
                [(bl_id,) for bl_id in removed],
            )
        conn.execute(
            """
            INSERT INTO inventory_imports (imported_at, row_count, added, updated, removed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, len(prepared), added, updated, len(removed)),
        )
    return {
        "imported_at": now,
        "row_count": len(prepared),
        "added": added,
        "updated": updated,
        "removed": len(removed),
    }


_INT_SYNC_FIELDS = {
    "quantity",
    "unit_price_milli",
    "bulk",
    "is_retain",
    "is_stock_room",
    "my_cost_milli",
    "sale_rate",
    "tier_quantity1",
    "tier_quantity2",
    "tier_quantity3",
}

SYNC_FIELD_LABELS = {
    "item_no": "Item number",
    "item_name": "Name",
    "item_type": "Type",
    "category_id": "Category",
    "color_id": "Color id",
    "color_name": "Color",
    "quantity": "Quantity",
    "new_or_used": "Condition",
    "completeness": "Completeness",
    "unit_price": "Price",
    "bind_id": "Bind",
    "description": "Description",
    "remarks": "Remarks",
    "bulk": "Bulk",
    "is_retain": "Retain",
    "is_stock_room": "Stockroom",
    "stock_room_id": "Stockroom id",
    "date_created": "Created",
    "my_cost": "My cost",
    "sale_rate": "Sale",
    "tier_quantity1": "Tier 1 qty",
    "tier_price1": "Tier 1 price",
    "tier_quantity2": "Tier 2 qty",
    "tier_price2": "Tier 2 price",
    "tier_quantity3": "Tier 3 qty",
    "tier_price3": "Tier 3 price",
    "my_weight": "Weight",
    "image_url": "Image",
    "api_json": "BrickLink payload",
}

SYNC_CHANGE_ORDER = (
    "quantity",
    "unit_price",
    "sale_rate",
    "my_cost",
    "new_or_used",
    "completeness",
    "color_name",
    "color_id",
    "item_no",
    "item_name",
    "item_type",
    "category_id",
    "description",
    "remarks",
    "bulk",
    "is_retain",
    "is_stock_room",
    "stock_room_id",
    "date_created",
    "bind_id",
    "tier_quantity1",
    "tier_price1",
    "tier_quantity2",
    "tier_price2",
    "tier_quantity3",
    "tier_price3",
    "my_weight",
    "image_url",
)


def _sync_value(field: str, row: dict):
    value = row.get(field)
    if field in _INT_SYNC_FIELDS:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if value is None:
        return ""
    return str(value)


def _clip_sync(value: str, limit: int = 160) -> str:
    text = value if value else "—"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _show_sync_field(field: str, row: dict) -> str:
    value = _sync_value(field, row)
    if field in {"is_retain", "is_stock_room"}:
        return "Yes" if value else "No"
    if field == "new_or_used":
        return {"N": "New", "U": "Used"}.get(value, value or "—")
    if field == "sale_rate":
        return f"{value}%"
    if field in {"quantity", "bulk"} or field.startswith("tier_quantity"):
        return f"{value:,}"
    return _clip_sync(value)


def _sync_summary(row: dict) -> dict:
    return {
        "bl_inventory_id": _sync_value("bl_inventory_id", row) if "bl_inventory_id" in row else str(row.get("bl_inventory_id") or ""),
        "item_no": _sync_value("item_no", row),
        "item_name": _sync_value("item_name", row),
        "item_type": _sync_value("item_type", row),
        "color_id": _sync_value("color_id", row),
        "color_name": _sync_value("color_name", row),
        "new_or_used": _sync_value("new_or_used", row),
        "quantity": _sync_value("quantity", row),
        "unit_price_milli": _sync_value("unit_price_milli", row),
        "remarks": _sync_value("remarks", row),
        "description": _sync_value("description", row),
        "image_url": _sync_value("image_url", row),
    }


def _price_like_change(old: dict, new: dict, text_field: str, milli_field: str, label: str):
    text_same = _sync_value(text_field, old) == _sync_value(text_field, new)
    milli_same = _sync_value(milli_field, old) == _sync_value(milli_field, new)
    if text_same and milli_same:
        return None
    if not milli_same:
        before = money3(_sync_value(milli_field, old))
        after = money3(_sync_value(milli_field, new))
    else:
        before = _clip_sync(_sync_value(text_field, old))
        after = _clip_sync(_sync_value(text_field, new))
    return {"field": text_field, "label": label, "before": before, "after": after}


def inventory_row_changes(old: dict, new: dict) -> list:
    """Fields that differ between a stored lot and the BrickLink copy."""
    found = {}
    price = _price_like_change(old, new, "unit_price", "unit_price_milli", "Price")
    if price:
        found["unit_price"] = price
    cost = _price_like_change(old, new, "my_cost", "my_cost_milli", "My cost")
    if cost:
        found["my_cost"] = cost
    skip = {
        "id",
        "bl_inventory_id",
        "imported_at",
        "unit_price",
        "unit_price_milli",
        "my_cost",
        "my_cost_milli",
        "api_json",
    }
    for field in SYNC_CHANGE_ORDER:
        if field in skip or field in found:
            continue
        if _sync_value(field, old) == _sync_value(field, new):
            continue
        found[field] = {
            "field": field,
            "label": SYNC_FIELD_LABELS.get(field, field),
            "before": _show_sync_field(field, old),
            "after": _show_sync_field(field, new),
        }
    if not found and _sync_value("api_json", old) != _sync_value("api_json", new):
        found["api_json"] = {
            "field": "api_json",
            "label": SYNC_FIELD_LABELS["api_json"],
            "before": "previous",
            "after": "updated",
        }
    ordered = [field for field in SYNC_CHANGE_ORDER if field in found]
    if "api_json" in found:
        ordered.append("api_json")
    return [found[field] for field in ordered]


def diff_store_inventory(current: dict, incoming: dict) -> dict:
    """Compare inventory maps keyed by BrickLink inventory id."""
    added = []
    removed = []
    updated = []
    unchanged = 0
    for bl_id, row in incoming.items():
        old = current.get(bl_id)
        if old is None:
            added.append(_sync_summary(row))
            continue
        changes = inventory_row_changes(old, row)
        if changes:
            item = _sync_summary(row)
            item["changes"] = changes
            updated.append(item)
        else:
            unchanged += 1
    for bl_id, row in current.items():
        if bl_id not in incoming:
            removed.append(_sync_summary(row))

    def sort_key(row):
        return (row.get("item_no") or "", row.get("color_id") or "", row.get("bl_inventory_id") or "")

    added.sort(key=sort_key)
    removed.sort(key=sort_key)
    updated.sort(key=sort_key)
    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "unchanged": unchanged,
    }


def _inventory_tuple(row: dict, imported_at: str) -> tuple:
    values = []
    for field in STORE_INVENTORY_FIELDS:
        if field == "imported_at":
            values.append(imported_at)
        elif field == "bl_inventory_id":
            values.append(str(row.get("bl_inventory_id") or "").strip())
        else:
            values.append(_sync_value(field, row))
    return tuple(values)


def _inventory_upsert_sql(table: str) -> str:
    if table not in {"store_inventory", "store_inventory_staging"}:
        raise ValueError("Unknown inventory table.")
    columns = ", ".join(STORE_INVENTORY_FIELDS)
    placeholders = ", ".join("?" for _ in STORE_INVENTORY_FIELDS)
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in STORE_INVENTORY_FIELDS
        if field != "bl_inventory_id"
    )
    return (
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(bl_inventory_id) DO UPDATE SET {updates}"
    )


def _load_inventory_map(conn, table: str) -> dict:
    if table not in {"store_inventory", "store_inventory_staging"}:
        raise ValueError("Unknown inventory table.")
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return {row["bl_inventory_id"]: dict(row) for row in rows}


def pending_inventory_sync() -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT fetched_at, row_count FROM inventory_sync_batch WHERE id = 1"
        ).fetchone()
    return dict(row) if row else None


def stage_inventory_snapshot(rows: list) -> dict:
    """Replace the temp BrickLink copy. Does not change the live inventory."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prepared = []
    seen = set()
    for row in rows:
        bl_id = str(row.get("bl_inventory_id") or "").strip()
        if not bl_id or bl_id in seen or _sync_value("is_stock_room", row):
            continue
        seen.add(bl_id)
        prepared.append(row)
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM store_inventory").fetchone()["n"]
        if not prepared and existing:
            raise ValueError(
                "BrickLink returned no inventory lots. The local snapshot was left unchanged."
            )
        had_pending = conn.execute(
            "SELECT 1 FROM inventory_sync_batch WHERE id = 1"
        ).fetchone()
        conn.execute("DELETE FROM store_inventory_staging")
        if prepared:
            conn.executemany(
                _inventory_upsert_sql("store_inventory_staging"),
                [_inventory_tuple(row, now) for row in prepared],
            )
        conn.execute(
            """
            INSERT INTO inventory_sync_batch (id, fetched_at, row_count)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                row_count = excluded.row_count
            """,
            (now, len(prepared)),
        )
    return {
        "fetched_at": now,
        "row_count": len(prepared),
        "replaced_pending": bool(had_pending),
    }


def inventory_sync_report() -> Optional[dict]:
    pending = pending_inventory_sync()
    if not pending:
        return None
    with get_conn() as conn:
        current = _load_inventory_map(conn, "store_inventory")
        incoming = _load_inventory_map(conn, "store_inventory_staging")
    report = diff_store_inventory(current, incoming)
    report["fetched_at"] = pending["fetched_at"]
    report["incoming_count"] = pending["row_count"]
    report["current_count"] = len(current)
    report["quantity_changes"] = sum(
        1 for row in report["updated"] if any(change["field"] == "quantity" for change in row["changes"])
    )
    report["price_changes"] = sum(
        1 for row in report["updated"] if any(change["field"] == "unit_price" for change in row["changes"])
    )
    return report


def apply_inventory_sync() -> dict:
    """Write the staged BrickLink copy onto the local inventory."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT fetched_at, row_count FROM inventory_sync_batch WHERE id = 1"
        ).fetchone()
        if not pending:
            raise ValueError("There is no BrickLink sync waiting for approval.")
        current = _load_inventory_map(conn, "store_inventory")
        incoming = _load_inventory_map(conn, "store_inventory_staging")
        if not incoming and current:
            raise ValueError(
                "The staged BrickLink copy is empty. The local snapshot was left unchanged."
            )
        report = diff_store_inventory(current, incoming)
        changed_ids = {row["bl_inventory_id"] for row in report["added"]}
        changed_ids.update(row["bl_inventory_id"] for row in report["updated"])
        to_write = [incoming[bl_id] for bl_id in changed_ids if bl_id in incoming]
        if to_write:
            conn.executemany(
                _inventory_upsert_sql("store_inventory"),
                [_inventory_tuple(row, now) for row in to_write],
            )
        removed_ids = [row["bl_inventory_id"] for row in report["removed"]]
        if removed_ids:
            conn.executemany(
                "DELETE FROM store_inventory WHERE bl_inventory_id = ?",
                [(bl_id,) for bl_id in removed_ids],
            )
        conn.execute(
            """
            INSERT INTO inventory_imports (imported_at, row_count, added, updated, removed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                now,
                len(incoming),
                len(report["added"]),
                len(report["updated"]),
                len(report["removed"]),
            ),
        )
        conn.execute("DELETE FROM store_inventory_staging")
        conn.execute("DELETE FROM inventory_sync_batch WHERE id = 1")
    return {
        "imported_at": now,
        "row_count": len(incoming),
        "added": len(report["added"]),
        "updated": len(report["updated"]),
        "removed": len(report["removed"]),
        "unchanged": report["unchanged"],
    }


def discard_inventory_sync() -> bool:
    with get_conn() as conn:
        pending = conn.execute("SELECT 1 FROM inventory_sync_batch WHERE id = 1").fetchone()
        conn.execute("DELETE FROM store_inventory_staging")
        conn.execute("DELETE FROM inventory_sync_batch WHERE id = 1")
    return bool(pending)
