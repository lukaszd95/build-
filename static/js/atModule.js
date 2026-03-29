const INDUSTRY_BADGE_STYLES = {
  "Architektura": "border-violet-300 bg-violet-50 text-violet-700",
  "PZT": "border-sky-300 bg-sky-50 text-sky-700",
  "Konstrukcja": "border-amber-300 bg-amber-50 text-amber-700",
  "Elektryka": "border-yellow-300 bg-yellow-50 text-yellow-700",
  "Wod-kan": "border-cyan-300 bg-cyan-50 text-cyan-700",
  "Wentylacja": "border-indigo-300 bg-indigo-50 text-indigo-700",
  "Nieznana": "border-zinc-300 bg-zinc-100 text-zinc-600",
  "Wiele branż": "border-fuchsia-300 bg-fuchsia-50 text-fuchsia-700",
};
const CONTENT_TYPE_OPTIONS = ["Opis", "Rzut", "Przekrój", "Elewacja", "Schemat", "Zestawienie", "Detal", "Plan sytuacyjny / PZT", "Legenda", "Inna / Nieznana"];

const CONTENT_TYPE_BADGE_STYLES = {
  "Opis": "border-slate-300 bg-slate-50 text-slate-700",
  "Rzut": "border-blue-300 bg-blue-50 text-blue-700",
  "Przekrój": "border-indigo-300 bg-indigo-50 text-indigo-700",
  "Elewacja": "border-emerald-300 bg-emerald-50 text-emerald-700",
  "Schemat": "border-yellow-300 bg-yellow-50 text-yellow-700",
  "Zestawienie": "border-orange-300 bg-orange-50 text-orange-700",
  "Detal": "border-rose-300 bg-rose-50 text-rose-700",
  "Plan sytuacyjny / PZT": "border-cyan-300 bg-cyan-50 text-cyan-700",
  "Legenda": "border-teal-300 bg-teal-50 text-teal-700",
  "Inna / Nieznana": "border-zinc-300 bg-zinc-100 text-zinc-600",
};
const SCALE_SOURCE_LABELS = {
  title_block_scale: "z tabelki/ramki",
  drawing_label_scale: "z opisu rysunku",
  text_scale_detected: "z tekstu",
  dimension_inferred_scale: "wyliczona z wymiarów",
  manual_override: "ręczna",
};

function normalizeIndustryName(industry) {
  return industry || "Nieznana";
}

function getIndustryBadgeClass(industry) {
  return INDUSTRY_BADGE_STYLES[normalizeIndustryName(industry)] || INDUSTRY_BADGE_STYLES["Nieznana"];
}
function normalizeContentType(contentType) {
  return contentType || "Inna / Nieznana";
}
function getContentTypeBadgeClass(contentType) {
  return CONTENT_TYPE_BADGE_STYLES[normalizeContentType(contentType)] || CONTENT_TYPE_BADGE_STYLES["Inna / Nieznana"];
}

function getIndustryLabel(item) {
  if (item.processingStatus === "CLASSIFYING_INDUSTRY") return "W trakcie rozpoznawania";
  if (item.processingStatus === "INDUSTRY_CLASSIFICATION_FAILED") return "Błąd klasyfikacji";
  return normalizeIndustryName(item.detectedIndustry);
}

function buildIndustryDetailsText(item) {
  const industries = Array.isArray(item.detectedIndustries) && item.detectedIndustries.length
    ? item.detectedIndustries.join(", ")
    : "—";
  const confidenceValue = Number(item.industryConfidence);
  const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "—";
  const reason = item.industryClassificationReason || "Brak uzasadnienia klasyfikacji.";
  const signalCount = Array.isArray(item.industrySignals) ? item.industrySignals.length : 0;
  const details = item.industryClassificationDetails || {};
  const scoreBreakdown = details.industryScoreBreakdown || {};
  const topScores = Array.isArray(scoreBreakdown.topScores) ? scoreBreakdown.topScores.slice(0, 3) : [];
  const scoreInfo = topScores.length
    ? topScores.map((entry) => `${entry.industry}: ${entry.score}`).join(", ")
    : "—";
  const pageResults = Array.isArray(details.pageIndustryResults) ? details.pageIndustryResults : [];
  const pageInfo = pageResults.length
    ? pageResults.map((entry) => `s.${entry.pageNumber}:${entry.detectedIndustry}`).join("; ")
    : "—";
  return [
    `Branża główna: ${getIndustryLabel(item)}`,
    `Wykryte branże: ${industries}`,
    `Pewność: ${confidence}`,
    `Sygnały: ${signalCount}`,
    `Top scoring: ${scoreInfo}`,
    `Per strona: ${pageInfo}`,
    `Uzasadnienie: ${reason}`,
  ].join("\n");
}
function buildContentTypeDetailsText(item) {
  const contentTypes = Array.isArray(item.detectedContentTypes) && item.detectedContentTypes.length
    ? item.detectedContentTypes.join(", ")
    : "—";
  const confidenceValue = Number(item.contentTypeConfidence);
  const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "—";
  const reason = item.contentTypeReason || "Brak uzasadnienia klasyfikacji typu zawartości.";
  const pagesSummary = item.contentTypePagesSummary || {};
  const summary = Object.entries(pagesSummary).map(([name, count]) => `${name}: ${count}`).join(", ") || "—";
  const pageResults = Array.isArray(item.pageContentResults) ? item.pageContentResults : [];
  const topPages = pageResults.slice(0, 6).map((entry) => {
    const pageConfidence = Number.isFinite(Number(entry.confidence)) ? `${Math.round(Number(entry.confidence) * 100)}%` : "—";
    const origin = entry.isUserOverridden ? "user" : "system";
    return `s.${entry.pageNumber}: ${entry.detectedContentType} (${pageConfidence}, ${origin})`;
  }).join("; ") || "—";
  const diagnostics = pageResults.slice(0, 3).map((entry) => {
    const positives = Array.isArray(entry.topPositiveSignals) ? entry.topPositiveSignals.slice(0, 2).map((signal) => `${signal.contentType}:${signal.phrase}`).join(", ") : "—";
    const conflicts = Array.isArray(entry.topConflictSignals) ? entry.topConflictSignals.slice(0, 2).map((signal) => `${signal.contentType}:${signal.phrase}`).join(", ") : "—";
    return `s.${entry.pageNumber} +[${positives}] -[${conflicts}]`;
  }).join("; ") || "—";
  return [
    `Typ główny: ${normalizeContentType(item.detectedContentType)}`,
    `Czy mieszany: ${item.isMixedContent ? "tak" : "nie"}`,
    `Wykryte typy: ${contentTypes}`,
    `Pewność: ${confidence}`,
    `Podsumowanie stron: ${summary}`,
    `Strony: ${topPages}`,
    `Diagnostyka: ${diagnostics}`,
    `Uzasadnienie: ${reason}`,
  ].join("\n");
}

