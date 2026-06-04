#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON:-python}"
if [[ -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
fi

"$python_bin" -m PyInstaller \
  --windowed \
  --name "HoverTranslate" \
  --icon "assets/hovertranslate.icns" \
  --noconfirm \
  --clean \
  main.py

echo "Built dist/HoverTranslate.app"
