import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.brickowl.com/v1"
USER_AGENT = "Lotledger/0.1 (local BrickOwl import)"
ALLOWED_PATHS = {
    "order/list",
    "order/view",
    "order/items",
    "order/tax_schemes",
}


def call(api_key: str, path: str, params: dict = None) -> dict:
    if path not in ALLOWED_PATHS:
        raise ValueError("That BrickOwl path is not enabled.")
    query = {"key": api_key}
    for name, value in (params or {}).items():
        if value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        query[name] = text
    url = f"{BASE}/{path}?{urllib.parse.urlencode(query)}"
    safe_url = f"{BASE}/{path}?{urllib.parse.urlencode({k: v for k, v in query.items() if k != 'key'})}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach BrickOwl: {exc.reason}") from exc

    try:
        body = json.loads(raw)
        pretty = json.dumps(body, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        body = raw
        pretty = raw
    return {
        "status": status,
        "path": path,
        "url": safe_url,
        "body": body,
        "pretty": pretty,
    }


def list_store_orders(api_key: str, limit: int) -> list:
    result = call(
        api_key,
        "order/list",
        {"limit": str(limit), "list_type": "store", "sort_by": "created"},
    )
    _raise_for_status(result)
    return as_list(result["body"])


def fetch_order_view(api_key: str, order_id: str) -> dict:
    result = call(api_key, "order/view", {"order_id": str(order_id)})
    _raise_for_status(result)
    body = result["body"]
    return body if isinstance(body, dict) else {}


def fetch_order_items(api_key: str, order_id: str) -> list:
    result = call(api_key, "order/items", {"order_id": str(order_id)})
    _raise_for_status(result)
    return as_list(result["body"])


def collect_new_orders(api_key: str, limit: int, existing_numbers) -> list:
    parsed = []
    for raw in list_store_orders(api_key, limit):
        order_number = str(pick(raw, "order_id") or "")
        if not order_number or order_number in existing_numbers:
            continue
        view = fetch_order_view(api_key, order_number)
        time.sleep(0.12)
        items = fetch_order_items(api_key, order_number)
        parsed.append(normalize_order(raw, items, view))
        time.sleep(0.12)
    return parsed


def normalize_order(raw: dict, items: list, view: dict = None) -> dict:
    view = view or {}
    order_number = str(pick(raw, "order_id") or pick(view, "order_id") or "")
    sold_on, sold_at = unix_stamp(
        pick(raw, "order_date", "iso_order_time", "date")
        or pick(view, "order_date", "iso_order_time", "date")
    )
    return {
        "platform_key": "brickowl",
        "platform": "BrickOwl",
        "order_number": order_number,
        "sold_on": sold_on,
        "sold_at": sold_at,
        "currency": str(pick(view, "currency") or pick(raw, "currency") or "USD"),
        "status": str(pick(raw, "status") or pick(view, "status") or ""),
        "payment_method": str(pick(view, "payment_method_type", "payment_method") or ""),
        "header_lots": to_int(pick(raw, "total_lots", "lots") or pick(view, "total_lots", "lots")),
        "header_qty": to_int(
            pick(raw, "total_quantity", "quantity") or pick(view, "total_quantity", "quantity")
        ),
        "header_total_cents": money_cents(
            pick(raw, "base_order_total", "total", "grand_total")
            or pick(view, "base_order_total", "total", "grand_total")
        ),
        "lines": [normalize_item(item) for item in items],
    }


def normalize_item(raw: dict) -> dict:
    boid = str(pick(raw, "boid") or "")
    image = image_url(raw)
    return {
        "item_id": str(pick(raw, "bl_item_no", "item_id", "id") or boid),
        "item_name": str(pick(raw, "name", "item_name") or ""),
        "item_type": str(pick(raw, "type", "item_type") or ""),
        "category_id": "",
        "category_name": "",
        "color_id": str(pick(raw, "color_id") or ""),
        "color_name": str(pick(raw, "color_name", "color") or ""),
        "qty": to_int(pick(raw, "ordered_quantity", "qty", "quantity")),
        "condition": str(pick(raw, "condition") or ""),
        "price_cents": money_milli(pick(raw, "base_price", "price", "unit_price")),
        "image_url": image,
        "boid": boid,
        "owl_lot_id": str(pick(raw, "lot_id") or ""),
        "bl_lot_id": str(pick(raw, "bl_lot_id", "bllot_id") or ""),
        "personal_note": str(pick(raw, "personal_note", "note") or ""),
    }


def image_url(raw: dict) -> str:
    value = pick(raw, "image", "image_url", "img", "thumbnail", "image_small")
    if isinstance(value, dict):
        value = pick(value, "url", "src", "small", "medium", "large")
    image = str(value or "")
    if image.startswith("//"):
        return "https:" + image
    if image.startswith("/"):
        return "https://www.brickowl.com" + image
    return image


def as_list(body) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("orders", "items", "lots", "data", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return value
    return []


def pick(obj, *keys):
    if not isinstance(obj, dict):
        return ""
    lower = {str(key).lower(): value for key, value in obj.items()}
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
        value = lower.get(str(key).lower())
        if value not in (None, ""):
            return value
    return ""


def to_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


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


def unix_stamp(value):
    text = str(value or "").strip()
    if text.isdigit():
        dt = datetime.fromtimestamp(int(text), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.isoformat()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10], text
    return text, text


def _raise_for_status(result: dict) -> None:
    if result["status"] >= 400:
        raise ValueError(f"BrickOwl {result['path']} returned HTTP {result['status']}.")