function buildProjectIdentitySummary(item) {
  const title = item.projectTitleDetected || "—";
  const location = item.investmentAddressDetected || item.plotNumberDetected || "—";
  const confidenceValue = Number(item.projectIdentityConfidence);
  const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "—";
  return `Nazwa inwestycji: ${title} | Adres/działka: ${location} | Pewność projektu: ${confidence}`;
}

function buildRejectedOfficeInfo(item) {
  const rejected = item?.projectIdentitySignals?.rejectedOfficeAddressSignals;
  if (!Array.isArray(rejected) || !rejected.length) return "Brak odrzuconych adresów biura.";
  return `Odrzucone adresy biura: ${rejected.map((entry) => entry.value).join(" | ")}`;
}

function buildProjectIdentityDiagnostics(item) {
  const signals = item?.projectIdentitySignals || {};
  const titleCandidates = Array.isArray(signals.projectTitleCandidates) ? signals.projectTitleCandidates : [];
  const addressCandidates = Array.isArray(signals.investmentAddressCandidates) ? signals.investmentAddressCandidates : [];
  const plotCandidates = Array.isArray(signals.plotNumberCandidates) ? signals.plotNumberCandidates : [];
  const rejectedTitles = Array.isArray(signals.rejectedProjectTitleCandidates) ? signals.rejectedProjectTitleCandidates : [];
  const rejectedAddresses = Array.isArray(signals.rejectedInvestmentAddressCandidates) ? signals.rejectedInvestmentAddressCandidates : [];
  const rejectedPlots = Array.isArray(signals.rejectedPlotNumberCandidates) ? signals.rejectedPlotNumberCandidates : [];
  const identityCandidates = Array.isArray(signals.documentProjectIdentityCandidates) ? signals.documentProjectIdentityCandidates : [];
  const composed = identityCandidates.some((entry) => entry.composedFromMultipleSources);
  const topPlots = plotCandidates.slice(0, 3).map((entry) => `${entry.value} (${Math.round((Number(entry.confidence) || 0) * 100)}%)`).join(" | ") || "—";
  return [
    `Plot candidates: ${topPlots}`,
    `Title candidates: ${titleCandidates.length}, Address candidates: ${addressCandidates.length}, Identity candidates: ${identityCandidates.length}`,
    `Composed from multiple sources: ${composed ? "tak" : "nie"}`,
    `Rejected title/address/plot: ${rejectedTitles.length}/${rejectedAddresses.length}/${rejectedPlots.length}`,
  ].join("\n");
}

function buildLineExtractionStats(page) {
  const lines = Array.isArray(page?.lines) ? page.lines : [];
  let horizontal = 0;
  let vertical = 0;
  let diagonal = 0;
  let totalLength = 0;
  for (const line of lines) {
    const angle = Number(line.angle) || 0;
    totalLength += Number(line.length) || 0;
    const normalized = Math.min(Math.abs(angle), Math.abs(180 - angle), Math.abs(360 - angle));
    if (normalized <= 12) horizontal += 1;
    else if (Math.abs(90 - normalized) <= 12) vertical += 1;
    else diagonal += 1;
  }
  const avg = lines.length ? (totalLength / lines.length) : 0;
  return {
    lineCount: lines.length,
    source: page?.extractionSource || "—",
    confidence: Number.isFinite(Number(page?.extractionConfidence)) ? Number(page.extractionConfidence) : null,
    averageLength: avg,
    horizontal,
    vertical,
    diagonal,
  };
}
function normalizeScaleStatus(page) {
  if (!page) return "wymaga potwierdzenia";
  if (page.scaleSource === "manual_override") return "ustawiona ręcznie";
  if (page.scaleConflictDetected) return "konflikt";
  if (page.scaleSource === "dimension_inferred_scale") return "wyliczono z wymiarów";
  if (page.detectedScaleNormalized) return "wykryto";
  return "wymaga potwierdzenia";
}
function buildScaleSummary(page) {
  const normalized = page?.detectedScaleNormalized || "—";
  const confidenceValue = Number(page?.scaleConfidence);
  const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "—";
  const source = SCALE_SOURCE_LABELS[page?.scaleSource] || "—";
  return `Skala: ${normalized} | Źródło: ${source} | Confidence: ${confidence} | Status: ${normalizeScaleStatus(page)}`;
}
function formatRealLength(line, unit = "mm") {
  const value = Number(line?.realLength);
  if (!Number.isFinite(value)) return "—";
  if (unit === "m") return `${(value / 1000).toFixed(3)} m`;
  if (unit === "cm") return `${(value / 10).toFixed(2)} cm`;
  return `${value.toFixed(2)} mm`;
}
function formatDimensionCandidate(dimension) {
  const value = Number(dimension?.value);
  const valueMm = Number(dimension?.valueMm);
  const unit = (dimension?.unit || "mm").toLowerCase();
  if (!Number.isFinite(value) || !Number.isFinite(valueMm)) return "—";
  if (unit === "cm") {
    return `${value.toFixed(2)} cm (${valueMm.toFixed(2)} mm)`;
  }
  if (unit === "m") {
    return `${value.toFixed(3)} m (${valueMm.toFixed(2)} mm)`;
  }
  return `${valueMm.toFixed(2)} mm`;
}

if (typeof window !== "undefined") {
  window.__AT_INDUSTRY_UI__ = {
    getIndustryBadgeClass, getIndustryLabel, buildIndustryDetailsText,
    getContentTypeBadgeClass, buildContentTypeDetailsText, normalizeContentType,
  };
  window.__AT_PROJECT_IDENTITY_UI__ = {
    buildProjectIdentitySummary,
    buildRejectedOfficeInfo,
    buildProjectIdentityDiagnostics,
    buildLineExtractionStats,
  };
  window.__AT_SCALE_UI__ = {
    normalizeScaleStatus,
    buildScaleSummary,
    formatRealLength,
    formatDimensionCandidate,
    formatAxisDirection(direction) {
      if (direction === "horizontal") return "pozioma";
      if (direction === "vertical") return "pionowa";
      return "ukośna";
    },
  };
}

const atModule = document.getElementById("atModule");

