# Lotledger

Local tracker for used LEGO lots: record cost, shipping, tax, and handling, match sales to lots, and check profit against that total.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5050

SQLite data lives in `data/lotledger.db`.
