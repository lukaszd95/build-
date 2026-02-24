const uploadShell = document.getElementById("uploadShell");
const uploadView = document.getElementById("uploadView");
const closeUploadBtn = document.getElementById("closeUploadBtn");

const parcelIdInput = document.getElementById("parcelIdInput");
const addParcelBtn = document.getElementById("addParcelBtn");
const parcelList = document.getElementById("parcelList");
const parcelFileInput = document.getElementById("parcelFileInput");
const parcelUploadStatus = document.getElementById("parcelUploadStatus");
const parcelUnitsInfo = document.getElementById("parcelUnitsInfo");
const parcelBoundaryInfo = document.getElementById("parcelBoundaryInfo");
const parcelLayerList = document.getElementById("parcelLayerList");
const parcelVerticesInput = document.getElementById("parcelVerticesInput");
const parcelUploadProgressBar = document.getElementById("parcelUploadProgressBar");
const parcelPreviewCanvas = document.getElementById("parcelPreviewCanvas");
const parcelPreviewEmpty = document.getElementById("parcelPreviewEmpty");
const parcelPreviewMeta = document.getElementById("parcelPreviewMeta");
const plotVerticesInput = document.getElementById("plotVertices");
const plotImportList = document.getElementById("plotImportList");
const plotLayerTableBody = document.getElementById("plotLayerTableBody");

const documentCards = document.getElementById("documentCards");
const documentDataPanel = document.getElementById("documentDataPanel");
const documentSearchInput = document.getElementById("documentSearchInput");
const uploadTabParcel = document.getElementById("uploadTabParcel");
const uploadTabMpzp = document.getElementById("uploadTabMpzp");
const cardPanels = document.querySelectorAll("[data-card-panel]");

const DOCUMENT_MAX_SIZE_MB = 20;
const DOCUMENT_TYPES = [
  {
    type: "MPZP_WYPIS",
    label: "Wypis z MPZP",
    hint: "PDF/JPG/PNG z wypisem planu.",
  },
  {
    type: "MPZP_WYRYS",
    label: "Wyrys z MPZP",
    hint: "Skan mapy z wyrysem planu.",
  },
];

const MPZP_FIELDS = [
  { key: "znak_sprawy", label: "Znak sprawy", type: "text", section: "Metadane dokumentu" },
  { key: "data_wydania", label: "Data wydania", type: "text", section: "Metadane dokumentu" },
  { key: "wydany_dla", label: "Wydany dla", type: "text", section: "Metadane dokumentu" },
  { key: "numer_dzialki", label: "Numer działki", type: "text", section: "Informacje podstawowe" },
  { key: "obreb_gmina", label: "Obręb / gmina", type: "text", section: "Informacje podstawowe" },
  { key: "ulica", label: "Ulica", type: "text", section: "Informacje podstawowe" },
  { key: "miejscowosc", label: "Miejscowość", type: "text", section: "Informacje podstawowe" },
  { key: "symbol_terenu_mpzp", label: "Symbol terenu MPZP", type: "text", section: "Informacje podstawowe" },
  {
    key: "status_planu",
    label: "Status planu",
    type: "select",
    options: ["obowiązuje", "zmiana", "brak"],
    section: "Informacje podstawowe",
  },
  { key: "podstawa_prawna", label: "Podstawa prawna (uchwała, data)", type: "text", section: "Informacje podstawowe" },
  { key: "przeznaczenie_podstawowe", label: "Przeznaczenie podstawowe", type: "text", section: "Przeznaczenie terenu" },
  { key: "przeznaczenie_dopuszczalne", label: "Przeznaczenie dopuszczalne", type: "text", section: "Przeznaczenie terenu" },
  { key: "funkcje_zakazane", label: "Funkcje zakazane", type: "text", section: "Przeznaczenie terenu" },
  {
    key: "mozliwosc_laczenia_funkcji",
    label: "Możliwość łączenia funkcji",
    type: "select",
    options: ["tak", "nie"],
    section: "Przeznaczenie terenu",
  },
  { key: "symbol_terenu", label: "Symbol terenu", type: "text", section: "Parametry MPZP" },
  { key: "max_wysokosc", label: "Maks. wysokość", type: "number", unitOptions: ["m", "kondygnacje"], section: "Parametry MPZP" },
  { key: "max_liczba_kondygnacji_nadziemnych", label: "Maks. liczba kondygnacji nadziemnych", type: "number", section: "Parametry MPZP" },
  { key: "max_liczba_kondygnacji_podziemnych", label: "Maks. liczba kondygnacji podziemnych", type: "number", section: "Parametry MPZP" },
  { key: "max_wysokosc_kalenicy", label: "Maks. wysokość kalenicy", type: "number", unitOptions: ["m"], section: "Parametry MPZP" },
  { key: "max_wysokosc_okapu", label: "Maks. wysokość okapu", type: "number", unitOptions: ["m"], section: "Parametry MPZP" },
  { key: "min_intensywnosc", label: "Min. intensywność", type: "number", section: "Parametry MPZP" },
  { key: "max_intensywnosc", label: "Maks. intensywność", type: "number", section: "Parametry MPZP" },
  { key: "max_pow_zabudowy", label: "Maks. pow. zabudowy", type: "number", unitOptions: ["%", "m²"], section: "Parametry MPZP" },
  { key: "min_pow_biol_czynna", label: "Min. pow. biologicznie czynna", type: "number", unitOptions: ["%", "m²"], section: "Parametry MPZP" },
  { key: "min_szerokosc_elewacji_frontowej", label: "Min. szerokość elewacji frontowej", type: "number", unitOptions: ["m"], section: "Parametry MPZP" },
  { key: "max_szerokosc_elewacji_frontowej", label: "Maks. szerokość elewacji frontowej", type: "number", unitOptions: ["m"], section: "Parametry MPZP" },
  { key: "linie_zabudowy", label: "Linie zabudowy", type: "text", section: "Parametry MPZP" },
  { key: "dach_typ", label: "Typ dachu", type: "text", section: "Parametry MPZP" },
  { key: "parking_wymagania", label: "Wymagania parkingowe", type: "text", section: "Parametry MPZP" },
  { key: "strefy_ograniczenia", label: "Strefy i ograniczenia", type: "text", section: "Parametry MPZP" },
  { key: "notatki", label: "Notatki", type: "textarea", section: "Parametry MPZP" },
];

