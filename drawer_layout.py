"""Physical drawer map for the Akro Mills cabinets, Parkside units, and minifig towers.

The same ranges feed the drawer board and the first-run category seed.
"""

import re

LEFT_LETTERS = "ABCDEFGH"
RIGHT_LETTERS = "IJKLMNOP"
DRAWER_COLUMNS = {
    "left": [f"A{letter}" for letter in LEFT_LETTERS],
    "right": [f"A{letter}" for letter in RIGHT_LETTERS],
}
DRAWER_BLOCKS = {
    "left": (range(1, 8), range(8, 15)),
    "right": (range(1, 9), range(9, 17)),
}
PARKSIDE_COLUMNS = ["BA", "BB", "BC", "BD"]
PARKSIDE_UNITS = (
    (range(1, 9), 9),
    (range(10, 18), 18),
)
MINIFIG_TOWERS = (range(1, 13), range(13, 25))
MINIFIG_CODES = tuple(f"D17-{row:02d}" for row in range(1, 25))
SEED_CABINETS = (
    (LEFT_LETTERS, range(1, 15)),
    (RIGHT_LETTERS, range(1, 17)),
)


def on_drawer_map(code: str) -> bool:
    text = (code or "").strip().upper()
    if re.fullmatch(r"D17-\d{2}", text):
        return 1 <= int(text[4:]) <= 24
    if len(text) != 5 or text[2] != "-" or not text[:2].isalpha() or not text[3:].isdigit():
        return False
    column, row = text[:2], int(text[3:])
    if column in DRAWER_COLUMNS["left"]:
        return 1 <= row <= 14
    if column in DRAWER_COLUMNS["right"]:
        return 1 <= row <= 16
    if column in PARKSIDE_COLUMNS:
        if (1 <= row <= 8) or (10 <= row <= 17):
            return True
        return column == "BA" and row in (9, 18)
    return False
