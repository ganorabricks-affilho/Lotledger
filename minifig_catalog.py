"""BrickStore catalog: minifigure parts lists in BrickLink ids."""

from __future__ import annotations

import struct
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bricklink

CATALOG_PATH = Path.home() / "Library" / "Caches" / "BrickStore" / "database-v12"
PAGE_SIZE = 40
# BrickStore lists these with a parts list that does not match the real figure.
SKIP_FIG_IDS = {"gen101", "gen102"}

_lock = threading.Lock()
_cache = {"key": None, "catalog": None}


class CatalogError(Exception):
    pass


class _Reader:
    def __init__(self, data: bytes, pos: int, end: int):
        self.data = data
        self.pos = pos
        self.end = end

    def _need(self, size: int) -> None:
        if self.pos + size > self.end:
            raise CatalogError("The BrickStore catalog ended early.")

    def u8(self) -> int:
        self._need(1)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def u16(self) -> int:
        self._need(2)
        value = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return value

    def u32(self) -> int:
        self._need(4)
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def i32(self) -> int:
        self._need(4)
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def i64(self) -> int:
        self._need(8)
        value = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return value

    def raw(self, size: int) -> bytes:
        self._need(size)
        value = self.data[self.pos : self.pos + size]
        self.pos += size
        return value

    def str8(self) -> str:
        size = self.u32()
        if size in (0, 0xFFFFFFFF):
            return ""
        return self.raw(size).decode("latin1")

    def str16(self) -> str:
        size = self.u32()
        if size in (0, 0xFFFFFFFF):
            return ""
        return self.raw(size).decode("utf-16-le")

    def skip_array(self, elem_size: int) -> int:
        count = self.u32()
        self.raw(count * elem_size)
        return count


def _chunks(data: bytes) -> dict[str, tuple[int, int]]:
    if data[:4] != b"BSDB":
        raise CatalogError("This is not a BrickStore catalog.")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 12:
        raise CatalogError(f"BrickStore catalog version {version} is not supported.")
    root_size = struct.unpack_from("<Q", data, 8)[0]
    pos = 16
    end = 16 + root_size
    found = {}
    while pos + 16 <= end:
        chunk_id = data[pos : pos + 4].decode("latin1")
        size = struct.unpack_from("<Q", data, pos + 8)[0]
        payload = pos + 16
        found[chunk_id] = (payload, size)
        pos = payload + size
        if size % 16:
            pos += 16 - (size % 16)
        pos += 16
    return found


def _generated_at(data: bytes, payload: int) -> datetime | None:
    julian = struct.unpack_from("<q", data, payload)[0]
    msecs = struct.unpack_from("<I", data, payload + 8)[0]
    # Qt's Julian day 2451545 is 2000-01-01.
    day = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(days=julian - 2451545)
    return day + timedelta(milliseconds=msecs)


def _colors(data: bytes, payload: int, size: int) -> list[tuple[str, str]]:
    """Color index -> (BrickLink color id, name), in catalog order."""
    end = payload + size
    count = struct.unpack_from("<I", data, payload)[0]
    colors = []
    pos = payload + 4
    while pos < end - 8 and len(colors) < count:
        name_bytes = struct.unpack_from("<I", data, pos)[0]
        if not (2 <= name_bytes <= 80 and name_bytes % 2 == 0 and pos + 4 + name_bytes <= end):
            pos += 1
            continue
        try:
            name = data[pos + 4 : pos + 4 + name_bytes].decode("utf-16-le")
        except UnicodeDecodeError:
            pos += 1
            continue
        if not name or any(char != " " and not char.isalpha() and char not in "-()/." for char in name):
            pos += 1
            continue
        color_id = struct.unpack_from("<I", data, pos - 4)[0]
        if color_id > 10000:
            pos += 1
            continue
        colors.append((str(color_id), name))
        pos += 4 + name_bytes
    if len(colors) != count or not colors or colors[0] != ("0", "(Not Applicable)"):
        raise CatalogError("Could not read the BrickStore color list.")
    return colors