const state = {
  parcels: [],
  documentsByType: {},
  activeDocumentId: null,
  activeDocumentType: null,
  extractedDataByDocument: {},
  errorsByType: {},
  expandedType: null,
  activeParcelId: "_global",
  fieldQuery: "",
  activeCard: "parcel",
  plotImports: [],
  activePlotImportId: null,
  plotLayers: [],
};

const parcelPreviewState = {
  points: null,
  layer: null,
  area: null,
  units: null,
};

let autosaveTimerId = null;

function getEffectiveParcelId() {
  if (state.activeParcelId && state.activeParcelId !== "_global") {
    return state.activeParcelId;
  }
  if (state.parcels.length) {
    return state.parcels[0].parcelId;
  }
  return "_global";
}

function getOrCreateExtractedEntry(documentId, parcelId) {
  if (!state.extractedDataByDocument[documentId]) {
    state.extractedDataByDocument[documentId] = {};
  }
  if (!state.extractedDataByDocument[documentId][parcelId]) {
    state.extractedDataByDocument[documentId][parcelId] = {
      documentId,
      parcelId,
      fields: {},
      source: { source: "manual" },
    };
  }
  return state.extractedDataByDocument[documentId][parcelId];
}

function syncPlotVerticesValue(value) {
  if (plotVerticesInput && plotVerticesInput.value !== value) {
    plotVerticesInput.value = value;
  }
  if (parcelVerticesInput && parcelVerticesInput.value !== value) {
    parcelVerticesInput.value = value;
  }
}

function bindPlotVerticesSync() {
  const handler = (event) => {
    syncPlotVerticesValue(event.target.value);
  };
  parcelVerticesInput?.addEventListener("input", handler);
  plotVerticesInput?.addEventListener("input", handler);
  if (parcelVerticesInput?.value) {
    syncPlotVerticesValue(parcelVerticesInput.value);
  } else if (plotVerticesInput?.value) {
    syncPlotVerticesValue(plotVerticesInput.value);
  }
}

function setUploadView(active) {
  if (!uploadShell) return;
  uploadShell.classList.toggle("active", active);
  document.body.classList.toggle("upload-open", active);
  if (!active) {
    window.location.hash = "";
  }
  localStorage.setItem("uploadPanelOpen", active ? "1" : "0");
}

function setUploadCard(card) {
  state.activeCard = card;
  cardPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.cardPanel === card);
  });
  uploadTabParcel?.classList.toggle("active", card === "parcel");
  uploadTabMpzp?.classList.toggle("active", card === "mpzp");
  uploadTabParcel?.setAttribute("aria-selected", card === "parcel" ? "true" : "false");
  uploadTabMpzp?.setAttribute("aria-selected", card === "mpzp" ? "true" : "false");
  localStorage.setItem("uploadActiveCard", card);
}

function syncRoute() {
  const hash = window.location.hash;
  if (hash === "#upload") {
    setUploadView(true);
    setUploadCard(state.activeCard);
    return;
  }
  setUploadView(false);
}

closeUploadBtn?.addEventListener("click", () => setUploadView(false));
uploadShell?.addEventListener("click", (event) => {
  if (event.target === uploadShell) {
    setUploadView(false);
  }
});
uploadTabParcel?.addEventListener("click", () => setUploadCard("parcel"));
uploadTabMpzp?.addEventListener("click", () => setUploadCard("mpzp"));
window.addEventListener("hashchange", syncRoute);
state.activeCard = localStorage.getItem("uploadActiveCard") || "parcel";
syncRoute();
bindPlotVerticesSync();
setParcelProgress("idle");
window.addEventListener("plot-imported", (event) => updateParcelPreview(event.detail));
loadPlotImports();

documentSearchInput?.addEventListener("input", () => renderDocumentCards());

async function loadParcels() {
  const response = await fetch("/api/parcels");
  const payload = await response.json();
  state.parcels = payload.parcels || [];
  if (state.parcels.length && state.activeParcelId === "_global") {
    state.activeParcelId = state.parcels[0].parcelId;
  }
  renderParcels();
  renderDataForm();
}

async function loadPlotImports() {
  if (!plotImportList) return;
  const response = await fetch("/api/plots");
  const payload = await response.json();
  const imports = payload.imports || [];
  if (!imports.length) {
    state.plotImports = [
      {
        id: "demo",
        filename: "Przykładowa_dzialka.dxf",
        status: "DEMO",
        createdAt: null,
        isDisabled: false,
        isDemo: true,
      },
    ];
  } else {
    state.plotImports = imports;
  }
  state.plotLayers = buildPlotLayerRows(state.plotImports);
  renderPlotImportList();
  renderPlotLayers();
}

