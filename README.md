# Lotledger

Local store tool for Ganorabricks. Record what a used LEGO lot cost, import BrickLink and BrickOwl orders, and match those sales back to the lot. Inventory keeps an approved copy of the BrickLink store, including drawer remarks. Minifig Forge reads that copy against the BrickStore catalog on this Mac (`~/Library/Caches/BrickStore/database-v12`).

BrickLink and BrickOwl item prices, including prices on a purchased lot, are kept to three decimal places.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5050

SQLite data lives in `data/lotledger.db`.

## Mac app

Build a double-clickable app on this Mac:

```bash
./scripts/build_mac_app.sh
open dist/Ganorabricks.app
```

The app opens its own window and does not use port 5050, so it can run beside `python app.py`.

Its database is `~/Library/Application Support/Ganorabricks/lotledger.db`. The first launch copies the current `data/lotledger.db` there. After that the two files are separate.
