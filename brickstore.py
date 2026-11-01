import xml.etree.ElementTree as ET

ITEM_TYPES = {
    "P": "Part",
    "M": "Minifig",
    "S": "Set",
    "G": "Gear",
    "B": "Book",
    "I": "Instruction",
    "C": "Catalog",
    "O": "Box",
    "U": "Unsorted",
}

CONDITIONS = {"N": "New", "U": "Used"}


def parse_inventory(xml_text: str) -> list[dict]:
    text = (xml_text or "").strip()
    if not text:
        raise ValueError("The XML file is empty.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not read BrickStore XML: {exc}") from exc

    if root.tag.upper() != "INVENTORY":
        raise ValueError("This is not a BrickStore inventory file (missing INVENTORY).")

    items = []
    for node in root.findall("ITEM"):
        qty = _int(text_of(node, "QTY"), default=0)
        if qty <= 0:
            continue
        price = _float(text_of(node, "PRICE"))
        item_type = text_of(node, "ITEMTYPE") or "P"
        condition = text_of(node, "CONDITION") or "U"
        items.append(
            {
                "item_id": text_of(node, "ITEMID"),
                "item_type": item_type,
                "item_type_label": ITEM_TYPES.get(item_type, item_type),
                "color": text_of(node, "COLOR"),
                "category": text_of(node, "CATEGORY"),
                "qty": qty,
                "price_cents": int(round(price * 100)),
                "condition": condition,
                "condition_label": CONDITIONS.get(condition, condition),
                "remarks": text_of(node, "REMARKS"),
            }
        )
    if not items:
        raise ValueError("No listable items found in that XML.")
    return items


def text_of(node, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _int(value: str, default: int = 0) -> int:
    try:
        return int(float(value)) if value else default
    except ValueError:
        return default


def _float(value: str) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


_PLACE_TAGS = ("ITEMID", "ITEMTYPE", "COLOR", "CATEGORY", "QTY", "PRICE", "CONDITION", "SALE", "DESCRIPTION", "REMARKS")
_PLACE_LIMIT = 2000


def parse_place_xml(xml_text: str) -> tuple:
    """Read a BrickStore inventory paste, including optional sale, comments, and remarks.

    Returns (items, skipped). Items with no id or a quantity below 1 are skipped.
    Unknown tags are kept so a later download does not drop them.
    """
    text = (xml_text or "").strip().lstrip("\ufeff")
    if not text:
        raise ValueError("Paste the BrickStore XML first.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not read that XML: {exc}") from exc
    if root.tag.upper() != "INVENTORY":
        raise ValueError("This is not a BrickStore inventory file (missing INVENTORY).")

    items = []
    skipped = 0
    for node in root.findall("ITEM"):
        fields = {}
        extra = []
        for child in list(node):
            tag = (child.tag or "").strip().upper()
            if not tag:
                continue
            value = (child.text or "").strip()
            if tag in fields:
                continue
            fields[tag] = value
            if tag not in _PLACE_TAGS:
                extra.append((tag, value))
        item_id = fields.get("ITEMID", "")
        qty = _int(fields.get("QTY", ""), default=0)
        if not item_id or qty <= 0:
            skipped += 1
            continue
        if len(items) >= _PLACE_LIMIT:
            raise ValueError(f"Paste up to {_PLACE_LIMIT:,} items at a time.")
        price = fields.get("PRICE", "")
        sale = fields.get("SALE", "")
        if sale in {"0", "0.0"}:
            sale = ""
        condition = (fields.get("CONDITION") or "").upper()
        if condition not in CONDITIONS:
            condition = ""
        items.append(
            {
                "item_id": item_id,
                "item_type": fields.get("ITEMTYPE") or "P",
                "color_id": fields.get("COLOR", ""),
                "category_id": fields.get("CATEGORY", ""),
                "qty": qty,
                "price": price,
                "condition": condition,
                "sale": sale,
                "comments": fields.get("DESCRIPTION", ""),
                "remarks": fields.get("REMARKS", ""),
                "extra": extra,
            }
        )
    if not items:
        raise ValueError("No items with a quantity found in that XML.")
    return items, skipped


def render_place_xml(items: list) -> str:
    """Write BrickStore XML from the reviewed rows."""
    root = ET.Element("INVENTORY")
    for item in items:
        node = ET.SubElement(root, "ITEM")
        values = {
            "ITEMID": item.get("item_id") or "",
            "ITEMTYPE": item.get("item_type") or "P",
            "COLOR": item.get("color_id") or "",
            "CATEGORY": item.get("category_id") or "",
            "QTY": str(item.get("qty") or 0),
            "PRICE": _price_text(item.get("price")),
            "CONDITION": item.get("condition") or "",
        }
        sale = str(item.get("sale") or "").strip()
        if sale and sale != "0":
            values["SALE"] = sale
        comments = str(item.get("comments") or "").strip()
        if comments:
            values["DESCRIPTION"] = comments
        values["REMARKS"] = str(item.get("remarks") or "").strip()
        for tag in _PLACE_TAGS:
            if tag not in values:
                continue
            child = ET.SubElement(node, tag)
            child.text = values[tag]
        for tag, value in item.get("extra") or []:
            child = ET.SubElement(node, tag)
            child.text = value
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def _price_text(value) -> str:
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return "0.000"
    try:
        return f"{float(raw):.3f}"
    except ValueError:
        return "0.000"