function renderPlotImportList() {
  if (!plotImportList) return;
  plotImportList.innerHTML = "";
  if (!state.plotImports.length) {
    plotImportList.innerHTML = "<div class=\"muted\">Brak zaczytanych plików.</div>";
    return;
  }

  state.plotImports.forEach((job) => {
    const item = document.createElement("div");
    item.className = "parcel-uploaded-item";
    if (job.isDisabled) {
      item.classList.add("disabled");
    }

    const main = document.createElement("div");
    main.className = "parcel-uploaded-main";

    const name = document.createElement("div");
    name.className = "parcel-uploaded-name";
    name.textContent = job.filename;
    name.addEventListener("click", async () => {
      if (job.isDemo) return;
      if (job.isDisabled) return;
      await selectPlotImport(job.id);
    });

    const meta = document.createElement("div");
    meta.className = "parcel-uploaded-meta";
    meta.textContent = job.isDemo ? "Plik demonstracyjny" : "Gotowy do użycia";

    main.appendChild(name);
    main.appendChild(meta);

    const status = document.createElement("div");
    status.className = "parcel-uploaded-status";
    if (job.isDemo) {
      status.classList.add("demo");
      status.textContent = job.isDisabled ? "Wyłączone" : "Włączone";
    } else if (job.isDisabled) {
      status.classList.add("disabled");
      status.textContent = "Wygaszony";
    } else {
      status.classList.add("active");
      status.textContent = "Aktywny";
    }

    const removeWrap = document.createElement("div");
    removeWrap.className = "parcel-uploaded-remove";
    const removeBtn = document.createElement("button");
    removeBtn.className = "parcel-uploaded-icon-btn";
    removeBtn.type = "button";
    removeBtn.setAttribute("aria-label", "Usuń plik");
    removeBtn.textContent = "🗑";
    removeBtn.addEventListener("click", async () => {
      if (job.isDemo) return;
      await deletePlotImport(job.id);
    });
    if (job.isDemo) {
      removeBtn.disabled = true;
    }
    removeWrap.appendChild(removeBtn);

    item.appendChild(main);
    item.appendChild(status);
    item.appendChild(removeWrap);
    plotImportList.appendChild(item);
  });
}

function buildPlotLayerRows(imports) {
  const layers = [];
  const defaultAssigned = ["Granice działki", "Warstwy pomocnicze", "Opis"];
  imports.forEach((job, index) => {
    const baseName = job.filename?.split(".")[0] || `Plik ${index + 1}`;
    for (let i = 0; i < 3; i += 1) {
      layers.push({
        id: `${job.id}-${i}`,
        name: `${baseName}_L${i + 1}`,
        assigned: defaultAssigned[i] || "Inne",
        fileName: job.filename,
        enabled: !job.isDisabled,
      });
    }
  });
  if (!layers.length) {
    layers.push(
      {
        id: "demo-1",
        name: "Granica_glowna",
        assigned: "Granice działki",
        fileName: "Przykładowa_dzialka.dxf",
        enabled: true,
      },
      {
        id: "demo-2",
        name: "Drogi_wewnetrzne",
        assigned: "Warstwy pomocnicze",
        fileName: "Przykładowa_dzialka.dxf",
        enabled: true,
      }
    );
  }
  return layers;
}

function renderPlotLayers() {
  if (!plotLayerTableBody) return;
  plotLayerTableBody.innerHTML = "";
  if (!state.plotLayers.length) {
    plotLayerTableBody.innerHTML = "<div class=\"muted\">Brak warstw do wyświetlenia.</div>";
    return;
  }

  state.plotLayers.forEach((layer) => {
    const row = document.createElement("div");
    row.className = "parcel-layers-row";

    const name = document.createElement("div");
    name.className = "parcel-layer-name";
    name.textContent = layer.name;

    const assigned = document.createElement("div");
    assigned.className = "parcel-layer-meta";
    assigned.textContent = layer.assigned;

    const file = document.createElement("div");
    file.className = "parcel-layer-file";
    file.textContent = layer.fileName;

    const badge = document.createElement("div");
    badge.className = "parcel-layer-badge";
    badge.textContent = "Warstwa";

    const toggleWrap = document.createElement("div");
    toggleWrap.className = "parcel-layer-actions";
    const toggleBtn = document.createElement("button");
    toggleBtn.className = `parcel-layer-icon-btn ${layer.enabled ? "active" : "inactive"}`;
    toggleBtn.type = "button";
    toggleBtn.setAttribute("aria-label", layer.enabled ? "Wyłącz warstwę" : "Włącz warstwę");
    toggleBtn.textContent = layer.enabled ? "⏽" : "⏻";
    toggleBtn.addEventListener("click", () => {
      layer.enabled = !layer.enabled;
      renderPlotLayers();
    });
    toggleWrap.appendChild(toggleBtn);

    const removeWrap = document.createElement("div");
    removeWrap.className = "parcel-layer-actions";
    const removeBtn = document.createElement("button");
    removeBtn.className = "parcel-layer-icon-btn remove";
    removeBtn.type = "button";
    removeBtn.setAttribute("aria-label", "Usuń warstwę");
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", () => {
      state.plotLayers = state.plotLayers.filter((item) => item.id !== layer.id);
      renderPlotLayers();
    });
    removeWrap.appendChild(removeBtn);

    row.appendChild(name);
    row.appendChild(assigned);
    row.appendChild(file);
    row.appendChild(badge);
    row.appendChild(toggleWrap);
    row.appendChild(removeWrap);
    plotLayerTableBody.appendChild(row);
  });
}

