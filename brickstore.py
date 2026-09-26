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
