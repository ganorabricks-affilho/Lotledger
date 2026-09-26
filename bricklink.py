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


def call(creds: dict, path: str, params: dict = None) -> dict:
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
        "Authorization": oauth_header("GET", url, query, creds),
    }
    req = urllib.request.Request(full, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach BrickLink: {exc.reason}") from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = raw
    return {"status": status, "path": path, "url": full, "body": body}


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


def normalize_order(raw: dict, items: list, detail: dict = None) -> dict:
    detail = detail or {}
    merged = {**raw, **detail}
    order_number = str(merged.get("order_id") or "")
    sold_on, sold_at = iso_stamp(merged.get("date_ordered"))
    cost = merged.get("cost") if isinstance(merged.get("cost"), dict) else {}
    payment = merged.get("payment") if isinstance(merged.get("payment"), dict) else {}
    subtotal = cost.get("subtotal") or cost.get("disp_subtotal") or "0"
    shipping = cost.get("shipping") or "0"
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
        "header_total_cents": money_cents(subtotal),
        "shipping_cents": money_cents(shipping),
        "lines": [normalize_item(item) for item in items],
    }


def normalize_item(raw: dict) -> dict:
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_no = str(item.get("no") or "")
    color_id = str(raw.get("color_id") if raw.get("color_id") is not None else "")
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
        "color_name": color_id,
        "qty": to_int(raw.get("quantity")),
        "condition": condition,
        "price_cents": money_milli(raw.get("unit_price")),
        "image_url": image_url(item.get("type"), item_no, color_id),
        "boid": "",
        "owl_lot_id": "",
        "bl_lot_id": str(raw.get("inventory_id") or ""),
        "personal_note": str(raw.get("remarks") or ""),
    }


def image_url(item_type, item_no: str, color_id: str) -> str:
    if not item_no:
        return ""
    kind = str(item_type or "PART").upper()
    prefix = {
        "PART": "PN",
        "MINIFIG": "MN",
        "SET": "SN",
        "BOOK": "BN",
        "GEAR": "GN",
        "CATALOG": "CN",
        "INSTRUCTION": "IN",
        "ORIGINAL_BOX": "ON",
    }.get(kind, "PN")
    if kind == "PART" and color_id:
        return f"https://img.bricklink.com/ItemImage/{prefix}/{color_id}/{item_no}.png"
    return f"https://img.bricklink.com/ItemImage/{prefix}/{item_no}.png"


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