async function selectPlotImport(importId) {
  const response = await fetch(`/api/plots/${importId}/boundaries`);
  const details = await response.json();
  if (!response.ok) {
    setParcelStatus("bad", details.error || "Nie udało się pobrać podglądu.");
    return;
  }
  state.activePlotImportId = importId;
  window.dispatchEvent(new CustomEvent("plot-imported", { detail: details }));
  updateParcelPreview(details);
  setParcelStatus("ok", "Podgląd działki załadowany.");
}

async function togglePlotImport(importId, disable) {
  const response = await fetch(`/api/plots/${importId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ isDisabled: disable }),
  });
  if (!response.ok) {
    const payload = await response.json();
    setParcelStatus("bad", payload.error || "Nie udało się zaktualizować pliku.");
    return;
  }
  if (disable && state.activePlotImportId === importId) {
    clearPlotPreview();
  }
  await loadPlotImports();
}

async function deletePlotImport(importId) {
  const response = await fetch(`/api/plots/${importId}`, { method: "DELETE" });
  if (!response.ok) {
    const payload = await response.json();
    setParcelStatus("bad", payload.error || "Nie udało się usunąć pliku.");
    return;
  }
  if (state.activePlotImportId === importId) {
    clearPlotPreview();
  }
  await loadPlotImports();
}

function renderParcels() {
  if (!parcelList) return;
  parcelList.innerHTML = "";
  state.parcels.forEach(parcel => {
    const chip = document.createElement("div");
    chip.className = "parcel-chip";
    chip.textContent = parcel.parcelId;
    parcelList.appendChild(chip);
  });
}

addParcelBtn?.addEventListener("click", async () => {
  const value = parcelIdInput?.value?.trim();
  if (!value) return;
  await fetch("/api/parcels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parcelId: value }),
  });
  parcelIdInput.value = "";
  loadParcels();
});

parcelFileInput?.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  await uploadParcelFile(file);
  event.target.value = "";
});

async function uploadParcelFile(file) {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".dxf") && !lower.endsWith(".dwg")) {
    setParcelStatus("warn", "Obsługiwane są tylko pliki DXF/DWG.");
    setParcelProgress("error");
    return;
  }

  try {
    setParcelStatus("", "");
    setParcelProgress("upload");
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/plots/upload", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) {
      setParcelStatus("bad", payload.error || "Nie udało się wgrać działki.");
      setParcelProgress("error");
      return;
    }

    setParcelProgress("parsing");
    const detailsResponse = await fetch(`/api/plots/${payload.importJobId}/boundaries`);
    const details = await detailsResponse.json();
    if (!detailsResponse.ok) {
      setParcelStatus("bad", details.error || "Nie udało się pobrać granic.");
      setParcelProgress("error");
      return;
    }

    window.dispatchEvent(new CustomEvent("plot-imported", { detail: details }));
    renderParcelDetails(details);
    setParcelProgress("done");
    setParcelStatus("ok", "Granice działki załadowane.");
    state.activePlotImportId = details.importJob?.id || null;
    updateParcelPreview(details);
    await loadPlotImports();
  } catch (error) {
    console.error("Parcel upload error:", error);
    setParcelStatus("bad", "Nie udało się zaimportować pliku.");
    setParcelProgress("error");
  }
}

function setParcelStatus(level, message) {
  if (!parcelUploadStatus) return;
  parcelUploadStatus.textContent = message;
  parcelUploadStatus.classList.remove("ok", "warn", "bad", "info");
  if (level) parcelUploadStatus.classList.add(level);
}

function setParcelProgress(stage) {
  if (!parcelUploadProgressBar) return;
  const progressMap = {
    idle: 0,
    upload: 25,
    parsing: 65,
    done: 100,
    error: 100,
  };
  const value = progressMap[stage] ?? 0;
  parcelUploadProgressBar.style.width = `${value}%`;
  parcelUploadProgressBar.classList.toggle("error", stage === "error");
}

function renderParcelDetails(details) {
  if (parcelUnitsInfo) {
    const units = details.importJob?.units || "—";
    const unitScale = Number.isFinite(details.importJob?.unitScale)
      ? details.importJob.unitScale.toFixed(4)
      : "—";
    const unitsSource = details.importJob?.unitsSource || "—";
    parcelUnitsInfo.innerHTML = `<strong>Jednostka:</strong> ${units} · <strong>Skala → m:</strong> ${unitScale} · <span class=\"muted\">${unitsSource}</span>`;
  }
  if (parcelBoundaryInfo) {
    const count = details.candidates?.length || 0;
    const selected = details.selectedBoundary?.metadata?.layer || "—";
    parcelBoundaryInfo.innerHTML = `<strong>Granice:</strong> ${count} · <strong>Główna:</strong> ${selected}`;
  }
  if (parcelLayerList) {
    const layers = details.layerSummary || [];
    parcelLayerList.innerHTML = layers.length
      ? layers
        .map((layer) => `<div class=\"parcel-layer-item\"><span>${layer.name}</span><span>${layer.entityCount}</span></div>`)
        .join("")
      : "<div class=\"muted\">Brak warstw.</div>";
  }
}

