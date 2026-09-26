from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

import brickstore
import database as db

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
        title = request.form.get("title", "").strip()
        purchased_on = request.form.get("purchased_on", "").strip()
        if not title or not purchased_on:
            flash("A lot needs a name and purchase date.")
            return redirect(url_for("lots"))
        lot_id = db.create_lot(
            {
                "title": title,
                "purchased_on": purchased_on,
                "source": request.form.get("source") or "Other",
                "cost_cents": db.parse_money(request.form.get("cost")),
                "shipping_cents": db.parse_money(request.form.get("shipping")),
                "tax_cents": db.parse_money(request.form.get("tax")),
                "handling_cents": db.parse_money(request.form.get("handling")),
                "notes": request.form.get("notes", "").strip(),
            }
        )
        flash("Lot saved as pending details. Add the BrickStore XML when the listing is ready.")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    return render_template("lots.html", lots=db.list_lots())


@app.route("/lots/<int:lot_id>")
def lot_detail(lot_id):
    lot = db.get_lot(lot_id)
    if lot is None:
        flash("Lot not found.")
        return redirect(url_for("dashboard"))
    return render_template("lot_detail.html", lot=lot)


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
    flash(f"Imported {len(items)} listed lines from {filename}. This lot is now valid.")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/delete", methods=["POST"])
def lot_delete(lot_id):
    db.delete_lot(lot_id)
    flash("Lot deleted. Any matched sales are now unmatched.")
    return redirect(url_for("dashboard"))


@app.route("/sales", methods=["GET", "POST"])
def sales():
    if request.method == "POST":
        sold_on = request.form.get("sold_on", "").strip()
        if not sold_on:
            flash("A sale needs a date.")
            return redirect(url_for("sales"))
        lot_id = request.form.get("lot_id") or None
        db.create_sale(
            {
                "sold_on": sold_on,
                "platform": request.form.get("platform") or "Other",
                "order_ref": request.form.get("order_ref", "").strip(),
                "description": request.form.get("description", "").strip(),
                "gross_cents": db.parse_money(request.form.get("gross")),
                "fees_cents": db.parse_money(request.form.get("fees")),
                "lot_id": int(lot_id) if lot_id else None,
            }
        )
        flash("Sale saved.")
        return redirect(url_for("sales"))
    lots = db.list_lots()
    return render_template(
        "sales.html",
        sales=db.list_sales(),
        lots=lots,
        ready_lots=[lot for lot in lots if lot["has_details"]],
    )


@app.route("/sales/<int:sale_id>/match", methods=["POST"])
def sale_match(sale_id):
    lot_id = request.form.get("lot_id") or None
    db.match_sale(sale_id, int(lot_id) if lot_id else None)
    flash("Sale matching updated.")
    next_url = request.form.get("next") or url_for("sales")
    return redirect(next_url)


@app.route("/sales/<int:sale_id>/delete", methods=["POST"])
def sale_delete(sale_id):
    db.delete_sale(sale_id)
    flash("Sale deleted.")
    return redirect(request.form.get("next") or url_for("sales"))


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
