import calendar

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

import bricklink
import brickowl
import brickstore
import database as db

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
    }


@app.route("/")
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
                "net_cents": 0,
            }
            index[key] = group
            groups.append(group)
        group["orders"].append(order)
        group["qty"] += int(order.get("display_qty") or 0)
        group["lots"] += int(order.get("display_lots") or 0)
        group["items_cents"] += int(order.get("items_cents") or 0)
        group["shipping_cents"] += int(order.get("shipping_cents") or 0)
        group["packing_cents"] += int(order.get("packing_cents") or 0)
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
    return render_template(
        "sales.html",
        orders=orders,
        month_groups=_orders_by_month(orders),
        import_limit=10,
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
