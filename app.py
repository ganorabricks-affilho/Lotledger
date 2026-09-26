from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

import brickstore
import database as db
import sales_csv

app = Flask(__name__)
app.secret_key = "lotledger-local-dev"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
db.init_db()

SOURCES = ["BrickLink", "BrickOwl", "eBay", "Goodwill", "Facebook Marketplace", "Other"]
PLATFORMS = ["BrickLink", "BrickOwl", "eBay", "Other"]


@app.context_processor
def inject_helpers():
    return {
        "money": db.money,
        "money_input": db.money_input,
        "sources": SOURCES,
        "platforms": PLATFORMS,
        "item_types": brickstore.ITEM_TYPES,
        "conditions": brickstore.CONDITIONS,
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
        try:
            filename, csv_text = _read_csv_input()
            parsed = sales_csv.parse_sales_csv(csv_text)
        except ValueError as exc:
            flash(str(exc))
            return redirect(url_for("sales"))
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / filename).write_text(csv_text, encoding="utf-8")
        result = db.import_orders(parsed)
        flash(
            f"Imported {result['imported']} new orders ({result['lines']} lots). "
            f"Skipped {result['skipped']} duplicate order #s."
        )
        return redirect(url_for("sales"))
    return render_template("sales.html", orders=db.list_orders())


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
    db.delete_order(order_id)
    flash("Order deleted.")
    return redirect(url_for("sales"))


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


def _read_csv_input():
    uploaded = request.files.get("csv_file")
    path_value = (request.form.get("csv_path") or "").strip()
    if uploaded and uploaded.filename:
        filename = Path(uploaded.filename).name
        if not filename.lower().endswith(".csv"):
            raise ValueError("Use a .csv sales file.")
        return filename, uploaded.read().decode("utf-8", errors="replace")
    if path_value:
        path = Path(path_value).expanduser()
        if path.suffix.lower() != ".csv":
            raise ValueError("Use a .csv sales file.")
        if not path.is_file():
            raise ValueError(f"No file at {path}")
        return path.name, path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Upload a sales CSV or paste its local path.")


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5050)