function coordsToPoints(coords) {
  if (!coords || coords.length < 3) return [];
  const points = coords.map(([x, y]) => ({ x, y }));
  const first = points[0];
  const last = points[points.length - 1];
  if (first && last && first.x === last.x && first.y === last.y) {
    points.pop();
  }
  return points;
}

function geojsonToPoints(geometry) {
  if (!geometry) return null;
  if (geometry.type === "Polygon") {
    return coordsToPoints(geometry.coordinates?.[0] || []);
  }
  if (geometry.type === "MultiPolygon") {
    const polygons = geometry.coordinates || [];
    let best = null;
    let bestArea = 0;
    polygons.forEach((polyCoords) => {
      const points = coordsToPoints(polyCoords?.[0] || []);
      if (points.length < 3) return;
      const area = Math.abs(polygonArea(points));
      if (area > bestArea) {
        bestArea = area;
        best = points;
      }
    });
    return best;
  }
  return null;
}

function polygonArea(points) {
  if (!points || points.length < 3) return 0;
  return points.reduce((acc, point, index) => {
    const next = points[(index + 1) % points.length];
    return acc + (point.x * next.y - next.x * point.y);
  }, 0) / 2;
}

function updateParcelPreview(details) {
  if (!parcelPreviewCanvas || !parcelPreviewEmpty || !parcelPreviewMeta) return;
  const candidate = details?.selectedBoundary || details?.candidates?.[0] || null;
  const points = geojsonToPoints(candidate?.geometry);
  if (!points || points.length < 3) {
    parcelPreviewEmpty.style.display = "grid";
    parcelPreviewMeta.innerHTML = "";
    parcelPreviewState.points = null;
    return;
  }

  parcelPreviewState.points = points;
  parcelPreviewState.layer = candidate?.metadata?.layer || "—";
  parcelPreviewState.area = candidate?.metadata?.area || null;
  parcelPreviewState.units = details?.importJob?.units || "—";

  renderParcelPreviewCanvas(points);
  parcelPreviewEmpty.style.display = "none";
  const areaText = Number.isFinite(parcelPreviewState.area)
    ? `${parcelPreviewState.area.toFixed(2)} m²`
    : "—";
  parcelPreviewMeta.innerHTML = `
    <div><strong>Warstwa:</strong> ${parcelPreviewState.layer}</div>
    <div><strong>Powierzchnia:</strong> ${areaText}</div>
    <div><strong>Jednostki:</strong> ${parcelPreviewState.units}</div>
  `;
}

