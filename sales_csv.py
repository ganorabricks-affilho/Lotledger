import csv
import io
from collections import OrderedDict

REQUIRED = {"Date", "Order Type", "Order #", "Bricklink ID", "Quantity", "Price"}

PLATFORM_LABELS = {
    "brickowl": "BrickOwl",
    "bricklink": "BrickLink",
}


def parse_sales_csv(text: str) -> list:
    sample = (text or "").lstrip("\ufeff")
    if not sample.strip():
        raise ValueError("The CSV file is empty.")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise ValueError("The CSV has no header row.")
    headers = {name.strip() for name in reader.fieldnames if name}
    missing = REQUIRED - headers
    if missing:
        raise ValueError("CSV is missing columns: " + ", ".join(sorted(missing)))

    grouped = OrderedDict()
    for raw in reader:
        row = { (k or "").strip(): (v or "").strip() for k, v in raw.items() }
        order_type = row.get("Order Type", "").lower()
        order_number = row.get("Order #", "")
        if not order_type or not order_number:
            continue
        qty = _int(row.get("Quantity"))
        if qty <= 0:
            continue
        key = (order_type, order_number)
        if key not in grouped:
            grouped[key] = {
                "sold_on": _date(row.get("Date", "")),
                "sold_at": row.get("Date", ""),
                "platform_key": order_type,
                "platform": PLATFORM_LABELS.get(order_type, order_type.title()),
                "order_number": order_number,
                "currency": row.get("Currency") or "USD",
                "lines": [],
            }
        grouped[key]["lines"].append(
            {
                "item_id": row.get("Bricklink ID", ""),
                "item_name": row.get("Bricklink Name", ""),
                "item_type": row.get("Bricklink Type", ""),
                "category_id": row.get("Category ID", ""),
                "category_name": row.get("Category Name", ""),
                "color_id": row.get("Colour ID", ""),
                "color_name": row.get("Colour Name", ""),
                "qty": qty,
                "condition": row.get("Condition", ""),
                "price_cents": _money(row.get("Price")),
            }
        )

    orders = [order for order in grouped.values() if order["lines"]]
    if not orders:
        raise ValueError("No orders found in that CSV.")
    return orders


def _date(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return value


def _int(value: str) -> int:
    try:
        return int(float(value)) if value else 0
    except ValueError:
        return 0


def _money(value: str) -> int:
    raw = (value or "").replace("$", "").replace(",", "").strip()
    if not raw:
        return 0
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return 0
