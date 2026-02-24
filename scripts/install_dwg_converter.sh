#!/usr/bin/env bash
set -euo pipefail

if command -v dwg2dxf >/dev/null 2>&1; then
  echo "dwg2dxf jest już zainstalowany." >&2
  exit 0
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "Instaluję LibreDWG (dwg2dxf) przez apt-get..." >&2
  sudo apt-get update
  sudo apt-get install -y libredwg-tools
  exit 0
fi

if command -v brew >/dev/null 2>&1; then
  echo "Instaluję LibreDWG (dwg2dxf) przez Homebrew..." >&2
  brew install libredwg
  exit 0
fi

cat <<'INSTRUCTIONS' >&2
Nie wykryto menedżera pakietów. Zainstaluj ręcznie narzędzie dwg2dxf (LibreDWG)

Przykłady:
- Debian/Ubuntu: sudo apt-get install libredwg-tools
- macOS (Homebrew): brew install libredwg

Alternatywnie pobierz ODAFileConverter i ustaw ODA_FILE_CONVERTER_PATH
(np. /opt/ODAFileConverter/ODAFileConverter).
INSTRUCTIONS
exit 1