function renderParcelPreviewCanvas(points) {
  const ctx = parcelPreviewCanvas?.getContext("2d");
  if (!ctx || !points?.length) return;
  const width = parcelPreviewCanvas.width;
  const height = parcelPreviewCanvas.height;
  ctx.clearRect(0, 0, width, height);

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  points.forEach((point) => {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  });
  const padding = 18;
  const scaleX = (width - padding * 2) / (maxX - minX || 1);
  const scaleY = (height - padding * 2) / (maxY - minY || 1);
  const scale = Math.min(scaleX, scaleY);
  const offsetX = padding + (width - padding * 2 - (maxX - minX) * scale) / 2;
  const offsetY = padding + (height - padding * 2 - (maxY - minY) * scale) / 2;

  ctx.beginPath();
  points.forEach((point, index) => {
    const x = offsetX + (point.x - minX) * scale;
    const y = height - (offsetY + (point.y - minY) * scale);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(56, 189, 248, 0.2)";
  ctx.strokeStyle = "rgba(56, 189, 248, 0.9)";
  ctx.lineWidth = 2;
  ctx.fill();
  ctx.stroke();
}

function clearPlotPreview() {
  state.activePlotImportId = null;
  if (parcelPreviewEmpty) parcelPreviewEmpty.style.display = "grid";
  if (parcelPreviewMeta) parcelPreviewMeta.innerHTML = "";
  if (parcelUploadStatus) {
    parcelUploadStatus.textContent = "Podgląd wyłączony dla wygaszonego pliku.";
    parcelUploadStatus.classList.remove("ok", "warn", "bad", "info");
  }
  window.dispatchEvent(new CustomEvent("plot-cleared"));
}

async function loadDocuments() {
  const responses = await Promise.all(
    DOCUMENT_TYPES.map(async (docType) => {
      const response = await fetch(`/api/documents?type=${docType.type}`);
      const payload = await response.json();
      state.documentsByType[docType.type] = payload.documents || [];
      return payload.documents || [];
    })
  );

  if (!state.activeDocumentId) {
    const latestDoc = responses.flat()[0];
    if (latestDoc) {
      state.activeDocumentId = latestDoc.id;
      state.activeDocumentType = latestDoc.type;
      await loadDocumentDetail(latestDoc.id);
    }
  }
  renderDocumentCards();
  renderDataForm();
}

async function loadDocumentDetail(documentId) {
  const response = await fetch(`/api/documents/${documentId}`);
  if (!response.ok) return;
  const payload = await response.json();
  const entries = payload.extractedData || [];
  state.extractedDataByDocument[documentId] = entries.reduce((acc, entry) => {
    acc[entry.parcelId] = entry;
    return acc;
  }, {});
}

function renderDocumentCards() {
  if (!documentCards) return;
  documentCards.innerHTML = "";
  const query = documentSearchInput?.value?.trim().toLowerCase() || "";

  DOCUMENT_TYPES.filter((docType) => docType.label.toLowerCase().includes(query)).forEach((docType) => {
    const card = document.createElement("div");
    card.className = "document-card";

    const header = document.createElement("div");
    header.className = "document-card-header";

    const title = document.createElement("div");
    title.className = "document-card-title";
    title.textContent = docType.label;

    const statusBadge = document.createElement("div");
    statusBadge.className = "document-status-badge";

    const documents = state.documentsByType[docType.type] || [];
    const currentDocument = documents[0] || null;
    if (currentDocument) {
      statusBadge.textContent = statusLabel(currentDocument.status, currentDocument.ocrStatus);
      statusBadge.classList.add(statusClass(currentDocument.status, currentDocument.ocrStatus));
    } else {
      statusBadge.textContent = "Brak";
      statusBadge.classList.add("error");
    }

    header.appendChild(title);
    header.appendChild(statusBadge);

    const dropzone = document.createElement("label");
    dropzone.className = "document-dropzone";
    dropzone.innerHTML = `<strong>${currentDocument ? "Zamień plik" : "Wgraj plik"}</strong><span class="muted">${docType.hint}</span>`;

    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf,.png,.jpg,.jpeg";
    input.addEventListener("change", async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      await handleDocumentUpload(file, docType.type);
      event.target.value = "";
    });

    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
    });
    dropzone.addEventListener("drop", async (event) => {
      event.preventDefault();
      const file = event.dataTransfer?.files?.[0];
      if (file) {
        await handleDocumentUpload(file, docType.type);
      }
    });

    dropzone.appendChild(input);

    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.innerHTML = currentDocument
      ? `
        <div><strong>Plik:</strong> ${currentDocument.fileName}</div>
        <div><strong>Wersja:</strong> ${currentDocument.version}</div>
        <div><strong>Data:</strong> ${formatDate(currentDocument.uploadedAt)}</div>
        <div><strong>Rozmiar:</strong> ${formatBytes(currentDocument.size)}</div>
      `
      : "<div class=\"muted\">Brak wgranego dokumentu.</div>";

    const actions = document.createElement("div");
    actions.className = "document-actions";

    const uploadBtn = document.createElement("button");
    uploadBtn.textContent = currentDocument ? "Zamień" : "Wgraj";
    uploadBtn.addEventListener("click", () => input.click());

    const ocrBtn = document.createElement("button");
    ocrBtn.textContent = "Zaczytaj ze skanu";
    ocrBtn.classList.add("secondary");
    ocrBtn.disabled = !currentDocument;
    ocrBtn.addEventListener("click", async () => {
      if (!currentDocument) return;
      await runOcr(currentDocument.id, state.activeParcelId);
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.textContent = "Usuń";
    deleteBtn.classList.add("danger");
    deleteBtn.disabled = !currentDocument;
    deleteBtn.addEventListener("click", async () => {
      if (!currentDocument) return;
      await deleteDocument(currentDocument.id);
    });

    actions.appendChild(uploadBtn);
    actions.appendChild(ocrBtn);
    actions.appendChild(deleteBtn);

    const toggleBtn = document.createElement("button");
    toggleBtn.className = "document-toggle";
    toggleBtn.textContent = state.expandedType === docType.type ? "Ukryj wersje" : "Pokaż wersje";
    toggleBtn.addEventListener("click", () => {
      state.expandedType = state.expandedType === docType.type ? null : docType.type;
      renderDocumentCards();
    });

    const history = document.createElement("div");
    history.className = "document-versions";
    if (state.expandedType !== docType.type) {
      history.classList.add("hidden");
    }
    history.innerHTML = `<div class="muted">Ostatnie wersje (max 3)</div>`;

    documents.slice(0, 3).forEach((doc) => {
      const item = document.createElement("div");
      item.className = "document-version-item";
      if (doc.id === state.activeDocumentId) {
        item.classList.add("active");
      }
      item.innerHTML = `
        <div>
          <div><strong>v${doc.version}</strong> · ${doc.fileName}</div>
          <div class="muted">${formatDate(doc.uploadedAt)}</div>
        </div>
        <div class="document-status-badge ${statusClass(doc.status, doc.ocrStatus)}">${statusLabel(doc.status, doc.ocrStatus)}</div>
      `;
      item.addEventListener("click", async () => {
        state.activeDocumentId = doc.id;
        state.activeDocumentType = doc.type;
        await loadDocumentDetail(doc.id);
        renderDocumentCards();
        renderDataForm();
      });
      history.appendChild(item);
    });

    if (state.errorsByType[docType.type]) {
      const error = document.createElement("div");
      error.className = "document-error";
      error.textContent = state.errorsByType[docType.type];
      card.appendChild(error);
    }

    card.appendChild(header);
    card.appendChild(dropzone);
    card.appendChild(meta);
    card.appendChild(actions);
    card.appendChild(toggleBtn);
    card.appendChild(history);
    documentCards.appendChild(card);
  });
}

function renderDataForm() {
  if (!documentDataPanel) return;
  documentDataPanel.innerHTML = "";

  const activeDocument = findActiveDocument();
  const effectiveParcelId = getEffectiveParcelId();
  if (state.activeParcelId !== effectiveParcelId) {
    state.activeParcelId = effectiveParcelId;
  }
  const extractedMap = activeDocument ? state.extractedDataByDocument[activeDocument.id] || {} : {};
  const extracted = extractedMap[effectiveParcelId] || null;
  const fieldsData = extracted?.fields || {};

  const header = document.createElement("div");
  header.className = "document-data-header";
  header.innerHTML = `
    <div><strong>Dokument:</strong> ${activeDocument ? activeDocument.fileName : "— brak wybranego dokumentu —"}</div>
    <div class="muted">Źródło danych: ${extracted?.source?.source || "manual"}</div>
  `;

  const fieldSearch = document.createElement("div");
  fieldSearch.className = "document-field-search";
  fieldSearch.innerHTML = `
    <label>Znajdź pole w formularzu</label>
    <input type="text" placeholder="Wpisz nazwę pola, np. przeznaczenie..." value="${state.fieldQuery}" />
    <span class="muted">Wszystkie pola pozostają widoczne.</span>
  `;
  const searchInput = fieldSearch.querySelector("input");
  searchInput?.addEventListener("input", () => {
    state.fieldQuery = searchInput.value.toLowerCase();
    renderDataForm();
  });

  const parcelRow = document.createElement("div");
  parcelRow.className = "document-data-row";
  const parcelLabel = document.createElement("label");
  parcelLabel.textContent = "Działka";
  const parcelSelect = document.createElement("select");
  if (!state.parcels.length) {
    parcelSelect.innerHTML = `<option value="_global">— brak przypisania —</option>`;
  }
  state.parcels.forEach((parcel) => {
    const option = document.createElement("option");
    option.value = parcel.parcelId;
    option.textContent = parcel.parcelId;
    if (parcel.parcelId === state.activeParcelId) {
      option.selected = true;
    }
    parcelSelect.appendChild(option);
  });
  parcelSelect.addEventListener("change", async () => {
    state.activeParcelId = parcelSelect.value;
    if (activeDocument.id) {
      await loadDocumentDetail(activeDocument.id);
    }
    renderDataForm();
  });
  parcelRow.appendChild(parcelLabel);
  parcelRow.appendChild(parcelSelect);

  const grid = document.createElement("div");
  grid.className = "document-data-grid";

  let currentSection = null;
  MPZP_FIELDS.forEach((field) => {
    if (field.section && field.section !== currentSection) {
      currentSection = field.section;
      const sectionTitle = document.createElement("div");
      sectionTitle.className = "document-section-title";
      sectionTitle.textContent = field.section;
      grid.appendChild(sectionTitle);
    }
    const row = document.createElement("div");
    row.className = "document-data-row";
    if (state.fieldQuery && field.label.toLowerCase().includes(state.fieldQuery)) {
      row.classList.add("match");
    }
    const label = document.createElement("label");
    label.textContent = field.label;
    row.appendChild(label);

    if (field.type === "textarea") {
      const textarea = document.createElement("textarea");
      textarea.rows = 3;
      textarea.value = fieldValueToString(fieldsData[field.key]);
      textarea.dataset.fieldKey = field.key;
      row.appendChild(textarea);
    } else if (field.type === "select") {
      const select = document.createElement("select");
      select.dataset.fieldKey = field.key;
      field.options.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        if (fieldsData[field.key] === optionValue) {
          option.selected = true;
        }
        select.appendChild(option);
      });
      row.appendChild(select);
    } else if (field.unitOptions) {
      const wrapper = document.createElement("div");
      wrapper.style.display = "flex";
      wrapper.style.gap = "6px";
      const input = document.createElement("input");
      input.type = "number";
      input.step = "0.01";
      input.value = fieldsData[field.key]?.value ?? "";
      input.dataset.fieldKey = field.key;
      input.dataset.fieldRole = "value";
      const select = document.createElement("select");
      select.dataset.fieldKey = field.key;
      select.dataset.fieldRole = "unit";
      field.unitOptions.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        if (fieldsData[field.key]?.unit === optionValue) {
          option.selected = true;
        }
        select.appendChild(option);
      });
      wrapper.appendChild(input);
      wrapper.appendChild(select);
      row.appendChild(wrapper);
    } else {
      const input = document.createElement("input");
      input.type = field.type;
      input.step = field.type === "number" ? "0.01" : undefined;
      input.value = fieldValueToString(fieldsData[field.key]);
      input.dataset.fieldKey = field.key;
      row.appendChild(input);
    }

    grid.appendChild(row);
  });

  const actions = document.createElement("div");
  actions.className = "document-data-actions";

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Zapisz dane";
  saveBtn.addEventListener("click", async () => {
    if (!activeDocument) return;
    const parcelId = getEffectiveParcelId();
    const payload = collectFormValues(documentDataPanel);
    await saveDocumentData(activeDocument.id, payload, parcelId);
  });
  if (!activeDocument) {
    saveBtn.disabled = true;
  }

  const editBtn = document.createElement("button");
  editBtn.textContent = "Edytuj ręcznie";
  editBtn.classList.add("secondary");
  editBtn.addEventListener("click", () => {
    documentDataPanel.querySelector("input, textarea, select")?.focus();
  });

  actions.appendChild(saveBtn);
  actions.appendChild(editBtn);

  documentDataPanel.appendChild(header);
  documentDataPanel.appendChild(fieldSearch);
  documentDataPanel.appendChild(parcelRow);
  documentDataPanel.appendChild(grid);
  documentDataPanel.appendChild(actions);

  if (activeDocument) {
    const bindAutosave = async () => {
      const parcelId = getEffectiveParcelId();
      const payload = collectFormValues(documentDataPanel);
      const localEntry = getOrCreateExtractedEntry(activeDocument.id, parcelId);
      localEntry.fields = payload;
      localEntry.source = { source: "manual" };
      if (autosaveTimerId) {
        clearTimeout(autosaveTimerId);
      }
      autosaveTimerId = window.setTimeout(async () => {
        await saveDocumentData(activeDocument.id, payload, parcelId, { rerender: false });
      }, 450);
    };
    documentDataPanel.querySelectorAll("[data-field-key]").forEach((input) => {
      input.addEventListener("input", bindAutosave);
      input.addEventListener("change", bindAutosave);
    });
  }
}