if (atModule) {
  const maxSizeMb = Number(atModule.dataset.atMaxSizeMb || 40);
  const maxFiles = Number(atModule.dataset.atMaxFiles || 20);
  const atDropzone = document.getElementById("atDropzone");
  const atFileInput = document.getElementById("atFileInput");
  const atChooseFilesBtn = document.getElementById("atChooseFilesBtn");
  const atClearQueueBtn = document.getElementById("atClearQueueBtn");
  const atStartProcessingBtn = document.getElementById("atStartProcessingBtn");
  const atFileList = document.getElementById("atFileList");
  const atEmptyState = document.getElementById("atEmptyState");
  const atValidationMessage = document.getElementById("atValidationMessage");
  const atStatusBoard = document.getElementById("atStatusBoard");
  const atCloseWindowBtn = document.getElementById("atCloseWindowBtn");
  const atLinesViewer = document.getElementById("atLinesViewer");
  const atLinesPageSelect = document.getElementById("atLinesPageSelect");
  const atLinesRefreshBtn = document.getElementById("atLinesRefreshBtn");
  const atLinesToggle = document.getElementById("atLinesToggle");
  const atLinesMinLength = document.getElementById("atLinesMinLength");
  const atLinesStatsToggle = document.getElementById("atLinesStatsToggle");
  const atLinesMeta = document.getElementById("atLinesMeta");
  const atLinesSvgOverlay = document.getElementById("atLinesSvgOverlay");
  const atLinesSourceBadge = document.getElementById("atLinesSourceBadge");
  const atLinesStats = document.getElementById("atLinesStats");
  const atScaleBadge = document.getElementById("atScaleBadge");
  const atScaleSource = document.getElementById("atScaleSource");
  const atScaleStatus = document.getElementById("atScaleStatus");
  const atScaleConfidence = document.getElementById("atScaleConfidence");
  const atScaleDiagnostics = document.getElementById("atScaleDiagnostics");
  const atScaleDetectBtn = document.getElementById("atScaleDetectBtn");
  const atScaleRetryBtn = document.getElementById("atScaleRetryBtn");
  const atScaleOverrideBtn = document.getElementById("atScaleOverrideBtn");
  const atLineMeasurement = document.getElementById("atLineMeasurement");
  const atAxesDetectBtn = document.getElementById("atAxesDetectBtn");
  const atAxesRetryBtn = document.getElementById("atAxesRetryBtn");
  const atAxesToggle = document.getElementById("atAxesToggle");
  const atAxesLabelsToggle = document.getElementById("atAxesLabelsToggle");
  const atAxesConfidenceToggle = document.getElementById("atAxesConfidenceToggle");
  const atAxesMinConfidence = document.getElementById("atAxesMinConfidence");
  const atAxesList = document.getElementById("atAxesList");

  const state = {
    queue: [],
    uploading: false,
    selectedDocumentId: null,
    linesByPage: {},
    axesByPage: {},
  };

  const statusLabels = {
    READY: "gotowy do wysłania",
    UPLOADING: "wysyłanie",
    UPLOADED: "przesłano",
    ANALYZING: "analizowanie",
    CLASSIFYING_INDUSTRY: "rozpoznawanie branży",
    CLASSIFYING_CONTENT_TYPE: "rozpoznawanie typu zawartości",
    INDUSTRY_CLASSIFIED: "branża rozpoznana",
    INDUSTRY_CLASSIFICATION_FAILED: "błąd klasyfikacji branży",
    ERROR: "błąd",
    COMPLETED: "ukończono",
    matching_pending: "oczekuje na matching projektu",
    review_required: "wymaga review",
    project_matched: "dopasowano do projektu",
    project_created: "utworzono nowy projekt",
    manually_assigned: "ręcznie przypisany",
    manually_reviewed: "ręczna korekta",
  };

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    return `${size.toFixed(size >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
  }

  function showMessage(message, variant = "error") {
    if (!message) {
      atValidationMessage.className = "mb-2 hidden rounded-lg border px-3 py-2 text-xs";
      atValidationMessage.textContent = "";
      return;
    }
    atValidationMessage.className = variant === "success"
      ? "mb-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-700"
      : "mb-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700";
    atValidationMessage.textContent = message;
  }

  function validateFile(file) {
    if (!file) return { ok: false, message: "Nie wybrano pliku." };
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return { ok: false, message: `Plik ${file.name} nie jest PDF.` };
    }
    if (file.size <= 0) {
      return { ok: false, message: `Plik ${file.name} jest pusty.` };
    }
    if (file.size > maxSizeMb * 1024 * 1024) {
      return { ok: false, message: `Plik ${file.name} przekracza limit ${maxSizeMb} MB.` };
    }
    return { ok: true };
  }

  function isDuplicate(file) {
    return state.queue.some((item) => item.file.name === file.name && item.file.size === file.size);
  }

  function removeQueuedFile(localId) {
    state.queue = state.queue.filter((item) => item.localId !== localId);
    render();
  }

  function render() {
    atFileList.innerHTML = "";
    atEmptyState.classList.toggle("hidden", state.queue.length > 0);
    atStartProcessingBtn.disabled = state.queue.length === 0 || state.uploading;

    state.queue.forEach((item) => {
      const row = document.createElement("div");
      row.className = "at-file-row";
      const statusText = statusLabels[item.status] || item.status;
      const industryLabel = getIndustryLabel(item);
      const contentTypeLabel = normalizeContentType(item.detectedContentType);
      const confidenceValue = Number(item.industryConfidence);
      const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "—";
      const contentTypeConfidenceValue = Number(item.contentTypeConfidence);
      const contentTypeConfidence = Number.isFinite(contentTypeConfidenceValue) ? `${Math.round(contentTypeConfidenceValue * 100)}%` : "—";
      const projectIdentityConfidenceValue = Number(item.projectIdentityConfidence);
      const projectIdentityConfidence = Number.isFinite(projectIdentityConfidenceValue) ? `${Math.round(projectIdentityConfidenceValue * 100)}%` : "—";
      const projectStatus = item.projectAssignmentStatus || "unassigned";
      row.innerHTML = `
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <div class="truncate text-sm font-semibold text-zinc-900">${item.file.name}</div>
            <span class="at-status-badge">${statusText}</span>
            <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${getIndustryBadgeClass(industryLabel)}">${industryLabel}</span>
            <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${getContentTypeBadgeClass(contentTypeLabel)}">${contentTypeLabel}${item.isMixedContent ? " (mieszany)" : ""}</span>
          </div>
          <div class="at-file-meta">
            <span>Rozmiar: ${formatBytes(item.file.size)}</span>
            <span>Dodano: ${new Date(item.addedAt).toLocaleString("pl-PL")}</span>
            <span>Postęp: ${item.progress}%</span>
            <span>Pewność: ${confidence}</span>
            <span>Pewność typu: ${contentTypeConfidence}</span>
            <span>Pewność projektu: ${projectIdentityConfidence}</span>
            <span>Status projektu: ${statusLabels[projectStatus] || projectStatus}</span>
          </div>
          <div class="mt-1 text-xs text-zinc-700">Nazwa inwestycji: ${item.projectTitleDetected || "—"}</div>
          <div class="mt-1 text-xs text-zinc-700">Adres / działka: ${item.investmentAddressDetected || item.plotNumberDetected || "—"}</div>
          <div class="mt-1 text-xs text-zinc-700">Działki: ${Array.isArray(item.projectIdentitySignals?.plotNumbersNormalized) && item.projectIdentitySignals.plotNumbersNormalized.length ? item.projectIdentitySignals.plotNumbersNormalized.join(", ") : (item.plotNumberDetected || "—")}</div>
          <div class="mt-1 text-xs text-zinc-700">Ekstrakcja linii: ${(item.lineExtractionSummary?.pages || 0)} stron / ${(item.lineExtractionSummary?.totalLines || 0)} linii</div>
          ${(item.projectIdentitySignals?.rejectedOfficeAddressSignals?.length)
            ? `<div class="mt-1 text-xs text-amber-700">Odrzucone adresy biura: ${item.projectIdentitySignals.rejectedOfficeAddressSignals.map((s) => s.value).join(" | ")}</div>`
            : ""
          }
          ${(item.projectIdentitySignals?.rejectedProjectTitleCandidates?.length || item.projectIdentitySignals?.rejectedPlotNumberCandidates?.length)
            ? `<div class="mt-1 text-xs text-amber-700">Odrzucone kandydaty: tytuł ${item.projectIdentitySignals?.rejectedProjectTitleCandidates?.length || 0}, działka ${item.projectIdentitySignals?.rejectedPlotNumberCandidates?.length || 0}</div>`
            : ""
          }
          ${item.industryClassificationReason ? `<div class="mt-1 text-xs text-zinc-600">${item.industryClassificationReason}</div>` : ""}
          ${item.error ? `<div class="mt-1 text-xs text-rose-600">${item.error}</div>` : ""}
        </div>
        <div class="flex items-center gap-1">
          <button type="button" class="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-gray-50" data-action="details">Szczegóły</button>
          <button type="button" class="rounded-full border border-zinc-300 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-zinc-100" data-action="retry-classification">Klasyfikuj ponownie</button>
          <button type="button" class="rounded-full border border-zinc-300 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-zinc-100" data-action="retry-content-type">Typy stron ponownie</button>
          <button type="button" class="rounded-full border border-cyan-300 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700 hover:bg-cyan-100" data-action="retry-project">Matching projektu</button>
          <button type="button" class="rounded-full border border-sky-300 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-100" data-action="override-project">Korekta projektu</button>
          <button type="button" class="rounded-full border border-violet-300 bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700 hover:bg-violet-100" data-action="override-page">Korekta strony</button>
          <button type="button" class="rounded-full border border-blue-300 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100" data-action="lines">Linie rzutu</button>
          <button type="button" class="rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-100" data-action="retry">Ponów</button>
          <button type="button" class="rounded-full border border-rose-300 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100" data-action="remove">Usuń</button>
        </div>
      `;

      row.querySelector('[data-action="remove"]').addEventListener("click", () => removeQueuedFile(item.localId));
      row.querySelector('[data-action="details"]').addEventListener("click", () => {
        showMessage(`${buildIndustryDetailsText(item)}\n\n${buildContentTypeDetailsText(item)}\n\n${buildProjectIdentitySummary(item)}\n${buildRejectedOfficeInfo(item)}\n${buildProjectIdentityDiagnostics(item)}`, "success");
      });
      row.querySelector('[data-action="retry"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await retryProcessing(item);
      });
      row.querySelector('[data-action="retry-classification"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await retryClassification(item);
      });
      row.querySelector('[data-action="retry-content-type"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await retryContentTypeClassification(item);
      });
      row.querySelector('[data-action="retry-project"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await retryProjectMatching(item);
      });
      row.querySelector('[data-action="override-project"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        const projectTitle = window.prompt("Podaj poprawną nazwę inwestycji:", item.projectTitleDetected || "");
        if (projectTitle === null) return;
        const investmentAddress = window.prompt("Podaj poprawny adres inwestycji:", item.investmentAddressDetected || "");
        if (investmentAddress === null) return;
        const plotNumber = window.prompt("Podaj poprawny numer działki:", item.plotNumberDetected || "");
        if (plotNumber === null) return;
        const reason = window.prompt("Powód korekty (opcjonalnie):", "");
        await overrideProjectIdentity(item, { projectTitle, investmentAddress, plotNumber, reason });
      });
      row.querySelector('[data-action="override-page"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        const pageNumberRaw = window.prompt("Podaj numer strony do korekty:", "1");
        const pageNumber = Number(pageNumberRaw);
        if (!Number.isInteger(pageNumber) || pageNumber <= 0) return;
        const typeHint = `Podaj typ (${CONTENT_TYPE_OPTIONS.join(", ")}):`;
        const overrideType = window.prompt(typeHint, item.detectedContentType || "Inna / Nieznana");
        if (!overrideType) return;
        const reason = window.prompt("Powód korekty (opcjonalnie):", "");
        try {
          await overridePageContentType(item, pageNumber, overrideType, reason || "");
          atStatusBoard.textContent = `Zapisano korektę typu strony s.${pageNumber} dla ${item.file.name}.`;
        } catch (error) {
          showMessage(error.message || "Nie udało się zapisać korekty strony.");
        }
      });
      row.querySelector('[data-action="lines"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await openLinesViewer(item);
      });

      atFileList.appendChild(row);
    });
  }

  function enqueueFiles(files) {
    const incoming = Array.from(files || []);
    if (!incoming.length) return;

    if (state.queue.length + incoming.length > maxFiles) {
      showMessage(`Limit plików został przekroczony. Maksymalnie ${maxFiles}.`);
      return;
    }

    const errors = [];
    for (const file of incoming) {
      const valid = validateFile(file);
      if (!valid.ok) {
        errors.push(valid.message);
        continue;
      }
      if (isDuplicate(file)) {
        errors.push(`Plik ${file.name} jest już na liście.`);
        continue;
      }
      state.queue.push({
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        file,
        status: "READY",
        progress: 0,
        addedAt: new Date().toISOString(),
        documentId: null,
        error: null,
        detectedIndustry: "Nieznana",
        detectedIndustries: [],
        industryConfidence: null,
        industryClassificationReason: "",
        industrySignals: [],
        industryClassificationDetails: {},
        detectedContentType: "Inna / Nieznana",
        detectedContentTypes: [],
        contentTypeConfidence: null,
        contentTypeScoreBreakdown: {},
        contentTypeReason: "",
        contentTypePagesSummary: {},
        pageContentResults: [],
        contentTypeSignals: [],
        isMixedContent: false,
        projectTitleDetected: "",
        investmentAddressDetected: "",
        plotNumberDetected: "",
        projectIdentityConfidence: null,
        projectAssignmentStatus: "unassigned",
        projectIdentitySignals: {},
        lineExtractionSummary: { pages: 0, totalLines: 0 },
      });
    }

    if (errors.length) {
      showMessage(errors.join(" "));
    } else {
      showMessage("Pliki dodane do kolejki.", "success");
    }
    render();
  }

  function applyIndustryResult(item, documentPayload) {
    item.status = documentPayload.processingStatus || item.status;
    item.detectedIndustry = documentPayload.detectedIndustry || "Nieznana";
    item.detectedIndustries = documentPayload.detectedIndustries || [];
    item.industryConfidence = documentPayload.industryConfidence;
    item.industryClassificationReason = documentPayload.industryClassificationReason || "";
    item.industrySignals = documentPayload.industrySignals || [];
    item.industryClassificationDetails = documentPayload.industryClassificationDetails || {};
    item.detectedContentType = documentPayload.detectedContentType || "Inna / Nieznana";
    item.detectedContentTypes = documentPayload.detectedContentTypes || [];
    item.contentTypeConfidence = documentPayload.contentTypeConfidence;
    item.contentTypeScoreBreakdown = documentPayload.contentTypeScoreBreakdown || {};
    item.contentTypeReason = documentPayload.contentTypeReason || "";
    item.contentTypePagesSummary = documentPayload.contentTypePagesSummary || {};
    item.pageContentResults = documentPayload.pageContentResults || [];
    item.contentTypeSignals = documentPayload.contentTypeSignals || [];
    item.isMixedContent = Boolean(documentPayload.isMixedContent);
    item.contentTypeDetectedBySystem = documentPayload.contentTypeDetectedBySystem || item.detectedContentType;
    item.contentTypeConfirmedByUser = documentPayload.contentTypeConfirmedByUser || null;
    item.contentTypeOverride = documentPayload.contentTypeOverride || null;
    item.contentTypeOverrideReason = documentPayload.contentTypeOverrideReason || null;
    item.projectTitleDetected = documentPayload.projectTitleDetected || "";
    item.projectTitleNormalized = documentPayload.projectTitleNormalized || "";
    item.projectTitleConfidence = documentPayload.projectTitleConfidence ?? null;
    item.projectTitleSource = documentPayload.projectTitleSource || "";
    item.investmentAddressDetected = documentPayload.investmentAddressDetected || "";
    item.investmentAddressNormalized = documentPayload.investmentAddressNormalized || "";
    item.investmentAddressConfidence = documentPayload.investmentAddressConfidence ?? null;
    item.investmentAddressSource = documentPayload.investmentAddressSource || "";
    item.plotNumberDetected = documentPayload.plotNumberDetected || "";
    item.plotNumberNormalized = documentPayload.plotNumberNormalized || "";
    item.landRegistryUnitDetected = documentPayload.landRegistryUnitDetected || "";
    item.projectIdentityConfidence = documentPayload.projectIdentityConfidence ?? null;
    item.projectIdentitySignals = documentPayload.projectIdentitySignals || {};
    item.projectMatchScore = documentPayload.projectMatchScore ?? null;
    item.projectMatchReason = documentPayload.projectMatchReason || "";
    item.projectAssignmentStatus = documentPayload.projectAssignmentStatus || "unassigned";
    item.assignedAtProjectId = documentPayload.assignedAtProjectId ?? null;
    item.projectIdentityOverrideJson = documentPayload.projectIdentityOverrideJson || {};
  }

  function summarizeLineExtraction(item) {
    const pages = Object.values(state.linesByPage[item.documentId] || {});
    item.lineExtractionSummary = {
      pages: pages.length,
      totalLines: pages.reduce((sum, page) => sum + (Number(page.lineCount) || 0), 0),
    };
  }

  function getSourceBadge(source) {
    if (source === "pdf_vector") {
      return { label: "Wektor PDF", className: "border-emerald-300 bg-emerald-50 text-emerald-700" };
    }
    if (source === "raster_detected") {
      return { label: "Fallback rastrowy", className: "border-amber-300 bg-amber-50 text-amber-700" };
    }
    return { label: "Brak danych", className: "border-zinc-300 bg-zinc-50 text-zinc-700" };
  }


  function formatAxisDirection(direction) {
    if (direction === "horizontal") return "pozioma";
    if (direction === "vertical") return "pionowa";
    return "ukośna";
  }

  function renderAxesList(item, pageNumber) {
    if (!atAxesList) return;
    const axes = (((state.axesByPage[item.documentId] || {})[pageNumber] || {}).axes) || [];
    const minConfidence = Number(atAxesMinConfidence?.value) || 0;
    const filtered = axes.filter((axis) => Number(axis.confidence) >= minConfidence);
    if (!filtered.length) {
      atAxesList.textContent = "Brak wykrytych osi (lub poniżej progu confidence).";
      return;
    }
    atAxesList.innerHTML = "";
    filtered.forEach((axis) => {
      const row = document.createElement("div");
      row.className = "mb-1 rounded border border-fuchsia-200 bg-white px-2 py-1";
      const confidence = Number.isFinite(Number(axis.confidence)) ? `${Math.round(Number(axis.confidence) * 100)}%` : "—";
      row.innerHTML = `<div><b>${axis.axisLabel || axis.systemAxisLabel || "—"}</b> · ${formatAxisDirection(axis.axisDirection)} · ${formatRealLength({ realLength: axis.realLength }, "mm")}</div>
      <div class="text-[10px] text-zinc-600">id=${axis.axisId} · conf=${confidence} · ${axis.detectionSource || "—"}</div>`;
      row.addEventListener("click", async () => {
        const newLabel = window.prompt("Nowa etykieta osi:", axis.axisLabel || axis.systemAxisLabel || "");
        if (newLabel === null) return;
        const status = window.prompt("Status osi (confirmed/rejected/uncertain):", axis.userStatus || "confirmed");
        const payload = { axisLabel: newLabel, isUserConfirmed: status === "rejected" ? 0 : 1, userStatus: status };
        const res = await fetch(`/api/at/documents/${item.documentId}/pages/${pageNumber}/axes/${axis.axisId}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
        });
        if (res.ok) {
          await loadAxesForPage(item, pageNumber, false, true);
        }
      });
      atAxesList.appendChild(row);
    });
  }

  async function loadAxesForPage(item, pageNumber, forceRetry = false, silent = false) {
    const docId = item.documentId;
    state.axesByPage[docId] = state.axesByPage[docId] || {};
    if (!forceRetry && state.axesByPage[docId][pageNumber]) return state.axesByPage[docId][pageNumber];
    const path = forceRetry ? `/api/at/documents/${docId}/pages/${pageNumber}/detect-axes/retry` : `/api/at/documents/${docId}/pages/${pageNumber}/detect-axes`;
    const response = await fetch(path, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Nie udało się wykryć osi.");
    state.axesByPage[docId][pageNumber] = payload;
    if (!silent) renderAxesList(item, pageNumber);
    return payload;
  }

  function drawLinesOverlay(page) {
    if (!atLinesSvgOverlay) return;
    const width = 900;
    const height = 580;
    atLinesSvgOverlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
    atLinesSvgOverlay.innerHTML = "";
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", "0");
    bg.setAttribute("y", "0");
    bg.setAttribute("width", String(width));
    bg.setAttribute("height", String(height));
    bg.setAttribute("fill", "#ffffff");
    atLinesSvgOverlay.appendChild(bg);

    if (!page) return;
    const pageW = Number(page.pageWidth) || 1;
    const pageH = Number(page.pageHeight) || 1;
    const scale = Math.min(width / pageW, height / pageH);
    const offsetX = (width - pageW * scale) / 2;
    const offsetY = (height - pageH * scale) / 2;

    const frame = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    frame.setAttribute("x", String(offsetX));
    frame.setAttribute("y", String(offsetY));
    frame.setAttribute("width", String(pageW * scale));
    frame.setAttribute("height", String(pageH * scale));
    frame.setAttribute("fill", "none");
    frame.setAttribute("stroke", "#e4e4e7");
    atLinesSvgOverlay.appendChild(frame);

    if (!atLinesToggle?.checked) return;
    const minLength = Number(atLinesMinLength?.value) || 0;
    const lines = (Array.isArray(page.lines) ? page.lines : []).filter((line) => Number(line.length) >= minLength);
    lines.forEach((line) => {
      const svgLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
      svgLine.setAttribute("x1", String(offsetX + Number(line.x1) * scale));
      svgLine.setAttribute("y1", String(offsetY + Number(line.y1) * scale));
      svgLine.setAttribute("x2", String(offsetX + Number(line.x2) * scale));
      svgLine.setAttribute("y2", String(offsetY + Number(line.y2) * scale));
      svgLine.setAttribute("stroke", "#0f766e");
      svgLine.setAttribute("stroke-width", String(Math.max(1, Number(line.strokeWidth) || 1.2)));
      svgLine.style.cursor = "pointer";
      svgLine.addEventListener("click", () => {
        const text = `PDF: ${(Number(line.length) || 0).toFixed(2)} • REAL: ${formatRealLength(line, page?.realWorldUnit || "mm")}`;
        if (atLineMeasurement) atLineMeasurement.textContent = text;
      });
      atLinesSvgOverlay.appendChild(svgLine);
    });

    const selectedDocId = state.selectedDocumentId;
    const pageNumber = Number(atLinesPageSelect?.value || 0);
    const axesPage = ((state.axesByPage[selectedDocId] || {})[pageNumber] || {});
    const minAxisConfidence = Number(atAxesMinConfidence?.value) || 0;
    if (atAxesToggle?.checked) {
      (axesPage.axes || []).filter((axis) => Number(axis.confidence) >= minAxisConfidence).forEach((axis) => {
        const axisLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        axisLine.setAttribute("x1", String(offsetX + Number(axis.x1) * scale));
        axisLine.setAttribute("y1", String(offsetY + Number(axis.y1) * scale));
        axisLine.setAttribute("x2", String(offsetX + Number(axis.x2) * scale));
        axisLine.setAttribute("y2", String(offsetY + Number(axis.y2) * scale));
        axisLine.setAttribute("stroke", "#c026d3");
        axisLine.setAttribute("stroke-width", "1.6");
        axisLine.setAttribute("stroke-dasharray", "7 5");
        atLinesSvgOverlay.appendChild(axisLine);
        if (atAxesLabelsToggle?.checked && (axis.axisLabel || axis.systemAxisLabel)) {
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.setAttribute("x", String(offsetX + Number(axis.x2) * scale + 4));
          label.setAttribute("y", String(offsetY + Number(axis.y2) * scale - 4));
          label.setAttribute("font-size", "11");
          label.setAttribute("fill", "#701a75");
          label.textContent = atAxesConfidenceToggle?.checked ? `${axis.axisLabel || axis.systemAxisLabel} (${Math.round((Number(axis.confidence) || 0) * 100)}%)` : `${axis.axisLabel || axis.systemAxisLabel}`;
          atLinesSvgOverlay.appendChild(label);
        }
      });
    }
  }

  function renderLineStats(page) {
    const stats = buildLineExtractionStats(page || {});
    const confidence = stats.confidence == null ? "—" : `${Math.round(stats.confidence * 100)}%`;
    atLinesMeta.textContent = `Źródło: ${stats.source} • Linie: ${stats.lineCount} • Confidence: ${confidence} • Status: ${page?.extractionStatus || "—"}`;
    if (atLinesSourceBadge) {
      const badge = getSourceBadge(stats.source);
      atLinesSourceBadge.textContent = badge.label;
      atLinesSourceBadge.className = `inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${badge.className}`;
    }
    const debug = [
      buildScaleSummary(page || {}),
      `lineCount=${stats.lineCount}`,
      `source=${stats.source}`,
      `averageLength=${stats.averageLength.toFixed(2)}`,
      `horizontal=${stats.horizontal}`,
      `vertical=${stats.vertical}`,
      `diagonal=${stats.diagonal}`,
      `fallbackUsed=${page?.diagnostics?.fallbackUsed ? "tak" : "nie"}`,
      `fallbackReason=${page?.diagnostics?.fallbackReason || "—"}`,
      `nativeVectorAvailable=${page?.diagnostics?.nativeVectorAvailable ? "tak" : "nie"}`,
      `nativeVectorUsed=${page?.diagnostics?.nativeVectorUsed ? "tak" : "nie"}`,
      `vectorObjectCount=${page?.diagnostics?.vectorObjectCount ?? 0}`,
      `vectorExtractionReason=${page?.diagnostics?.vectorExtractionReason || "—"}`,
      `rejectedShort=${page?.diagnostics?.rejected?.rejectedShort ?? 0}`,
      `rejectedDuplicate=${page?.diagnostics?.rejected?.rejectedDuplicate ?? 0}`,
    ].join("\n");
    atLinesStats.textContent = debug;
    atLinesStats.classList.toggle("hidden", !atLinesStatsToggle?.checked);
    if (atScaleBadge) atScaleBadge.textContent = page?.detectedScaleNormalized || "—";
    if (atScaleSource) atScaleSource.textContent = SCALE_SOURCE_LABELS[page?.scaleSource] || "—";
    if (atScaleStatus) atScaleStatus.textContent = normalizeScaleStatus(page);
    if (atScaleConfidence) {
      atScaleConfidence.textContent = Number.isFinite(Number(page?.scaleConfidence))
        ? `${Math.round(Number(page.scaleConfidence) * 100)}%`
        : "—";
    }
    if (atScaleDiagnostics) {
      atScaleDiagnostics.textContent = [
        `Kandydaci skali: ${(page?.scaleCandidates || []).map((c) => `${c.normalized}(${Math.round((Number(c.confidence) || 0) * 100)}%)`).join(", ") || "—"}`,
        `Kandydaci wymiarów: ${(page?.dimensionCandidates || []).slice(0, 8).map((d) => `${d.raw}=${formatDimensionCandidate(d)}`).join(", ") || "—"}`,
        `Konflikt: ${page?.scaleConflictDetected ? "tak" : "nie"} ${page?.scaleConflictReason || ""}`.trim(),
        `Faktor: ${page?.pdfUnitToRealFactor ?? "—"} mm/pdf`,
      ].join("\n");
    }
  }

  async function loadLinesForPage(item, pageNumber, forceRetry = false) {
    const docId = item.documentId;
    state.linesByPage[docId] = state.linesByPage[docId] || {};
    const cache = state.linesByPage[docId][pageNumber];
    if (cache && !forceRetry) return cache;

    if (forceRetry) {
      const retryResponse = await fetch(`/api/at/documents/${docId}/pages/${pageNumber}/extract-lines/retry`, { method: "POST" });
      const retryPayload = await retryResponse.json();
      if (!retryResponse.ok) throw new Error(retryPayload.error || "Nie udało się ponowić ekstrakcji linii.");
      state.linesByPage[docId][pageNumber] = retryPayload.page;
      summarizeLineExtraction(item);
      return retryPayload.page;
    }

    const response = await fetch(`/api/at/documents/${docId}/pages/${pageNumber}/lines`);
    if (response.ok) {
      const payload = await response.json();
      state.linesByPage[docId][pageNumber] = payload.page;
      summarizeLineExtraction(item);
      return payload.page;
    }

    const extractResponse = await fetch(`/api/at/documents/${docId}/extract-lines`, { method: "POST" });
    const extractPayload = await extractResponse.json();
    if (!extractResponse.ok) throw new Error(extractPayload.error || "Nie udało się uruchomić ekstrakcji linii.");
    (extractPayload.pages || []).forEach((page) => {
      state.linesByPage[docId][page.pageNumber] = page;
    });
    summarizeLineExtraction(item);
    return state.linesByPage[docId][pageNumber] || null;
  }

  async function openLinesViewer(item) {
    atLinesViewer?.classList.remove("hidden");
    state.selectedDocumentId = item.documentId;
    const planPages = (item.pageContentResults || []).filter((entry) => normalizeContentType(entry.detectedContentType) === "Rzut" || entry.contentTypeOverride === "Rzut");
    if (!planPages.length) {
      atLinesMeta.textContent = "Brak stron sklasyfikowanych jako Rzut.";
      atLinesStats.textContent = "empty_state";
      drawLinesOverlay(null);
      return;
    }
    atLinesPageSelect.innerHTML = planPages.map((entry) => `<option value="${entry.pageNumber}">Strona ${entry.pageNumber}</option>`).join("");
    const activePage = Number(atLinesPageSelect.value) || planPages[0].pageNumber;
    atStatusBoard.textContent = `Ładowanie linii dla dokumentu ${item.file.name}, strona ${activePage}...`;
    try {
      const page = await loadLinesForPage(item, activePage);
      if (!page) throw new Error("Brak danych ekstrakcji linii dla wybranej strony.");
      renderLineStats(page);
      try { await loadAxesForPage(item, activePage, false, true); } catch (_err) { /* noop */ }
      renderAxesList(item, activePage);
      drawLinesOverlay(page);
      atStatusBoard.textContent = `Załadowano linie: ${page.lineCount} (źródło: ${page.extractionSource}).`;
      render();
    } catch (error) {
      atLinesMeta.textContent = error.message || "Nie udało się wczytać linii.";
      atLinesStats.textContent = "error_state";
      drawLinesOverlay(null);
    }
  }

  async function retryClassification(item) {
    try {
      item.status = "CLASSIFYING_INDUSTRY";
      render();
      const response = await fetch(`/api/at/documents/${item.documentId}/classify-industry/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić klasyfikacji branży.");
      applyIndustryResult(item, payload.document || {});
      atStatusBoard.textContent = `Ponownie sklasyfikowano ${item.file.name}: ${getIndustryLabel(item)}.`;
      render();
    } catch (error) {
      item.status = "INDUSTRY_CLASSIFICATION_FAILED";
      showMessage(error.message || "Błąd podczas klasyfikacji branży.");
      render();
    }
  }


  async function overridePageContentType(item, pageNumber, contentTypeOverride, contentTypeOverrideReason) {
    const response = await fetch(`/api/at/documents/${item.documentId}/pages/${pageNumber}/content-type-override`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contentTypeOverride, contentTypeOverrideReason }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Nie udało się zapisać korekty strony.");
    }

    const payload = await response.json();
    applyIndustryResult(item, payload.document || {});
    render();
  }

  async function retryContentTypeClassification(item) {
    try {
      item.status = "CLASSIFYING_CONTENT_TYPE";
      render();
      const response = await fetch(`/api/at/documents/${item.documentId}/classify-content-type/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić klasyfikacji typu zawartości.");
      applyIndustryResult(item, payload.document || {});
      atStatusBoard.textContent = `Ponownie sklasyfikowano typy stron ${item.file.name}: ${normalizeContentType(item.detectedContentType)}.`;
      render();
    } catch (error) {
      item.status = "ERROR";
      showMessage(error.message || "Błąd podczas klasyfikacji typu zawartości.");
      render();
    }
  }

  async function retryProjectMatching(item) {
    item.status = "matching_pending";
    render();
    const response = await fetch(`/api/at/documents/${item.documentId}/match-project/retry`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      item.status = "ERROR";
      item.error = payload.error || "Nie udało się ponowić matchingu projektu.";
      render();
      return;
    }
    applyIndustryResult(item, payload.document || {});
    atStatusBoard.textContent = `Zakończono matching projektu dla ${item.file.name}.`;
    render();
  }

  async function overrideProjectIdentity(item, data) {
    const response = await fetch(`/api/at/documents/${item.documentId}/project-identity-override`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      showMessage(payload.error || "Nie udało się zapisać ręcznej korekty projektu.");
      return;
    }
    applyIndustryResult(item, payload.document || {});
    atStatusBoard.textContent = `Zapisano ręczną korektę projektu dla ${item.file.name}.`;
    render();
  }

  async function retryProcessing(item) {
    try {
      const response = await fetch(`/api/at/documents/${item.documentId}/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić przetwarzania.");
      applyIndustryResult(item, payload.document || {});
      atStatusBoard.textContent = `Ponowiono analizę dla ${item.file.name}: ${statusLabels[item.status] || item.status}.`;
      render();
    } catch (error) {
      showMessage(error.message || "Błąd podczas ponawiania przetwarzania.");
    }
  }

  async function uploadAndProcessQueue() {
    if (!state.queue.length || state.uploading) return;
    state.uploading = true;
    atStatusBoard.textContent = "Wysyłanie dokumentów...";
    showMessage("");

    for (const item of state.queue) {
      if (item.documentId) continue;
      item.status = "UPLOADING";
      item.progress = 15;
      render();

      const formData = new FormData();
      formData.append("file", item.file);

      try {
        const response = await fetch("/api/at/documents", { method: "POST", body: formData });
        const payload = await response.json();
        if (!response.ok && response.status !== 207) {
          throw new Error(payload.error || payload.errors?.[0]?.error || "Nie udało się przesłać pliku.");
        }
        const uploaded = payload.documents?.[0];
        if (!uploaded) {
          throw new Error(payload.errors?.[0]?.error || "Upload zakończył się bez dokumentu.");
        }
        item.documentId = uploaded.id;
        item.progress = 70;
        item.status = "UPLOADED";

        const processResponse = await fetch(`/api/at/documents/${item.documentId}/process`, { method: "POST" });
        const processPayload = await processResponse.json();
        if (!processResponse.ok) {
          throw new Error(processPayload.error || "Nie udało się uruchomić przetwarzania.");
        }
        item.progress = 100;
        applyIndustryResult(item, processPayload.document || {});
        atStatusBoard.textContent = `Przetworzono ${item.file.name}. Branża: ${getIndustryLabel(item)}.`;
      } catch (error) {
        item.status = "ERROR";
        item.error = error.message || "Błąd uploadu.";
        atStatusBoard.textContent = `Błąd dla ${item.file.name}.`;
      }
      render();
    }

    state.uploading = false;
    atStatusBoard.textContent = "Zakończono przetwarzanie kolejki AT.";
  }

  async function closeAtWindow() {
    if (state.uploading) {
      showMessage("Poczekaj na zakończenie bieżącego uploadu przed zamknięciem okna.");
      return;
    }

    atCloseWindowBtn?.setAttribute("disabled", "disabled");
    try {
      const response = await fetch("/api/at/window/close", { method: "POST", credentials: "include" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error || "Nie udało się zamknąć okna AT.");
      }
      state.queue = [];
      showMessage("");
      render();
      document.dispatchEvent(new CustomEvent("at:window:closed", { detail: payload }));
    } catch (error) {
      showMessage(error?.message || "Wystąpił błąd podczas zamykania okna AT.");
    } finally {
      atCloseWindowBtn?.removeAttribute("disabled");
    }
  }

  atChooseFilesBtn?.addEventListener("click", () => atFileInput?.click());
  atFileInput?.addEventListener("change", (event) => {
    enqueueFiles(event.target.files);
    atFileInput.value = "";
  });

  atClearQueueBtn?.addEventListener("click", () => {
    state.queue = [];
    showMessage("Lista plików została wyczyszczona.", "success");
    render();
  });

  atStartProcessingBtn?.addEventListener("click", uploadAndProcessQueue);
  atCloseWindowBtn?.addEventListener("click", closeAtWindow);

  atDropzone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    atDropzone.classList.add("is-dragover");
  });
  atDropzone?.addEventListener("dragleave", () => atDropzone.classList.remove("is-dragover"));
  atDropzone?.addEventListener("drop", (event) => {
    event.preventDefault();
    atDropzone.classList.remove("is-dragover");
    enqueueFiles(event.dataTransfer?.files);
  });
  atDropzone?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      atFileInput?.click();
    }
  });

  atLinesPageSelect?.addEventListener("change", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const page = await loadLinesForPage(item, Number(atLinesPageSelect.value));
    renderLineStats(page);
    drawLinesOverlay(page);
  });
  atLinesRefreshBtn?.addEventListener("click", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const pageNo = Number(atLinesPageSelect.value);
    const page = await loadLinesForPage(item, pageNo, true);
    renderLineStats(page);
    drawLinesOverlay(page);
    render();
  });
  atLinesToggle?.addEventListener("change", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const page = await loadLinesForPage(item, Number(atLinesPageSelect.value));
    drawLinesOverlay(page);
  });
  atLinesMinLength?.addEventListener("input", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const page = await loadLinesForPage(item, Number(atLinesPageSelect.value));
    drawLinesOverlay(page);
  });
  atLinesStatsToggle?.addEventListener("change", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const page = await loadLinesForPage(item, Number(atLinesPageSelect.value));
    renderLineStats(page);
  });
  atScaleDetectBtn?.addEventListener("click", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const pageNo = Number(atLinesPageSelect.value);
    const response = await fetch(`/api/at/documents/${docId}/pages/${pageNo}/detect-scale`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return showMessage(payload.error || "Nie udało się wykryć skali.");
    state.linesByPage[docId][pageNo] = payload.page;
    renderLineStats(payload.page);
    drawLinesOverlay(payload.page);
    render();
  });
  atScaleRetryBtn?.addEventListener("click", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const pageNo = Number(atLinesPageSelect.value);
    const response = await fetch(`/api/at/documents/${docId}/pages/${pageNo}/detect-scale/retry`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return showMessage(payload.error || "Nie udało się ponowić wykrywania skali.");
    state.linesByPage[docId][pageNo] = payload.page;
    renderLineStats(payload.page);
    drawLinesOverlay(payload.page);
    render();
  });
  atScaleOverrideBtn?.addEventListener("click", async () => {
    const docId = state.selectedDocumentId;
    const item = state.queue.find((entry) => entry.documentId === docId);
    if (!item) return;
    const pageNo = Number(atLinesPageSelect.value);
    const ratio = Number(window.prompt("Podaj skalę jako n dla 1:n", "100"));
    if (!Number.isInteger(ratio) || ratio <= 0) return;
    const reason = window.prompt("Powód ręcznej korekty:", "manual review");
    const response = await fetch(`/api/at/documents/${docId}/pages/${pageNo}/scale-override`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ratio, reason }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return showMessage(payload.error || "Nie udało się zapisać ręcznej skali.");
    state.linesByPage[docId][pageNo] = payload.page;
    renderLineStats(payload.page);
    drawLinesOverlay(payload.page);
    render();
  });

  render();
}
