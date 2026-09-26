from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

import brickowl
import brickstore
import database as db

app = Flask(__name__)
app.secret_key = "lotledger-local-dev"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
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
    try:
        filename, xml_text = _read_xml_input()
        items = brickstore.parse_inventory(xml_text)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("lot_detail", lot_id=lot_id))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{lot_id}_{filename}").write_text(xml_text, encoding="utf-8")
    db.replace_listing(lot_id, filename, items)
    flash(f"Imported {len(items)} lots ({sum(item['qty'] for item in items)} parts) from {filename}. This lot is now valid.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/delete", methods=["POST"])
def lot_delete(lot_id):
    db.delete_lot(lot_id)
    flash("Lot deleted. Any matched sales are now unmatched.")
    return redirect(url_for("dashboard"))


@app.route("/sales", methods=["GET", "POST"])
def sales():
    if request.method == "POST":
        fmt = (request.form.get("format") or "").strip().lower()
        labels = dict(SALE_FORMATS)
        if fmt not in labels:
            flash("Choose BrickLink or BrickOwl before importing.")
            return redirect(url_for("sales"))
        uploaded = request.files.get("sales_file")
        if not uploaded or not uploaded.filename:
            flash("Choose a sales file to import.")
            return redirect(url_for("sales"))
        filename = Path(uploaded.filename).name
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOAD_DIR / f"{fmt}_{filename}"
        uploaded.save(dest)
        flash(
            f"{labels[fmt]} file received ({filename}). "
            "This format’s import parser is next — send the file details when you’re ready."
        )
        return redirect(url_for("sales"))
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
    flash("Shipping and other costs saved on this order.")
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
        if request.form.get("action") == "clear_brickowl":
            db.set_setting("brickowl_api_key", "")
            flash("BrickOwl API key removed.")
        else:
            key = request.form.get("brickowl_api_key", "").strip()
            if not key:
                flash("Paste a BrickOwl API key, or use Remove key.")
            else:
                db.set_setting("brickowl_api_key", key)
                flash("BrickOwl API key saved.")
        return redirect(url_for("settings"))
    key = db.get_setting("brickowl_api_key")
    return render_template(
        "settings.html",
        has_brickowl_key=bool(key),
        key_hint=f"…{key[-4:]}" if len(key) >= 4 else "",
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


def _read_xml_input():
    uploaded = request.files.get("xml_file")
    path_value = (request.form.get("xml_path") or "").strip()
    if uploaded and uploaded.filename:
        filename = Path(uploaded.filename).name
        if not filename.lower().endswith(".xml"):
            raise ValueError("Use a .xml BrickStore inventory file.")
        return filename, uploaded.read().decode("utf-8", errors="replace")
    if path_value:
        path = Path(path_value).expanduser()
        if path.suffix.lower() != ".xml":
            raise ValueError("Use a .xml BrickStore inventory file.")
        if not path.is_file():
            raise ValueError(f"No file at {path}")
        return path.name, path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Upload a BrickStore XML or paste its local path.")


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5050)