async function handleDocumentUpload(file, documentType) {
  state.errorsByType[documentType] = "";

  if (!isAllowedDocument(file)) {
    state.errorsByType[documentType] = "Nieobsługiwany format. Dozwolone: PDF/JPG/PNG.";
    renderDocumentCards();
    return;
  }
  if (file.size > DOCUMENT_MAX_SIZE_MB * 1024 * 1024) {
    state.errorsByType[documentType] = `Plik jest za duży (max ${DOCUMENT_MAX_SIZE_MB} MB).`;
    renderDocumentCards();
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("type", documentType);
  const response = await fetch("/api/documents", { method: "POST", body: formData });
  if (!response.ok) {
    const payload = await response.json();
    state.errorsByType[documentType] = payload.error || "Nie udało się wgrać pliku.";
    renderDocumentCards();
    return;
  }

  const payload = await response.json();
  state.activeDocumentId = payload.documentId;
  state.activeDocumentType = documentType;
  await loadDocumentDetail(payload.documentId);
  await loadDocuments();

  try {
    await runOcr(payload.documentId, state.activeParcelId);
  } catch (_error) {
    state.errorsByType[documentType] = "Plik wgrany, ale automatyczne zaczytanie nie powiodło się. Użyj przycisku: Zaczytaj ze skanu.";
    renderDocumentCards();
  }
}

async function deleteDocument(documentId) {
  await fetch(`/api/documents/${documentId}`, { method: "DELETE" });
  state.activeDocumentId = null;
  state.activeDocumentType = null;
  await loadDocuments();
}

async function runOcr(documentId, parcelId) {
  const targetParcelId = parcelId || getEffectiveParcelId();
  await fetch(`/api/documents/${documentId}/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parcelId: targetParcelId }),
  });
  await pollDocument(documentId);
}

async function pollDocument(documentId) {
  const response = await fetch(`/api/documents/${documentId}`);
  if (!response.ok) return;
  const payload = await response.json();
  const document = payload.document;
  const entries = payload.extractedData || [];
  state.extractedDataByDocument[documentId] = entries.reduce((acc, entry) => {
    acc[entry.parcelId] = entry;
    return acc;
  }, {});

  if (document.ocrStatus === "PROCESSING") {
    setTimeout(() => pollDocument(documentId), 1200);
    return;
  }

  await loadDocuments();
}

async function saveDocumentData(documentId, fields, parcelId, options = {}) {
  const { rerender = true } = options;
  await fetch(`/api/documents/${documentId}/data`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields, source: { source: "manual" }, parcelId }),
  });
  await loadDocumentDetail(documentId);
  if (rerender) {
    renderDataForm();
  }
}

function collectFormValues(root) {
  const values = {};
  MPZP_FIELDS.forEach((field) => {
    if (field.unitOptions) {
      const valueInput = root.querySelector(`[data-field-key="${field.key}"][data-field-role="value"]`);
      const unitSelect = root.querySelector(`[data-field-key="${field.key}"][data-field-role="unit"]`);
      const rawValue = valueInput?.value;
      if (rawValue || unitSelect?.value) {
        values[field.key] = {
          value: rawValue ? Number(rawValue) : null,
          unit: unitSelect?.value || field.unitOptions[0],
        };
      }
      return;
    }
    const fieldInput = root.querySelector(`[data-field-key="${field.key}"]`);
    if (!fieldInput) return;
    const raw = fieldInput.value;
    if (!raw) return;
    if (field.type === "select") {
      values[field.key] = raw;
      return;
    }
    values[field.key] = field.type === "number" ? Number(raw) : raw;
  });
  return values;
}

function fieldValueToString(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return value.value ?? "";
  return String(value);
}

function isAllowedDocument(file) {
  const allowed = ["application/pdf", "image/png", "image/jpeg"];
  return allowed.includes(file.type);
}

function statusLabel(status, ocrStatus) {
  if (status === "PROCESSING" || ocrStatus === "PROCESSING") return "Przetwarzanie";
  if (status === "READY") return "Gotowe";
  if (status === "ERROR") return "Błąd";
  return "Brak";
}

function statusClass(status, ocrStatus) {
  if (status === "PROCESSING" || ocrStatus === "PROCESSING") return "processing";
  if (status === "READY") return "ready";
  if (status === "ERROR") return "error";
  return "error";
}

function findActiveDocument() {
  if (!state.activeDocumentId) return null;
  for (const docType of DOCUMENT_TYPES) {
    const docs = state.documentsByType[docType.type] || [];
    const found = docs.find((doc) => doc.id === state.activeDocumentId);
    if (found) return found;
  }
  return null;
}

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" });
}

loadParcels();
loadDocuments();
