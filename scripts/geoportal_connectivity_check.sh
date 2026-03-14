#!/usr/bin/env bash
set -euo pipefail

WFS_URL="${GEO_WFS_URL:-https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza}"
PROXY_URL="${1:-${HTTPS_PROXY:-${https_proxy:-}}}"

echo "[1/3] GetCapabilities (bez wymuszonego proxy)"
curl -v "${WFS_URL}?service=WFS&request=GetCapabilities" -o /tmp/geoportal-capabilities.xml || true

echo

echo "[2/3] GetFeature (count=1)"
curl -v "${WFS_URL}?service=WFS&version=2.0.0&request=GetFeature&typeNames=dzialki&count=1" -o /tmp/geoportal-feature.xml || true

if [[ -n "${PROXY_URL}" ]]; then
  echo
  echo "[3/3] GetCapabilities przez proxy: ${PROXY_URL}"
  curl -v -x "${PROXY_URL}" "${WFS_URL}?service=WFS&request=GetCapabilities" -o /tmp/geoportal-capabilities-proxy.xml || true
else
  echo
  echo "[3/3] Pominięto test przez proxy (brak ustawionego HTTPS_PROXY lub argumentu skryptu)."
fi

echo "\nZapisano odpowiedzi do /tmp/geoportal-*.xml (o ile połączenie się udało)."
