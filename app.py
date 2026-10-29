import calendar
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, session, url_for

import bricklink
import brickowl
import brickstore
import database as db
import minifig_catalog

app = Flask(__name__)
app.secret_key = "lotledger-local-dev"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
db.init_db()

SOURCES = ["BrickLink", "BrickOwl", "eBay", "Goodwill", "Facebook Marketplace", "Other"]
PLATFORMS = ["BrickLink", "BrickOwl", "eBay", "Other"]
SALE_FORMATS = [
    ("bricklink", "BrickLink"),
    ("brickowl", "BrickOwl"),
]
FORGE_GUIDE = {"guide_type": "sold", "new_or_used": "U", "currency_code": "USD"}
FORGE_PRICE_DAYS = 7
_price_refresh_lock = threading.Lock()
_price_refresh_running = False


def _nav_section() -> str:
    endpoint = request.endpoint or ""
    if endpoint in {
        "inventory",
        "inventory_detail",
        "inventory_duplicates",
        "inventory_duplicates_sync",
        "inventory_sync",
        "inventory_sync_apply",
        "inventory_sync_reject",
        "inventory_storage",
        "inventory_drawers",
        "inventory_place",
    }:
        return "inventory"
    if endpoint in {"forge", "forge_parts"}:
        return "forge"
    if endpoint == "expenses":
        return "expenses"
    if endpoint in {"settings", "brickowl_lab", "bricklink_lab"}:
        return "setup"
    if endpoint == "home":
        return "home"
    return "lotledger"


@app.context_processor
def inject_helpers():
    return {
        "money": db.money,
        "money3": db.money3,
        "money_input": db.money_input,
        "sources": SOURCES,
        "platforms": PLATFORMS,
        "sale_formats": SALE_FORMATS,
        "item_types": brickstore.ITEM_TYPES,
        "conditions": brickstore.CONDITIONS,
        "has_brickowl_key": bool(db.get_setting("brickowl_api_key")),
        "has_bricklink_creds": db.has_bricklink_creds(),
        "nav_section": _nav_section(),
    }


@app.route("/")
def home():
    return render_template("home.html", counts=db.home_counts())


@app.route("/pnl")
def dashboard():
    return render_template("dashboard.html", summary=db.summary())


