function formatBBox(bbox) {
  if (!bbox) return "—";
  return `${bbox.minX.toFixed(2)}, ${bbox.minY.toFixed(2)} → ${bbox.maxX.toFixed(2)}, ${bbox.maxY.toFixed(2)}`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function initCadUI({
  state,
  setStatus,
  onCadMapApplied,
  onCadMapUpdated,
}) {
  const uploadBtn = document.getElementById("applyMapImportBtn");
  const layersContainer = document.getElementById("mapLayersContainer");
  const metaContainer = document.getElementById("mapMetaInfo");
  const statusContainer = document.getElementById("mapImportStatus");
  const scaleInput = document.getElementById("cadScaleMultiplier");
  const scalePreview = document.getElementById("cadScalePreview");

  function renderMeta(cadMap) {
    if (!metaContainer) return;
    if (!cadMap) {
      metaContainer.innerHTML = "<div class=\"muted\">—</div>";
      return;
    }
    const scaleMultiplier = state.cadScaleMultiplier ?? 1;
    const parcelCount = cadMap.parcelBoundaryCount ?? cadMap.parcelBoundaries?.length ?? 0;
    metaContainer.innerHTML = `
      <div><b>Jednostka:</b> ${escapeHtml(cadMap.unitsDetected || "—")}</div>
      <div><b>Skala → m:</b> ${cadMap.unitScaleToMeters ?? "—"}</div>
      <div><b>Korekta skali:</b> ${scaleMultiplier.toFixed(2)}×</div>
      <div><b>Granice działek:</b> ${parcelCount || "brak"}</div>
      <div><b>Obiekty:</b> ${cadMap.entityCount ?? 0}</div>
      <div><b>BBox:</b> ${formatBBox(cadMap.bbox)}</div>
      <div class="muted">Czas parsowania: ${cadMap.parseMs ?? "—"} ms</div>
    `;
  }

  function renderParcelSummary(cadMap) {
    if (!layersContainer) return;
    if (!cadMap) {
      layersContainer.innerHTML = "<div class=\"muted\">Brak danych.</div>";
      return;
    }

    const parcelCount = cadMap.parcelBoundaryCount ?? cadMap.parcelBoundaries?.length ?? 0;
    const sourceLayers = cadMap.parcelSourceLayers || [];
    const detectionReasons = cadMap.parcelDetection?.reasons || [];
    const sourceLabel = sourceLayers.length
      ? `<div class="muted">Warstwy źródłowe: ${sourceLayers.map(escapeHtml).join(", ")}</div>`
      : "<div class=\"muted\">Nie znaleziono warstw źródłowych.</div>";
    const reasonsLabel = detectionReasons.length
      ? `<div class="muted">Powód: ${detectionReasons.map(escapeHtml).join(", ")}</div>`
      : "";

    layersContainer.innerHTML = `
      <div><b>Granice działek:</b> ${parcelCount || "brak"}</div>
      ${sourceLabel}
      ${reasonsLabel}
    `;
  }

  async function uploadCadFile(file) {
    if (!file) {
      setStatus("warn", "Nie wybrano pliku.");
      return;
    }
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".dxf") && !lower.endsWith(".dwg")) {
      setStatus("bad", "Nieobsługiwany format. Wgraj DXF lub DWG.");
      return;
    }

    try {
      setStatus("info", "Wgrywanie i analiza pliku...");
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("/api/import-cad", {
        method: "POST",
        body: formData,
      });

      const payload = await response.json();
      if (!response.ok) {
        setStatus("bad", payload.error || "Błąd importu CAD.");
        return;
      }

      state.cadMap = payload;
      renderMeta(payload);
      renderParcelSummary(payload);
      setStatus("ok", "Mapa została załadowana.");
      onCadMapApplied?.(payload);
    } catch (error) {
      console.error("CAD import error:", error);
      setStatus("bad", "Nie udało się zaimportować pliku.");
    }
  }

  uploadBtn?.addEventListener("click", () => uploadCadFile(state.mapImportFile));

  if (scaleInput) {
    scaleInput.value = String(state.cadScaleMultiplier ?? 1);
    const updateScale = () => {
      const value = parseFloat(scaleInput.value);
      if (!Number.isFinite(value) || value <= 0) return;
      state.cadScaleMultiplier = value;
      if (scalePreview) scalePreview.textContent = `${value.toFixed(2)}×`;
      renderMeta(state.cadMap);
      onCadMapUpdated?.(state.cadMap);
    };
    scaleInput.addEventListener("input", updateScale);
    scaleInput.addEventListener("change", updateScale);
    updateScale();
  }

  if (state.cadMap) {
    renderMeta(state.cadMap);
    renderParcelSummary(state.cadMap);
  } else {
    renderMeta(null);
    renderParcelSummary(null);
    if (statusContainer?.textContent === "") {
      setStatus("idle", "Oczekuje na plik.");
    }
  }
}