def _item_type_index(data: bytes, payload: int, size: int, type_id: str) -> int:
    reader = _Reader(data, payload, payload + size)
    count = reader.u32()
    for index in range(count):
        found = chr(reader.u8())
        reader.str16()
        reader.u8()
        reader.skip_array(2)
        if found == type_id:
            return index
    raise CatalogError(f"The BrickStore catalog has no {type_id} item type.")


def _decode_consists(blob: bytes, color_count: int) -> list[tuple[int, int, int]]:
    parts = []
    for offset in range(0, len(blob), 8):
        word = struct.unpack_from("<Q", blob, offset)[0]
        quantity = word & 0xFFF
        item_index = (word >> 12) & 0xFFFFF
        color_index = (word >> 32) & 0xFFF
        extra = (word >> 44) & 1
        alternate = (word >> 45) & 1
        if quantity <= 0 or extra or alternate or color_index >= color_count:
            continue
        parts.append((quantity, item_index, color_index))
    return parts


def _minifigs(data: bytes, payload: int, size: int, minifig_type: int, colors: list[tuple[str, str]]):
    reader = _Reader(data, payload, payload + size)
    count = reader.u32()
    item_ids = []
    item_names = []
    pending = []
    color_count = len(colors)
    for _ in range(count):
        item_id = reader.str8()
        name = reader.str16()
        item_type = reader.u16()
        reader.u16()
        reader.u8()
        reader.u8()
        reader.raw(8)
        reader.skip_array(4)
        consists_count = reader.u32()
        consists = reader.raw(consists_count * 8)
        reader.skip_array(2)
        reader.skip_array(2)
        reader.skip_array(2)
        reader.skip_array(8)
        reader.skip_array(8)
        reader.str8()
        item_ids.append(item_id)
        item_names.append(name)
        if item_type == minifig_type and consists_count:
            pending.append((item_id, name, _decode_consists(consists, color_count)))
    if reader.pos != reader.end:
        raise CatalogError("Could not read the BrickStore item list.")

    figs = []
    for fig_id, name, lines in pending:
        needed = {}
        for quantity, item_index, color_index in lines:
            if item_index >= len(item_ids):
                continue
            color_id, color_name = colors[color_index]
            key = (item_ids[item_index], color_id)
            slot = needed.get(key)
            if slot is None:
                needed[key] = {
                    "item_no": item_ids[item_index],
                    "item_name": item_names[item_index],
                    "color_id": color_id,
                    "color_name": color_name,
                    "need": quantity,
                }
            else:
                slot["need"] += quantity
        if not needed:
            continue
        parts = sorted(needed.values(), key=lambda part: (part["item_no"], part["color_name"]))
        figs.append({"fig_id": fig_id, "name": name, "parts": parts})
    figs.sort(key=lambda fig: (fig["name"].lower(), fig["fig_id"]))
    return figs