@app.route("/lots", methods=["GET", "POST"])
def lots():
    if request.method == "POST":
        data, error = _lot_from_form()
        if error:
            flash(error)
            return redirect(url_for("lots"))
        lot_id = db.create_lot(data)
        flash("Lot saved as pending details. Add the BrickStore XML when the listing is ready.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    return render_template("lots.html", lots=db.list_lots(), lot=None)


@app.route("/lots/<int:lot_id>")
def lot_detail(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    return render_template("lot_detail.html", lot=lot)


@app.route("/lots/<int:lot_id>/edit", methods=["GET", "POST"])
def lot_edit(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        data, error = _lot_from_form()
        if error:
            flash(error)
            return redirect(url_for("lot_edit", lot_id=lot_id))
        db.update_lot(lot_id, data)
        flash("Lot updated.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    return render_template("lot_edit.html", lot=lot)


@app.route("/lots/<int:lot_id>/details", methods=["POST"])
def lot_details(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    if lot.get("details_locked"):
        flash("Listing details are locked. Unlock to import more.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    try:
        creds = bricklink.creds_from_settings(db.get_setting)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("settings"))
    created_on = (request.form.get("created_on") or "").strip() or lot.get("purchased_on") or ""
    try:
        items = bricklink.inventories_for_date(creds, created_on)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("lot_detail", lot_id=lot_id))
    if not items:
        flash(f"No BrickLink inventory lots found with date_created on {created_on}.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    label = f"bricklink:{created_on}"
    result = db.append_listing(lot_id, label, items)
    flash(
        f"Imported {result['added']} new lots for {created_on}"
        + (f" ({result['skipped']} already on this lot)." if result["skipped"] else ".")
    )
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/details/manual", methods=["POST"])
def lot_details_manual(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    if lot.get("details_locked"):
        flash("Listing details are locked. Unlock to add rows.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    item_id = (request.form.get("item_id") or "").strip()
    try:
        qty = int(request.form.get("qty") or 0)
    except ValueError:
        qty = 0
    if not item_id or qty <= 0:
        flash("Manual row needs an item ID and quantity greater than 0.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    try:
        sale_rate = max(0, int(request.form.get("sale_rate") or 0))
    except ValueError:
        sale_rate = 0
    unit_cents = db.parse_money(request.form.get("price"))
    if sale_rate > 0:
        unit_cents = int(round(unit_cents * (100 - sale_rate) / 100.0))
    item_type = (request.form.get("item_type") or "P").strip() or "P"
    if item_type not in brickstore.ITEM_TYPES:
        item_type = "P"
    condition = (request.form.get("condition") or "U").strip() or "U"
    if condition not in brickstore.CONDITIONS:
        condition = "U"
    item = {
        "item_id": item_id,
        "item_name": (request.form.get("item_name") or "").strip(),
        "item_type": item_type,
        "color": (request.form.get("color") or "").strip(),
        "category": (request.form.get("category") or "").strip(),
        "qty": qty,
        "price_cents": unit_cents,
        "sale_rate": sale_rate,
        "condition": condition,
        "remarks": (request.form.get("remarks") or "").strip(),
        "bl_lot_id": (request.form.get("bl_lot_id") or "").strip(),
        "image_url": (request.form.get("image_url") or "").strip(),
    }
    result = db.append_listing(lot_id, "manual", [item])
    if result["skipped"]:
        flash("That BrickLink lot ID is already on this lot.")
    else:
        flash("Listing row added.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/details/clear", methods=["POST"])
def lot_details_clear(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    if lot.get("details_locked"):
        flash("Listing details are locked. Unlock to delete rows.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    deleted = db.clear_listing(lot_id)
    flash(f"Removed {deleted} listing row{'s' if deleted != 1 else ''}. Lot is pending details again.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/details/<int:item_id>/delete", methods=["POST"])
def lot_details_item_delete(lot_id, item_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    if lot.get("details_locked"):
        flash("Listing details are locked. Unlock to delete rows.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    if db.delete_listing_item(lot_id, item_id):
        flash("Listing row deleted.")
    else:
        flash("Listing row not found.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/details/lock", methods=["POST"])
def lot_details_lock(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    locked = request.form.get("locked") == "1"
    db.set_lot_details_locked(lot_id, locked)
    flash("Listing details locked." if locked else "Listing details unlocked.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/delete", methods=["POST"])
def lot_delete(lot_id):
    db.delete_lot(lot_id)
    flash("Lot deleted. Any matched sales are now unmatched.")
    return redirect(url_for("dashboard"))


@app.route("/lots/price-sync", methods=["GET", "POST"])
def lot_price_sync():
    preview = db.load_price_sync_preview()
    if request.method == "POST":
        action = request.form.get("action") or "preview"
        if action == "reject":
            db.clear_price_sync_preview()
            flash("Price sync cancelled. Nothing was changed.")
            return redirect(url_for("lot_price_sync"))
        if action == "apply":
            pending = db.load_price_sync_preview()
            if not pending or not pending.get("changes"):
                db.clear_price_sync_preview()
                flash("No pending price changes to apply.")
                return redirect(url_for("lot_price_sync"))
            updated = db.apply_listing_price_updates(pending["changes"])
            db.clear_price_sync_preview()
            flash(f"Updated unit prices on {updated} listing row{'s' if updated != 1 else ''}.")
            return redirect(url_for("lots"))
        # preview
        try:
            creds = bricklink.creds_from_settings(db.get_setting)
        except ValueError as exc:
            flash(str(exc))
            return redirect(url_for("settings"))
        try:
            prices = bricklink.inventory_unit_prices(creds)
        except ValueError as exc:
            flash(str(exc))
            return redirect(url_for("lot_price_sync"))
        preview = db.preview_listing_price_updates(prices)
        db.save_price_sync_preview(preview)
        if preview["change_count"] == 0:
            flash(
                f"Checked {preview['matched']} listing rows against BrickLink. "
                "All matched unit prices already match. Nothing to apply."
            )
        else:
            flash(
                f"Preview ready: {preview['change_count']} price change"
                f"{'s' if preview['change_count'] != 1 else ''} pending approval."
            )
        return redirect(url_for("lot_price_sync"))
    return render_template("lot_price_sync.html", preview=preview)


def _orders_by_month(orders):
    groups = []
    index = {}
    for order in orders:
        sold_on = order.get("sold_on") or ""
        key = sold_on[:7] if len(sold_on) >= 7 else "unknown"
        group = index.get(key)
        if group is None:
            label = key
            if len(key) == 7 and key[4] == "-":
                year, month = key.split("-")
                try:
                    label = f"{calendar.month_name[int(month)]} {year}"
                except (ValueError, IndexError):
                    label = key
            group = {
                "key": key,
                "label": label,
                "orders": [],
                "qty": 0,
                "lots": 0,
                "items_cents": 0,
                "shipping_cents": 0,
                "packing_cents": 0,
                "packing_labor_cents": 0,
                "net_cents": 0,
            }
            index[key] = group
            groups.append(group)
        group["orders"].append(order)
        if order.get("is_cancelled"):
            continue
        group["qty"] += int(order.get("display_qty") or 0)
        group["lots"] += int(order.get("display_lots") or 0)
        group["items_cents"] += int(order.get("items_cents") or 0)
        group["shipping_cents"] += int(order.get("shipping_cents") or 0)
        group["packing_cents"] += int(order.get("packing_cents") or 0)
        group["packing_labor_cents"] += int(order.get("packing_labor_cents") or 0)
        group["net_cents"] += int(order.get("net_cents") or 0)
    return groups


@app.route("/profit")
def sales_profit():
    raw_year = (request.args.get("year") or "").strip()
    raw_month = (request.args.get("month") or "").strip()
    year = int(raw_year) if raw_year.isdigit() else None
    month = int(raw_month) if raw_month.isdigit() else None
    report = db.sales_profit_report(year=year, month=month, all_years=raw_year == "all")
    return render_template("sales_profit.html", report=report)


@app.route("/sales")
def sales():
    orders = db.list_orders()
    status_periods = db.order_status_periods()
    return render_template(
        "sales.html",
        orders=orders,
        month_groups=_orders_by_month(orders),
        import_limit=10,
        status_years=status_periods["years"],
        status_periods=status_periods["periods"],
    )


@app.route("/sales/match", methods=["POST"])
def sales_match():
    result = db.match_sales_to_lots()
    flash(
        f"Matched {result['matched']} sale line"
        f"{'s' if result['matched'] != 1 else ''} to lots"
        f" · {result['already_matched']} already processed"
        f" · {result['unmatched_with_id']} with BL lot ID still unmatched."
    )
    return redirect(url_for("sales"))


@app.route("/sales/refresh-status", methods=["POST"])
def sales_refresh_status():
    raw_year = (request.form.get("year") or "").strip()
    raw_month = (request.form.get("month") or "").strip()
    year = int(raw_year) if raw_year.isdigit() else None
    month = int(raw_month) if raw_month.isdigit() else None
    try:
        result = db.refresh_order_statuses(year=year, month=month)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("sales"))
    msg = (
        f"{result['period_label']}: checked {result['checked']} of {result['order_count']} order"
        f"{'s' if result['order_count'] != 1 else ''}"
        f" · updated {result['updated']}"
        f" · {result['unchanged']} unchanged"
    )
    if result.get("skipped"):
        msg += f" · {result['skipped']} skipped (BO Received / BL Completed)"
    if result["errors"]:
        msg += f" · {len(result['errors'])} failed"
    flash(msg)
    return redirect(url_for("sales"))


@app.route("/sales/brickowl", methods=["POST"])
def sales_brickowl_import():
    key = db.get_setting("brickowl_api_key")
    if not key:
        flash("Add your BrickOwl API key in Settings first.")
        return redirect(url_for("settings"))
    try:
        limit = int(request.form.get("limit") or 10)
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 100))
    try:
        existing = db.existing_order_numbers("brickowl")
        parsed = brickowl.collect_new_orders(key, limit, existing)
        result = db.import_orders(parsed)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("sales"))
    flash(
        f"Looked at the last {limit} BrickOwl orders. "
        f"Imported {result['imported']} new ({result['lines']} lots). Duplicates skipped."
    )
    return redirect(url_for("sales"))


@app.route("/sales/bricklink", methods=["POST"])
def sales_bricklink_import():
    try:
        creds = bricklink.creds_from_settings(db.get_setting)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("settings"))
    try:
        limit = int(request.form.get("limit") or 10)
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 100))
    try:
        existing = db.existing_order_numbers("bricklink")
        parsed = bricklink.collect_new_orders(creds, limit, existing)
        result = db.import_orders(parsed)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("sales"))
    flash(
        f"Looked at the last {limit} BrickLink orders. "
        f"Imported {result['imported']} new ({result['lines']} lots). Duplicates skipped."
    )
    return redirect(url_for("sales"))


@app.route("/sales/<int:order_id>")
def order_detail(order_id):
    order = db.get_order(order_id)
    if order is None:
        flash("Order not found.")
        return redirect(url_for("sales"))
    return render_template("order_detail.html", order=order)


@app.route("/sales/<int:order_id>/costs", methods=["POST"])
def order_costs(order_id):
    order = db.get_order(order_id)
    if order is None:
        flash("Order not found.")
        return redirect(url_for("sales"))
    db.update_order_costs(
        order_id,
        db.parse_money(request.form.get("shipping")),
        db.parse_money(request.form.get("other_costs")),
        db.parse_money(request.form.get("packing")),
        db.parse_minutes(request.form.get("packing_minutes")),
    )
    order = db.get_order(order_id)
    flash(
        "Shipping and packing saved. "
        f"Line net gains updated in the database (order net {db.money(order['net_cents'])})."
    )
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/sales/<int:order_id>/delete", methods=["POST"])
def order_delete(order_id):
    order = db.get_order(order_id)
    number = order["order_number"] if order else order_id
    db.delete_order(order_id)
    flash(f"Order {number} deleted. Import again to bring it back.")
    return redirect(url_for("sales"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action") or ""
        if action == "clear_brickowl":
            db.set_setting("brickowl_api_key", "")
            flash("BrickOwl API key removed.")
        elif action == "save_brickowl":
            key = request.form.get("brickowl_api_key", "").strip()
            if not key:
                flash("Paste a BrickOwl API key, or use Remove key.")
            else:
                db.set_setting("brickowl_api_key", key)
                flash("BrickOwl API key saved.")
        elif action == "clear_bricklink":
            for key in bricklink.CRED_KEYS:
                db.set_setting(key, "")
            flash("BrickLink credentials removed.")
        elif action == "save_bricklink":
            fields = {
                "bricklink_consumer_key": request.form.get("bricklink_consumer_key", "").strip(),
                "bricklink_consumer_secret": request.form.get(
                    "bricklink_consumer_secret", ""
                ).strip(),
                "bricklink_token": request.form.get("bricklink_token", "").strip(),
                "bricklink_token_secret": request.form.get(
                    "bricklink_token_secret", ""
                ).strip(),
            }
            if not all(fields.values()):
                flash("Paste all four BrickLink OAuth values to save.")
            else:
                for key, value in fields.items():
                    db.set_setting(key, value)
                flash("BrickLink credentials saved.")
        else:
            flash("Unknown settings action.")
        return redirect(url_for("settings"))
    key = db.get_setting("brickowl_api_key")
    token = db.get_setting("bricklink_token")
    return render_template(
        "settings.html",
        has_brickowl_key=bool(key),
        key_hint=f"…{key[-4:]}" if len(key) >= 4 else "",
        has_bricklink_creds=db.has_bricklink_creds(),
        bricklink_hint=f"…{token[-4:]}" if len(token) >= 4 else "",
    )


@app.route("/lab/brickowl", methods=["GET", "POST"])
def brickowl_lab():
    if request.method == "POST":
        if request.form.get("action") == "clear":
            session.pop("brickowl_key", None)
            flash("API key removed from this session.")
        else:
            key = request.form.get("key", "").strip()
            if not key:
                flash("Paste a BrickOwl API key first.")
            else:
                session["brickowl_key"] = key
                flash("API key saved in this browser session only. It is not written to disk.")
        return redirect(url_for("brickowl_lab"))
    key = session.get("brickowl_key") or ""
    return render_template(
        "brickowl_lab.html",
        has_key=bool(key),
        key_hint=f"…{key[-4:]}" if len(key) >= 4 else "",
    )


@app.route("/lab/brickowl/try", methods=["POST"])
def brickowl_try():
    key = db.get_setting("brickowl_api_key") or session.get("brickowl_key")
    if not key:
        return jsonify({"error": "Paste and save an API key first."}), 400
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    params = data.get("params") or {}
    if not isinstance(params, dict):
        return jsonify({"error": "params must be an object."}), 400
    try:
        result = brickowl.call(key, path, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/lab/bricklink")
def bricklink_lab():
    token = db.get_setting("bricklink_token")
    return render_template(
        "bricklink_lab.html",
        has_creds=db.has_bricklink_creds(),
        creds_hint=f"…{token[-4:]}" if len(token) >= 4 else "",
    )


@app.route("/lab/bricklink/try", methods=["POST"])
def bricklink_try():
    try:
        creds = bricklink.creds_from_settings(db.get_setting)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    params = data.get("params") or {}
    method = (data.get("method") or "GET").strip().upper()
    body = data.get("body")
    if not isinstance(params, dict):
        return jsonify({"error": "params must be an object."}), 400
    if body is not None and not isinstance(body, (dict, list)):
        return jsonify({"error": "body must be a JSON object or array."}), 400
    try:
        result = bricklink.lab_call(creds, path, params, method=method, body=body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


INVENTORY_PAGE_SIZE = 100
INVENTORY_STOCKS = (
    ("", "Any location"),
    ("for_sale", "For sale"),
    ("retain", "Retain"),
)


def _present_inventory(item: dict) -> dict:
    row = dict(item)
    sale_rate = max(0, min(100, int(row.get("sale_rate") or 0)))
    unit = int(row.get("unit_price_milli") or 0)
    row["sale_rate"] = sale_rate
    row["effective_milli"] = int(round(unit * (100 - sale_rate) / 100))
    item_type = row.get("item_type") or ""
    row["type_label"] = bricklink.ITEM_TYPE_LABELS.get(item_type, item_type)
    condition = (row.get("new_or_used") or "").upper()
    row["condition_label"] = {"N": "New", "U": "Used"}.get(condition, condition)
    completeness = row.get("completeness") or ""
    row["completeness_label"] = bricklink.COMPLETENESS_LABELS.get(completeness, completeness)
    if row.get("is_retain"):
        where = "Retain"
    elif row.get("is_stock_room"):
        where = f"Stockroom {row.get('stock_room_id') or ''}".strip()
    else:
        where = "For sale"
    row["where_label"] = where
    row.update(db.inventory_age(row.get("date_created") or ""))
    row["catalog_url"] = bricklink.catalog_url(item_type, row.get("item_no") or "")
    bl_id = row.get("bl_inventory_id") or ""
    row["bricklink_url"] = (
        f"https://www.bricklink.com/inventory_detail.asp?invID={bl_id}" if bl_id else ""
    )
    return row


def _inventory_filters() -> dict:
    condition = (request.args.get("condition") or "").strip().upper()
    if condition not in {"", "N", "U"}:
        condition = ""
    stock = (request.args.get("stock") or "").strip()
    if stock not in {key for key, _label in INVENTORY_STOCKS}:
        stock = ""
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    sort = (request.args.get("sort") or "age").strip()
    direction = (request.args.get("dir") or "").strip().lower()
    if sort == "oldest":
        sort, direction = "age", "asc"
    elif sort == "newest":
        sort, direction = "age", "desc"
    elif sort == "item" and direction not in {"asc", "desc"}:
        direction = "asc"
    if sort not in db.INVENTORY_SORTS:
        sort = "age"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    remark = request.args.get("remark")
    if remark is not None:
        remark = remark.strip()
    drawer = (request.args.get("drawer") or "").strip().upper()
    if not db._DRAWER_CODE.fullmatch(drawer):
        drawer = ""
    return {
        "q": (request.args.get("q") or "").strip(),
        "item_type": (request.args.get("item_type") or "").strip(),
        "condition": condition,
        "stock": stock,
        "remark": remark,
        "drawer": drawer,
        "sort": sort,
        "dir": direction,
        "page": max(1, page),
    }


@app.route("/inventory")
def inventory():
    filters = _inventory_filters()
    result = db.list_store_inventory(
        q=filters["q"],
        item_type=filters["item_type"],
        condition=filters["condition"],
        stock=filters["stock"],
        remark=filters["remark"],
        drawer=filters["drawer"],
        sort=filters["sort"],
        direction=filters["dir"],
        page=filters["page"],
        limit=INVENTORY_PAGE_SIZE,
    )
    filters["page"] = result["page"]
    return render_template(
        "inventory.html",
        items=[_present_inventory(row) for row in result["rows"]],
        result=result,
        filters=filters,
        stocks=INVENTORY_STOCKS,
        summary=db.inventory_summary(),
        type_labels=bricklink.ITEM_TYPE_LABELS,
        filters_active=any(
            filters[key] for key in ("q", "item_type", "condition", "stock", "drawer")
        )
        or filters["remark"] is not None,
        pending_sync=db.pending_inventory_sync(),
    )


# Akro Mills: left cabinet AA–AH, rows 01–07 then 08–14. Right cabinet AI–AP,
# rows 01–08 then 09–16.
# Lidl Parkside: two units, columns BA–BD. First is rows 01–08 plus a wide
# BA-09. Second is rows 10–17 plus a wide BA-18.
_DRAWER_COLUMNS = {
    "left": [f"A{letter}" for letter in "ABCDEFGH"],
    "right": [f"A{letter}" for letter in "IJKLMNOP"],
}
_DRAWER_BLOCKS = {
    "left": (range(1, 8), range(8, 15)),
    "right": (range(1, 9), range(9, 17)),
}
_PARKSIDE_COLUMNS = ["BA", "BB", "BC", "BD"]
_PARKSIDE_UNITS = (
    (range(1, 9), 9),
    (range(10, 18), 18),
)
# Minifigure drawers: two towers, D17-01–D17-12 and D17-13–D17-24.
_MINIFIG_TOWERS = (range(1, 13), range(13, 25))


def _on_drawer_map(code: str) -> bool:
    text = (code or "").strip().upper()
    if re.fullmatch(r"D17-\d{2}", text):
        return 1 <= int(text[4:]) <= 24
    if len(text) != 5 or text[2] != "-" or not text[:2].isalpha() or not text[3:].isdigit():
        return False
    column, row = text[:2], int(text[3:])
    if column in _DRAWER_COLUMNS["left"]:
        return 1 <= row <= 14
    if column in _DRAWER_COLUMNS["right"]:
        return 1 <= row <= 16
    if column in _PARKSIDE_COLUMNS:
        if (1 <= row <= 8) or (10 <= row <= 17):
            return True
        return column == "BA" and row in (9, 18)
    return False


def _bl_category_names() -> dict:
    names = db.bl_category_names()
    if names or not db.has_bricklink_creds():
        return names
    try:
        rows = bricklink.list_categories(bricklink.creds_from_settings(db.get_setting))
    except ValueError:
        return {}
    db.replace_bl_categories(rows)
    return db.bl_category_names()


def _peek_label(group: dict, names: dict) -> str:
    catalog = names.get(group["category_id"]) or ""
    kind = bricklink.ITEM_TYPE_LABELS.get(group["item_type"], group["item_type"] or "Part")
    if catalog and group["item_type"] == "PART":
        return catalog
    if catalog:
        return f"{kind} · {catalog}"
    return kind or "Other"


def _drawer_board() -> dict:
    counts = db.drawer_quantities()
    part_groups = db.drawer_part_groups()
    unavailable = db.unavailable_drawers()
    catalog_names = _bl_category_names()
    categories = db.list_drawer_categories()
    assignments = db.drawer_category_assignments()
    legend = {
        category["id"]: {**category, "drawers": 0, "pieces": 0, "lots": 0}
        for category in categories
    }
    unassigned = {
        "id": None,
        "name": "Not assigned",
        "color": "",
        "ink": "#1a1a1a",
        "max_items": None,
        "keywords": "",
        "match_label": "",
        "drawers": 0,
        "pieces": 0,
        "lots": 0,
    }
    cabinets = []
    contents = {}
    pieces = lots = filled = drawers = 0

    def take(code, track_legend=True, fixed=""):
        nonlocal pieces, lots, filled, drawers
        counted = counts.get(code, {"pieces": 0, "lots": 0, "value_milli": 0})
        category = legend.get(assignments.get(code))
        # Minifigure towers stay tan until someone assigns a part. They are
        # not an entry in the Parts list while they have no category.
        if track_legend or category:
            bucket = category or unassigned
            bucket["drawers"] += 1
            bucket["pieces"] += counted["pieces"]
            bucket["lots"] += counted["lots"]
        else:
            bucket = unassigned
        pieces += counted["pieces"]
        lots += counted["lots"]
        drawers += 1
        if counted["pieces"]:
            filled += 1
        contents[code] = sorted(
            (
                {
                    "name": _peek_label(group, catalog_names),
                    "condition": group["condition"],
                    "pieces": group["pieces"],
                    "lots": group["lots"],
                }
                for group in part_groups.get(code, [])
            ),
            key=lambda row: (
                0 if row["condition"] == "N" else 1 if row["condition"] == "U" else 2,
                -row["pieces"],
                row["name"].lower(),
            ),
        )
        return {
            "code": code,
            "category_id": bucket["id"],
            "part_label": bucket["name"],
            "color": bucket["color"],
            "ink": bucket["ink"],
            "max_items": bucket["max_items"],
            "pieces": counted["pieces"],
            "lots": counted["lots"],
            "value_milli": counted["value_milli"],
            "unavailable": code in unavailable,
            "fixed": fixed,
        }

    for side in ("left", "right"):
        blocks = []
        for rows in _DRAWER_BLOCKS[side]:
            grid = []
            for row in rows:
                grid.append([take(f"{column}-{row:02d}") for column in _DRAWER_COLUMNS[side]])
            # Rows 05–07 and 12–14 are the deep drawers on the left cabinet.
            blocks.append({"rows": grid, "tall": side == "left"})
        cabinets.append(blocks)
    parkside = []
    for rows, wide_row in _PARKSIDE_UNITS:
        parkside.append(
            {
                "rows": [
                    [take(f"{column}-{row:02d}") for column in _PARKSIDE_COLUMNS]
                    for row in rows
                ],
                "wide": take(f"BA-{wide_row:02d}"),
            }
        )
    minifig = [
        [take(f"D17-{row:02d}", track_legend=False, fixed="tan") for row in rows]
        for rows in _MINIFIG_TOWERS
    ]
    return {
        "cabinets": cabinets,
        "parkside": parkside,
        "minifig": minifig,
        "categories": categories,
        "contents": contents,
        "legend": [*legend.values(), unassigned],
        "pieces": pieces,
        "lots": lots,
        "filled": filled,
        "drawers": drawers,
    }


def _optional_max(value):
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Max each has to be a whole number.") from exc
    return number


_PLACE_IMAGE = {
    "P": "PART",
    "M": "MINIFIG",
    "S": "SET",
    "G": "GEAR",
    "B": "BOOK",
    "C": "CATALOG",
    "I": "INSTRUCTION",
    "O": "ORIGINAL_BOX",
}


def _place_images(rows):
    for row in rows:
        kind = _PLACE_IMAGE.get((row.get("item_type") or "P").upper(), "PART")
        if not row.get("image_url"):
            row["image_url"] = bricklink.image_url(kind, row.get("item_id") or "", row.get("color_id") or "")
        row["catalog_url"] = bricklink.catalog_url(kind, row.get("item_id") or "")


def _place_summary(rows):
    return {
        "count": len(rows),
        "remarks": sum(1 for row in rows if row.get("remark_changed")),
        "prices": sum(1 for row in rows if row.get("price_changed")),
        "stored": sum(1 for row in rows if row.get("kind") == "duplicate"),
        "unplaced": sum(1 for row in rows if row.get("kind") == "none"),
    }


def _read_place_edits(rows, form):
    edited = []
    errors = []
    for index, row in enumerate(rows):
        prefix = f"item-{index}-"
        qty_raw = (form.get(prefix + "qty") or "").strip()
        price_raw = (form.get(prefix + "price") or "").strip().replace("$", "").replace(",", "")
        sale_raw = (form.get(prefix + "sale") or "").strip()
        comments = (form.get(prefix + "comments") or "").strip()
        remarks = (form.get(prefix + "remarks") or "").strip()
        item = dict(row)
        try:
            qty = int(qty_raw)
            if qty < 1:
                raise ValueError
        except ValueError:
            errors.append(f"Row {index + 1}: quantity has to be at least 1.")
            qty = int(row["qty"])
        try:
            price = float(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Row {index + 1}: price has to be a number.")
            price_text = row["price"]
        else:
            price_text = f"{price:.3f}"
        if sale_raw == "":
            sale_text = ""
        else:
            try:
                sale = int(sale_raw)
                if sale < 0 or sale > 100:
                    raise ValueError
            except ValueError:
                errors.append(f"Row {index + 1}: sale has to be a whole number from 0 to 100.")
                sale_text = row["sale"]
            else:
                sale_text = "" if sale == 0 else str(sale)
        item["qty"] = qty
        item["price"] = price_text
        item["sale"] = sale_text
        item["comments"] = comments
        item["remarks"] = remarks
        item["qty_changed"] = qty != int(row["orig_qty"])
        item["price_changed"] = bricklink.money_milli(price_text) != bricklink.money_milli(row["orig_price"])
        item["sale_changed"] = sale_text != str(row["orig_sale"] or "").strip()
        item["comments_changed"] = comments != (row["orig_comments"] or "")
        item["remark_changed"] = remarks.lower() != (row["orig_remarks"] or "").strip().lower()
        edited.append(item)
    return edited, errors


def _place_page(items, error, xml, skipped):
    summary = _place_summary(items) if items else None
    return render_template(
        "inventory_place.html",
        items=items,
        error=error,
        xml=xml,
        skipped=skipped,
        summary=summary,
    )


@app.route("/inventory/place", methods=["GET", "POST"])
def inventory_place():
    if request.method == "GET":
        return _place_page(None, "", "", 0)
    action = (request.form.get("action") or "calculate").strip()
    source = request.form.get("source_xml")
    if source is None:
        source = request.form.get("xml") or ""
    try:
        parsed, skipped = brickstore.parse_place_xml(source)
    except ValueError as exc:
        if action == "copy":
            return Response(str(exc), status=400, mimetype="text/plain")
        return _place_page(None, str(exc), source, 0)
    rows = db.suggest_place_rows(parsed)
    _place_images(rows)
    if action in {"download", "copy"}:
        edited, errors = _read_place_edits(rows, request.form)
        if errors:
            message = " ".join(errors)
            if action == "copy":
                return Response(message, status=400, mimetype="text/plain")
            return _place_page(edited, message, source, skipped)
        xml = brickstore.render_place_xml(edited)
        if action == "copy":
            return Response(xml, mimetype="text/plain; charset=utf-8")
        return Response(
            xml,
            mimetype="application/xml",
            headers={"Content-Disposition": "attachment; filename=place-parts.xml"},
        )
    return _place_page(rows, "", source, skipped)


@app.route("/inventory/drawers")
def inventory_drawers():
    return render_template("drawers.html", board=_drawer_board())


@app.route("/inventory/drawers/categories", methods=["POST"])
def inventory_drawer_category():
    payload = request.get_json(silent=True) or {}
    drawer = (payload.get("drawer") or "").strip().upper()
    if drawer and not _on_drawer_map(drawer):
        return jsonify(error="That drawer is not on this map."), 400
    try:
        category = db.create_drawer_category(
            payload.get("name") or "",
            payload.get("color") or "",
            _optional_max(payload.get("max_items")),
            payload.get("keywords") or "",
        )
        if drawer:
            db.assign_drawer_category(drawer, category["id"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(category=category, drawer=drawer)


@app.route("/inventory/drawers/categories/<int:category_id>", methods=["POST"])
def inventory_drawer_category_update(category_id):
    payload = request.get_json(silent=True) or {}
    try:
        category = db.update_drawer_category(
            category_id,
            payload.get("name") or "",
            payload.get("color") or "",
            _optional_max(payload.get("max_items")),
            payload.get("keywords") or "",
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(category=category)


@app.route("/inventory/drawers/assign", methods=["POST"])
def inventory_drawer_assign():
    payload = request.get_json(silent=True) or {}
    drawer = (payload.get("drawer") or "").strip().upper()
    if not _on_drawer_map(drawer):
        return jsonify(error="That drawer is not on this map."), 400
    raw = payload.get("category_id")
    category_id = None
    if raw not in (None, ""):
        try:
            category_id = int(raw)
        except (TypeError, ValueError):
            return jsonify(error="That category is not available."), 400
    try:
        db.assign_drawer_category(drawer, category_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(drawer=drawer, category_id=category_id)


@app.route("/inventory/drawers/unavailable", methods=["POST"])
def inventory_drawer_unavailable():
    payload = request.get_json(silent=True) or {}
    drawer = (payload.get("drawer") or "").strip().upper()
    if not _on_drawer_map(drawer):
        return jsonify(error="That drawer is not on this map."), 400
    unavailable = bool(payload.get("unavailable"))
    db.set_drawer_unavailable(drawer, unavailable)
    return jsonify(drawer=drawer, unavailable=unavailable)


@app.route("/inventory/storage")
def inventory_storage():
    sort = (request.args.get("sort") or "remark").strip()
    direction = (request.args.get("dir") or "asc").strip().lower()
    if sort not in db.STORAGE_SORTS:
        sort = "remark"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    q = (request.args.get("q") or "").strip()
    result = db.list_inventory_storage(q=q, sort=sort, direction=direction)
    return render_template(
        "inventory_storage.html",
        result=result,
        filters={"q": q, "sort": sort, "dir": direction},
    )


@app.route("/inventory/duplicates")
def inventory_duplicates():
    price = (request.args.get("price") or "differs").strip()
    if price not in {"differs", "same", "all"}:
        price = "differs"
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    q = (request.args.get("q") or "").strip()
    result = db.list_inventory_duplicates(q=q, price=price, page=page, limit=30)
    groups = []
    for group in result["groups"]:
        shown = dict(group)
        shown["lots"] = [_present_inventory(lot) for lot in group["lots"]]
        shown["raise_count"] = sum(
            1
            for lot in shown["lots"]
            if int(lot.get("unit_price_milli") or 0) < int(group.get("max_milli") or 0)
        )
        condition = (group.get("new_or_used") or "").upper()
        shown["condition_label"] = {"N": "New", "U": "Used"}.get(condition, condition or "Any condition")
        item_type = group.get("item_type") or ""
        shown["type_label"] = bricklink.ITEM_TYPE_LABELS.get(item_type, item_type)
        groups.append(shown)
    return render_template(
        "inventory_duplicates.html",
        groups=groups,
        result=result,
        summary=db.inventory_duplicate_summary(),
        filters={"q": q, "price": price, "page": result["page"]},
    )


def _duplicate_return_args():
    price = (request.form.get("price") or "differs").strip()
    if price not in {"differs", "same", "all"}:
        price = "differs"
    try:
        page = max(1, int(request.form.get("page") or 1))
    except ValueError:
        page = 1
    return {
        "q": (request.form.get("q") or "").strip(),
        "price": price,
        "page": page,
    }


@app.route("/inventory/duplicates/sync", methods=["POST"])
def inventory_duplicates_sync():
    back = _duplicate_return_args()
    scope = (request.form.get("scope") or "").strip()
    if scope == "group":
        updates = db.duplicate_price_updates(
            item_no=request.form.get("item_no") or "",
            color_id=request.form.get("color_id") or "",
            new_or_used=(request.form.get("new_or_used") or "").upper(),
            description=request.form.get("description") if request.form.get("description") is not None else "",
            matched_group=True,
        )
    elif scope == "all":
        updates = db.duplicate_price_updates()
    else:
        flash("Unknown price update.")
        return redirect(url_for("inventory_duplicates", **back))
    if not updates:
        flash("Those lots are already at the highest price.")
        return redirect(url_for("inventory_duplicates", **back))
    try:
        creds = bricklink.creds_from_settings(db.get_setting)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("inventory_duplicates", **back))
    updated = 0
    failed = []
    for index, row in enumerate(updates):
        if index:
            time.sleep(0.2)
        try:
            bricklink.update_inventory_price(creds, row["bl_inventory_id"], row["target_price"])
            db.set_store_inventory_price(
                row["bl_inventory_id"], row["target_price"], row["target_milli"]
            )
            updated += 1
        except ValueError as exc:
            failed.append(f"{row['bl_inventory_id']}: {exc}")
    if updated and not failed:
        flash(f"Updated {updated} BrickLink lot{'s' if updated != 1 else ''} to the highest price in the group.")
    elif updated:
        flash(
            f"Updated {updated} lot{'s' if updated != 1 else ''}. "
            f"{len(failed)} failed, starting with {failed[0]}"
        )
    else:
        flash(f"BrickLink did not update those lots. {failed[0]}")
    return redirect(url_for("inventory_duplicates", **back))


@app.route("/inventory/sync", methods=["GET", "POST"])
def inventory_sync():
    if request.method == "POST":
        try:
            creds = bricklink.creds_from_settings(db.get_setting)
            rows = bricklink.fetch_inventory_snapshot(creds)
            result = db.stage_inventory_snapshot(rows)
        except ValueError as exc:
            flash(str(exc))
            return redirect(url_for("inventory"))
        if result["replaced_pending"]:
            flash("Replaced the previous sync that was still waiting for review.")
        return redirect(url_for("inventory_sync"))
    report = db.inventory_sync_report()
    if report is None:
        flash("Fetch a BrickLink sync before reviewing changes.")
        return redirect(url_for("inventory"))
    return render_template("inventory_sync.html", report=report)


@app.route("/inventory/sync/apply", methods=["POST"])
def inventory_sync_apply():
    try:
        result = db.apply_inventory_sync()
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("inventory"))
    if result["added"] or result["updated"] or result["removed"]:
        flash(
            f"Synced BrickLink inventory. {result['added']} added, "
            f"{result['updated']} updated, {result['removed']} removed. "
            f"{result['unchanged']} unchanged."
        )
    else:
        flash("Synced. BrickLink already matches this inventory.")
    return redirect(url_for("inventory"))


@app.route("/inventory/sync/reject", methods=["POST"])
def inventory_sync_reject():
    if db.discard_inventory_sync():
        flash("Sync discarded. The local inventory was not changed.")
    else:
        flash("There was no sync waiting for review.")
    return redirect(url_for("inventory"))


@app.route("/inventory/<bl_inventory_id>")
def inventory_detail(bl_inventory_id):
    item = db.get_store_inventory(bl_inventory_id)
    if item is None:
        flash("That BrickLink inventory lot is not in the local snapshot.")
        return redirect(url_for("inventory"))
    try:
        pretty_json = json.dumps(json.loads(item.get("api_json") or "{}"), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty_json = item.get("api_json") or ""
    return render_template(
        "inventory_detail.html",
        item=_present_inventory(item),
        pretty_json=pretty_json,
    )


def _price_fetched_at(value: str):
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _forge_prices_due(fig_ids, prices: dict) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=FORGE_PRICE_DAYS)
    due = []
    for fig_id in fig_ids:
        info = prices.get(fig_id)
        if info is None:
            due.append(fig_id)
            continue
        fetched = _price_fetched_at(info.get("fetched_at"))
        if fetched is None or fetched < cutoff:
            due.append(fig_id)
    return due


def refresh_forge_prices(fig_ids, force: bool = False) -> int:
    """Fill the local price cache from BrickLink. Returns how many guides were fetched."""
    wanted = list(dict.fromkeys(fig_ids))
    prices = db.load_minifig_prices(**FORGE_GUIDE)
    due = wanted if force else _forge_prices_due(wanted, prices)
    if not due:
        return 0
    creds = bricklink.creds_from_settings(db.get_setting)
    print(f"forge prices fetching {len(due)}", flush=True)
    fresh_after = datetime.now(timezone.utc) - timedelta(days=FORGE_PRICE_DAYS)
    fetched = 0
    for index, fig_id in enumerate(due, 1):
        if not force:
            stamp = _price_fetched_at(db.minifig_price_fetched_at(fig_id, **FORGE_GUIDE))
            if stamp is not None and stamp >= fresh_after:
                continue
        delay = 1.0
        guide = None
        for attempt in range(5):
            try:
                guide = bricklink.item_price_guide(creds, fig_id, item_type="MINIFIG", **FORGE_GUIDE)
                break
            except bricklink.BrickLinkThrottle:
                time.sleep(delay)
                delay = min(delay * 2, 30)
            except ValueError as exc:
                text = str(exc)
                if any(code in text for code in ("HTTP 400", "HTTP 403", "HTTP 404")):
                    print(f"forge price skipped {fig_id}: {text}", flush=True)
                    guide = None
                    break
                if attempt == 4:
                    print(f"forge price skipped {fig_id}: {text}", flush=True)
                    guide = None
                    break
                time.sleep(delay)
                delay = min(delay * 2, 30)
        if guide is None:
            time.sleep(0.2)
            continue
        db.save_minifig_price(
            {
                "fig_id": fig_id,
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                **guide,
            }
        )
        fetched += 1
        if index % 25 == 0 or index == len(due):
            price = guide.get("qty_avg_price_milli")
            shown = f"${price / 1000:.2f}" if price is not None else "no sales"
            print(f"forge prices {index}/{len(due)} {fig_id} {shown}", flush=True)
        time.sleep(0.2)
    return fetched


def _start_forge_price_refresh(fig_ids) -> None:
    global _price_refresh_running
    if not fig_ids or not db.has_bricklink_creds():
        return
    with _price_refresh_lock:
        if _price_refresh_running:
            return
        _price_refresh_running = True

    def work():
        global _price_refresh_running
        try:
            refresh_forge_prices(fig_ids)
        except Exception as exc:
            print(f"forge price refresh failed: {exc}", flush=True)
        finally:
            with _price_refresh_lock:
                _price_refresh_running = False

    threading.Thread(target=work, daemon=True).start()


@app.route("/forge")
def forge():
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    try:
        catalog = minifig_catalog.load()
        prices = db.load_minifig_prices(**FORGE_GUIDE)
        result = minifig_catalog.buildable_figures(
            catalog,
            db.inventory_part_quantities(),
            q=q,
            page=page,
            prices=prices,
            places=db.inventory_part_places(),
            listed=db.inventory_part_prices(),
        )
    except minifig_catalog.CatalogError as exc:
        return render_template("forge.html", error=str(exc), filters={"q": q})
    _start_forge_price_refresh(_forge_prices_due(result["buildable_ids"], prices))
    generated = catalog["generated_at"]
    return render_template(
        "forge.html",
        error=None,
        rows=result["rows"],
        result=result,
        filters={"q": q, "page": result["page"]},
        generated_at=generated.strftime("%b %-d, %Y") if generated else "",
    )


@app.route("/forge/parts")
def forge_parts():
    return render_template("forge_parts.html")


@app.route("/expenses")
def expenses():
    return render_template("expenses.html")


def _lot_from_form():
    title = request.form.get("title", "").strip()
    purchased_on = request.form.get("purchased_on", "").strip()
    if not title or not purchased_on:
        return None, "A lot needs a name and purchase date."
    return {
        "title": title,
        "purchased_on": purchased_on,
        "source": request.form.get("source") or "Other",
        "cost_cents": db.parse_money(request.form.get("cost")),
        "shipping_cents": db.parse_money(request.form.get("shipping")),
        "tax_cents": db.parse_money(request.form.get("tax")),
        "handling_cents": db.parse_money(request.form.get("handling")),
        "notes": request.form.get("notes", "").strip(),
    }, None


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5050)
