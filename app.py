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


@app.route("/sales")
def sales():
    return render_template("sales.html", orders=db.list_orders(), import_limit=10)


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
    )
    flash("Shipping saved. Net gain was split across items.")
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
