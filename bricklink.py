import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.bricklink.com/api/store/v1"
USER_AGENT = "Lotledger/0.1 (local BrickLink import)"

CRED_KEYS = (
    "bricklink_consumer_key",
    "bricklink_consumer_secret",
    "bricklink_token",
    "bricklink_token_secret",
)

LAB_PATHS = {
    "orders",
    "orders/{order_id}",
    "orders/{order_id}/items",
    "inventories",
    "inventories/{inventory_id}",
}

LAB_METHODS = {
    "orders": ("GET",),
    "orders/{order_id}": ("GET",),
    "orders/{order_id}/items": ("GET",),
    "inventories": ("GET", "POST"),
    "inventories/{inventory_id}": ("GET", "PUT", "DELETE"),
}


def percent_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~")


def oauth_header(method: str, url: str, query: dict, creds: dict) -> str:
    oauth = {
        "oauth_consumer_key": creds["consumer_key"],
        "oauth_token": creds["token"],
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_version": "1.0",
    }
    params = {**query, **oauth}
    param_str = "&".join(
        f"{percent_encode(k)}={percent_encode(params[k])}" for k in sorted(params)
    )
    base = "&".join(
        [
            method.upper(),
            percent_encode(url),
            percent_encode(param_str),
        ]
    )
    key = f"{percent_encode(creds['consumer_secret'])}&{percent_encode(creds['token_secret'])}"
    digest = hmac.new(key.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    oauth["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    parts = ", ".join(f'{percent_encode(k)}="{percent_encode(oauth[k])}"' for k in sorted(oauth))
    return f'OAuth realm="", {parts}'


def resolve_lab_path(path: str, params: dict) -> tuple:
    """Map lab path templates to a concrete API path and leftover query params."""
    path = (path or "").strip().lstrip("/")
    if path not in LAB_PATHS:
        raise ValueError("That BrickLink path is not enabled in the lab.")
    query = dict(params or {})
    for placeholder, key in (("{order_id}", "order_id"), ("{inventory_id}", "inventory_id")):
        if placeholder in path:
            value = str(query.pop(key, "") or "").strip()
            if not value:
                raise ValueError(f"{key} is required for this endpoint.")
            if not value.isdigit():
                raise ValueError(f"{key} must be numeric.")
            path = path.replace(placeholder, value)
    return path, query


def call(creds: dict, path: str, params: dict = None, method: str = "GET", body=None, timeout: int = 45) -> dict:
    method = (method or "GET").upper()
    query = {}
    for name, value in (params or {}).items():
        if value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        query[name] = text
    url = f"{BASE}/{path.lstrip('/')}"
    full = url if not query else f"{url}?{urllib.parse.urlencode(query)}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Authorization": oauth_header(method, url, query, creds),
    }
    data = None
    if body is not None and method in ("POST", "PUT", "PATCH"):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        data = payload
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(full, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach BrickLink: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        parsed = raw
        pretty = raw
    return {
        "status": status,
        "path": path,
        "method": method,
        "url": full,
        "body": parsed,
        "pretty": pretty,
    }


def lab_call(creds: dict, path: str, params: dict = None, method: str = "GET", body=None) -> dict:
    template = (path or "").strip().lstrip("/")
    method = (method or "GET").upper()
    allowed = LAB_METHODS.get(template)
    if not allowed:
        raise ValueError("That BrickLink path is not enabled in the lab.")
    if method not in allowed:
        raise ValueError(f"{method} is not enabled for {template}.")
    resolved, query = resolve_lab_path(template, params or {})
    if method in ("POST", "PUT") and body is None:
        raise ValueError("JSON body is required for this method.")
    return call(creds, resolved, query, method=method, body=body)


def _raise_for_status(result: dict) -> None:
    body = result.get("body")
    meta = body.get("meta") if isinstance(body, dict) else None
    code = None
    if isinstance(meta, dict):
        try:
            code = int(meta.get("code"))
        except (TypeError, ValueError):
            code = None
    if result["status"] >= 400 or (code is not None and code >= 400):
        message = ""
        if isinstance(meta, dict):
            message = meta.get("description") or meta.get("message") or ""
        detail = f" {message}" if message else ""
        raise ValueError(f"BrickLink {result['path']} returned HTTP {result['status']}.{detail}")


def _data(result: dict):
    _raise_for_status(result)
    body = result.get("body")
    if isinstance(body, dict):
        return body.get("data")
    return None


def creds_from_settings(get_setting) -> dict:
    values = {key: (get_setting(key) or "").strip() for key in CRED_KEYS}
    if not all(values.values()):
        raise ValueError("Add all four BrickLink OAuth credentials in Settings first.")
    return {
        "consumer_key": values["bricklink_consumer_key"],
        "consumer_secret": values["bricklink_consumer_secret"],
        "token": values["bricklink_token"],
        "token_secret": values["bricklink_token_secret"],
    }


def list_inventories(creds: dict, params: dict = None) -> list:
    data = _data(call(creds, "inventories", params or {}, timeout=120))
    return data if isinstance(data, list) else []


def inventories_for_dates(creds: dict, created_on_list) -> list:
    """Return inventory lots whose date_created falls on any YYYY-MM-DD in the list."""
    days = sorted(
        {
            str(day or "").strip()[:10]
            for day in (created_on_list or [])
            if str(day or "").strip()
        }
    )
    if not days:
        raise ValueError("Add at least one date (YYYY-MM-DD).")
    for day in days:
        if len(day) != 10 or day[4] != "-" or day[7] != "-":
            raise ValueError(f"Invalid date {day}. Use YYYY-MM-DD.")
    day_set = set(days)
    matched = []
    for raw in list_inventories(creds):
        created = str(raw.get("date_created") or "")[:10]
        if created in day_set:
            matched.append(normalize_inventory_item(raw))
    return matched


def inventories_for_date(creds: dict, created_on: str) -> list:
    return inventories_for_dates(creds, [created_on])


def inventory_unit_prices(creds: dict) -> dict:
    """Map BrickLink inventory_id -> effective unit price cents (after sale %)."""
    prices = {}
    for raw in list_inventories(creds):
        bl_lot_id = str(raw.get("inventory_id") or "")
        if not bl_lot_id:
            continue
        sale_rate = to_int(raw.get("sale_rate"))
        unit = float(str(raw.get("unit_price") or "0").replace(",", "") or 0)
        if sale_rate > 0:
            unit = unit * (100 - sale_rate) / 100.0
        item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
        prices[bl_lot_id] = {
            "price_cents": int(round(unit * 100)),
            "sale_rate": max(0, sale_rate),
            "unit_price_raw": str(raw.get("unit_price") or ""),
            "item_id": str(item.get("no") or ""),
            "item_name": str(item.get("name") or ""),
        }
    return prices


def normalize_inventory_item(raw: dict) -> dict:
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_no = str(item.get("no") or "")
    item_type = str(item.get("type") or "")
    color_id = str(raw.get("color_id") if raw.get("color_id") is not None else "")
    color_name = str(raw.get("color_name") or color_id)
    sale_rate = to_int(raw.get("sale_rate"))
    unit = float(str(raw.get("unit_price") or "0").replace(",", "") or 0)
    if sale_rate > 0:
        unit = unit * (100 - sale_rate) / 100.0
    condition = str(raw.get("new_or_used") or "")
    if condition.upper() == "N":
        condition = "New"
    elif condition.upper() == "U":
        condition = "Used"
    return {
        "item_id": item_no,
        "item_name": str(item.get("name") or ""),
        "item_type": item_type,
        "color": color_name,
        "category": str(item.get("category_id") or item.get("categoryID") or ""),
        "qty": to_int(raw.get("quantity")),
        "price_cents": int(round(unit * 100)),
        "sale_rate": max(0, sale_rate),
        "condition": condition,
        "remarks": str(raw.get("remarks") or ""),
        "bl_lot_id": str(raw.get("inventory_id") or ""),
        "image_url": image_url(item_type, item_no, color_id),
        "date_created": str(raw.get("date_created") or ""),
    }


ITEM_TYPE_LABELS = {
    "PART": "Part",
    "MINIFIG": "Minifig",
    "SET": "Set",
    "BOOK": "Book",
    "GEAR": "Gear",
    "CATALOG": "Catalog",
    "INSTRUCTION": "Instruction",
    "ORIGINAL_BOX": "Box",
    "UNSORTED_LOT": "Unsorted lot",
}

COMPLETENESS_LABELS = {
    "C": "Complete",
    "B": "Incomplete",
    "S": "Sealed",
}

CATALOG_PREFIX = {
    "PART": "P",
    "MINIFIG": "M",
    "SET": "S",
    "BOOK": "B",
    "GEAR": "G",
    "CATALOG": "C",
    "INSTRUCTION": "I",
    "ORIGINAL_BOX": "O",
    "UNSORTED_LOT": "U",
}


def catalog_url(item_type: str, item_no: str) -> str:
    number = (item_no or "").strip()
    if not number:
        return ""
    prefix = CATALOG_PREFIX.get((item_type or "").upper(), "P")
    return (
        "https://www.bricklink.com/v2/catalog/catalogitem.page?"
        f"{prefix}={urllib.parse.quote(number)}"
    )


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _flag(value) -> int:
    if value is True or value == 1:
        return 1
    if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
        return 1
    return 0


def snapshot_item(raw: dict) -> dict:
    """One BrickLink store-inventory lot, including the raw payload."""
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_no = _text(item.get("no"))
    item_type = _text(item.get("type")).upper()
    color_id = _text(raw.get("color_id"))
    unit_price = _text(raw.get("unit_price"))
    my_cost = _text(raw.get("my_cost"))
    sale_rate = max(0, min(100, to_int(raw.get("sale_rate"))))
    return {
        "bl_inventory_id": _text(raw.get("inventory_id")),
        "item_no": item_no,
        "item_name": _text(item.get("name")),
        "item_type": item_type,
        "category_id": _text(item.get("category_id")),
        "color_id": color_id,
        "color_name": _text(raw.get("color_name")),
        "quantity": to_int(raw.get("quantity")),
        "new_or_used": _text(raw.get("new_or_used")).upper(),
        "completeness": _text(raw.get("completeness")).upper(),
        "unit_price": unit_price,
        "unit_price_milli": money_milli(unit_price),
        "bind_id": _text(raw.get("bind_id")),
        "description": _text(raw.get("description")),
        "remarks": _text(raw.get("remarks")),
        "bulk": to_int(raw.get("bulk")),
        "is_retain": _flag(raw.get("is_retain")),
        "is_stock_room": _flag(raw.get("is_stock_room")),
        "stock_room_id": _text(raw.get("stock_room_id")).upper(),
        "date_created": _text(raw.get("date_created")),
        "my_cost": my_cost,
        "my_cost_milli": money_milli(my_cost),
        "sale_rate": sale_rate,
        "tier_quantity1": to_int(raw.get("tier_quantity1")),
        "tier_price1": _text(raw.get("tier_price1")),
        "tier_quantity2": to_int(raw.get("tier_quantity2")),
        "tier_price2": _text(raw.get("tier_price2")),
        "tier_quantity3": to_int(raw.get("tier_quantity3")),
        "tier_price3": _text(raw.get("tier_price3")),
        "my_weight": _text(raw.get("my_weight")),
        "image_url": image_url(item_type, item_no, color_id) if item_no else "",
        "api_json": json.dumps(raw, ensure_ascii=False, sort_keys=True),
    }


def fetch_inventory_snapshot(creds: dict) -> list:
    rows = []
    seen = set()
    for raw in list_inventories(creds):
        if not isinstance(raw, dict):
            continue
        row = snapshot_item(raw)
        bl_id = row["bl_inventory_id"]
        if not bl_id or bl_id in seen:
            continue
        seen.add(bl_id)
        rows.append(row)
    return rows


def list_store_orders(creds: dict, limit: int) -> list:
    data = _data(call(creds, "orders", {"direction": "in"}))
    orders = data if isinstance(data, list) else []
    orders = sorted(orders, key=lambda row: str(row.get("date_ordered") or ""), reverse=True)
    return orders[: max(1, limit)]


def fetch_order(creds: dict, order_id: str) -> dict:
    data = _data(call(creds, f"orders/{order_id}"))
    return data if isinstance(data, dict) else {}


def fetch_order_items(creds: dict, order_id: str) -> list:
    data = _data(call(creds, f"orders/{order_id}/items"))
    items = []
    if not isinstance(data, list):
        return items
    for batch in data:
        if isinstance(batch, list):
            items.extend(item for item in batch if isinstance(item, dict))
        elif isinstance(batch, dict):
            items.append(batch)
    return items


def collect_new_orders(creds: dict, limit: int, existing_numbers) -> list:
    parsed = []
    for raw in list_store_orders(creds, limit):
        order_number = str(raw.get("order_id") or "")
        if not order_number or order_number in existing_numbers:
            continue
        detail = fetch_order(creds, order_number)
        time.sleep(0.12)
        items = fetch_order_items(creds, order_number)
        parsed.append(normalize_order(raw, items, detail))
        time.sleep(0.12)
    return parsed


def fetch_order_bundle(creds: dict, order_number: str, list_row: dict = None) -> dict:
    """Fetch full order + items payloads for storage / backfill."""
    detail = fetch_order(creds, order_number)
    time.sleep(0.12)
    items = fetch_order_items(creds, order_number)
    return normalize_order(list_row or {}, items, detail)


def normalize_order(raw: dict, items: list, detail: dict = None) -> dict:
    detail = detail or {}
    merged = {**raw, **detail}
    order_number = str(merged.get("order_id") or "")
    sold_on, sold_at = iso_stamp(merged.get("date_ordered"))
    cost = merged.get("cost") if isinstance(merged.get("cost"), dict) else {}
    payment = merged.get("payment") if isinstance(merged.get("payment"), dict) else {}
    subtotal_cents = money_cents(cost.get("subtotal") or cost.get("disp_subtotal") or "0")
    api_shipping_cents = money_cents(cost.get("shipping") or "0")
    grand = (
        cost.get("grand_total")
        or cost.get("grandtotal")
        or cost.get("disp_grand_total")
        or cost.get("disp_grandtotal")
    )
    tax_cents = money_cents(
        cost.get("salesTax_collected_by_bl")
        or cost.get("salesTax")
        or cost.get("vat_amount")
        or cost.get("vat")
        or "0"
    )
    if grand not in (None, ""):
        header_total = money_cents(grand)
    else:
        header_total = subtotal_cents + api_shipping_cents + tax_cents
    if tax_cents <= 0 and grand not in (None, ""):
        final = cost.get("final_total") or cost.get("disp_final_total")
        if final not in (None, ""):
            tax_cents = max(0, money_cents(grand) - money_cents(final))
    return {
        "platform_key": "bricklink",
        "platform": "BrickLink",
        "order_number": order_number,
        "sold_on": sold_on,
        "sold_at": sold_at,
        "currency": str(
            cost.get("currency_code") or payment.get("currency_code") or "USD"
        ),
        "status": str(merged.get("status") or ""),
        "payment_method": str(payment.get("method") or ""),
        "header_lots": to_int(merged.get("unique_count")),
        "header_qty": to_int(merged.get("total_count")),
        "header_total_cents": header_total,
        "tax_cents": tax_cents,
        "buyer_shipping_cents": api_shipping_cents,
        "shipping_cents": 0,
        "api_json": json.dumps(
            {"list": raw or {}, "detail": detail or {}, "items": items or []},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "lines": [normalize_item(item) for item in items],
    }


def normalize_item(raw: dict) -> dict:
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_no = str(item.get("no") or "")
    color_id = str(raw.get("color_id") if raw.get("color_id") is not None else "")
    color_name = str(raw.get("color_name") or color_id)
    condition = str(raw.get("new_or_used") or "")
    if condition.upper() == "N":
        condition = "New"
    elif condition.upper() == "U":
        condition = "Used"
    return {
        "item_id": item_no,
        "item_name": str(item.get("name") or ""),
        "item_type": str(item.get("type") or ""),
        "category_id": str(item.get("category_id") or item.get("categoryID") or ""),
        "category_name": "",
        "color_id": color_id,
        "color_name": color_name,
        "qty": to_int(raw.get("quantity")),
        "condition": condition,
        "price_cents": money_milli(
            raw.get("unit_price_final")
            or raw.get("disp_unit_price_final")
            or raw.get("unit_price")
            or raw.get("disp_unit_price")
        ),
        "image_url": image_url(item.get("type"), item_no, color_id),
        "boid": "",
        "owl_lot_id": "",
        "bl_lot_id": str(raw.get("inventory_id") or ""),
        "personal_note": str(raw.get("remarks") or ""),
        "api_json": json.dumps(raw or {}, ensure_ascii=False, separators=(",", ":")),
    }


def image_url(item_type, item_no: str, color_id: str = "") -> str:
    """Build img.bricklink.com thumbnail URL (catalogItemPic.asp is HTML, not an image)."""
    if not item_no:
        return ""
    kind = str(item_type or "PART").upper()
    color = str(color_id or "").strip() or "0"
    # New-style thumbs: TN codes use a color folder (0 for types without color).
    folder = {
        "PART": "PN",
        "MINIFIG": "MN",
        "SET": "SN",
        "BOOK": "BN",
        "GEAR": "GN",
        "CATALOG": "CN",
        "INSTRUCTION": "IN",
        "UNSORTED_LOT": "UN",
        "ORIGINAL_BOX": "ON",
    }.get(kind, "PN")
    if kind == "PART" and color == "0":
        color = "1"  # white fallback when color unknown
    return f"https://img.bricklink.com/ItemImage/{folder}/{color}/{item_no}.png"


def money_cents(value) -> int:
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return 0
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return 0


def money_milli(value) -> int:
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return 0
    try:
        return int(round(float(raw) * 1000))
    except ValueError:
        return 0


def to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def iso_stamp(value):
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10], text
    if text.isdigit():
        dt = datetime.fromtimestamp(int(text), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.isoformat()
    return text, text