def load(path: Path | None = None) -> dict:
    catalog_path = path or CATALOG_PATH
    if not catalog_path.is_file():
        raise CatalogError(f"BrickStore catalog was not found at {catalog_path}.")
    stat = catalog_path.stat()
    key = (str(catalog_path), stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cache["key"] == key and _cache["catalog"] is not None:
            return _cache["catalog"]
    data = catalog_path.read_bytes()
    chunks = _chunks(data)
    for name in ("DATE", "COL ", "TYPE", "ITEM"):
        if name not in chunks:
            raise CatalogError("The BrickStore catalog is missing part of its item list.")
    colors = _colors(data, *chunks["COL "])
    minifig_type = _item_type_index(data, *chunks["TYPE"], "M")
    figs = _minifigs(data, *chunks["ITEM"], minifig_type, colors)
    catalog = {
        "path": catalog_path,
        "generated_at": _generated_at(data, chunks["DATE"][0]),
        "fig_count": len(figs),
        "figs": figs,
    }
    with _lock:
        _cache["key"] = key
        _cache["catalog"] = catalog
    return catalog


def _color_key(color_id) -> str:
    text = str(color_id or "").strip()
    if text.isdigit():
        return str(int(text))
    return text


def owned_key(item_no: str, color_id) -> tuple[str, str]:
    return ((item_no or "").strip(), _color_key(color_id))


def _listed_cost(lots: list, need: int):
    """Cost of `need` units, taking the cheapest listed price first."""
    remaining = int(need or 0)
    if remaining <= 0:
        return None, None
    cost = 0
    used = []
    for lot in lots or []:
        if remaining <= 0:
            break
        take = min(remaining, int(lot.get("qty") or 0))
        if take <= 0:
            continue
        milli = int(lot.get("milli") or 0)
        cost += take * milli
        used.append(milli)
        remaining -= take
    if remaining > 0:
        return None, None
    unit = used[0] if len(set(used)) == 1 else None
    return cost, unit


def buildable_figures(
    catalog: dict,
    owned: dict[tuple[str, str], int],
    q: str = "",
    page: int = 1,
    limit: int = PAGE_SIZE,
    prices: dict | None = None,
    places: dict | None = None,
    listed: dict | None = None,
) -> dict:
    query = (q or "").strip().lower()
    matches = []
    for fig in catalog["figs"]:
        if fig["fig_id"].lower() in SKIP_FIG_IDS:
            continue
        if query and query not in fig["fig_id"].lower() and query not in fig["name"].lower():
            continue
        can_build = None
        parts = []
        for part in fig["parts"]:
            have = int(owned.get(owned_key(part["item_no"], part["color_id"]), 0))
            need = int(part["need"])
            possible = have // need if need else 0
            if can_build is None or possible < can_build:
                can_build = possible
            parts.append(
                {
                    **part,
                    "have": have,
                    "possible": possible,
                    "places": list((places or {}).get(owned_key(part["item_no"], part["color_id"]), [])),
                }
            )
        can_build = can_build or 0
        if not query and can_build < 1:
            continue
        parts_milli = 0
        parts_priced = True
        for part in parts:
            part["is_limit"] = part["possible"] == can_build
            cost, unit = _listed_cost(
                (listed or {}).get(owned_key(part["item_no"], part["color_id"])),
                part["need"],
            )
            part["list_milli"] = cost
            part["list_unit_milli"] = unit
            if cost is None:
                parts_priced = False
            else:
                parts_milli += cost
        info = (prices or {}).get(fig["fig_id"])
        price_milli = info["price_milli"] if info else None
        profit_milli = None
        if parts_priced and price_milli is not None:
            profit_milli = price_milli - parts_milli
        matches.append(
            {
                "fig_id": fig["fig_id"],
                "name": fig["name"],
                "can_build": can_build,
                "image_url": f"https://img.bricklink.com/ItemImage/MN/0/{fig['fig_id']}.png",
                "catalog_url": bricklink.catalog_url("MINIFIG", fig["fig_id"]),
                "parts": parts,
                "price_milli": price_milli,
                "sales": info["unit_quantity"] if info else 0,
                "price_fetched_at": info["fetched_at"] if info else "",
                "price_known": info is not None,
                "parts_milli": parts_milli if parts_priced else None,
                "profit_milli": profit_milli,
            }
        )
    matches.sort(
        key=lambda fig: (
            fig["price_milli"] is None,
            -(fig["price_milli"] or 0),
            fig["name"].lower(),
            fig["fig_id"],
        )
    )
    total = len(matches)
    buildable = [fig for fig in matches if fig["can_build"] >= 1]
    buildable_total = len(buildable)
    best = max((fig["can_build"] for fig in matches), default=0)
    priced = [fig for fig in matches if fig["price_milli"] is not None]
    top = priced[0] if priced else None
    pages = max(1, (total + limit - 1) // limit) if total else 1
    page = min(max(1, page), pages)
    start = (page - 1) * limit
    return {
        "rows": matches[start : start + limit],
        "total": total,
        "buildable_total": buildable_total,
        "buildable_ids": [fig["fig_id"] for fig in buildable],
        "best": best,
        "top_price_milli": top["price_milli"] if top else None,
        "top_fig_id": top["fig_id"] if top else "",
        "price_pending": sum(1 for fig in buildable if not fig["price_known"]),
        "page": page,
        "pages": pages,
        "fig_count": catalog["fig_count"],
    }
