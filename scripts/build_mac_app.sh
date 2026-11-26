#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-mac.txt

iconset="packaging/Ganorabricks.iconset"
rm -rf "$iconset"
mkdir -p "$iconset"
src="static/ganorabricks-logo.png"
sips -z 16 16 "$src" --out "$iconset/icon_16x16.png" >/dev/null
sips -z 32 32 "$src" --out "$iconset/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$src" --out "$iconset/icon_32x32.png" >/dev/null
sips -z 64 64 "$src" --out "$iconset/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$src" --out "$iconset/icon_128x128.png" >/dev/null
sips -z 256 256 "$src" --out "$iconset/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$src" --out "$iconset/icon_256x256.png" >/dev/null
sips -z 512 512 "$src" --out "$iconset/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$src" --out "$iconset/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$src" --out "$iconset/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$iconset" -o packaging/Ganorabricks.icns

python -m PyInstaller --noconfirm --clean packaging/Ganorabricks.spec
echo "Built dist/Ganorabricks.app"
