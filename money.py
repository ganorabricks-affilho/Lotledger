"""Dollar amounts.

BrickLink and BrickOwl item prices keep three decimal places. Those values are
thousandths of a dollar (milli). Lot costs, shipping, and order headers that
were already stored as whole cents stay in cents. Do not add a milli total to
a cent total.
"""


def cents_from_form(value) -> int:
    """Form dollars to cents. Blank is 0. Bad text raises ValueError."""
    raw = (value or "").strip().replace("$", "").replace(",", "")
    if raw == "":
        return 0
    return int(round(float(raw) * 100))


def cents_from_api(value) -> int:
    """API dollars to cents. Blank or bad text is 0."""
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return 0
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return 0


def milli_from_form(value) -> int:
    """Form dollars to thousandths. Blank is 0. Bad text raises ValueError."""
    raw = (value or "").strip().replace("$", "").replace(",", "")
    if raw == "":
        return 0
    return int(round(float(raw) * 1000))


def dollars_to_milli(amount) -> int:
    """A dollar amount, already numeric, to thousandths. Keeps the third decimal."""
    return int(round(float(amount or 0) * 1000))


def milli_from_api(value) -> int:
    """API dollars to thousandths. Keeps the third decimal. Blank or bad text is 0."""
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return 0
    try:
        return int(round(float(raw) * 1000))
    except ValueError:
        return 0


def milli_to_cents(millis) -> int:
    """Cents from a thousandths total. Ten milli is one cent; the remainder rounds.

    Stored item prices stay in milli. This is only for a total that has to meet
    a cent field, such as an order header.
    """
    return int(round((millis or 0) / 10))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def format_milli(millis: int) -> str:
    sign = "-" if millis < 0 else ""
    millis = abs(millis or 0)
    return f"{sign}${millis // 1000:,}.{millis % 1000:03d}"


def format_cents_input(cents: int) -> str:
    cents = cents or 0
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_milli_plain(millis: int) -> str:
    """Three decimal places, no dollar sign. Used when writing a BrickStore price."""
    return f"{(millis or 0) / 1000:.3f}"


def format_price_string(value) -> str:
    """Normalize a pasted price to three decimal places."""
    raw = str(value or "").replace("$", "").replace(",", "").strip()
    if raw == "":
        return "0.000"
    try:
        return f"{float(raw):.3f}"
    except ValueError:
        return "0.000"


def line_price_scale_needs_migration(stored) -> bool:
    """Multiply stored line prices by 10 only when they are still marked as cents.

    A missing flag is not a reason to multiply. Item prices are already
    thousandths, and multiplying again would drop the third-decimal scale.
    """
    return stored is not None and stored != "milli"
