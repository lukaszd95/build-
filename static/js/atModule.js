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

const OVERRIDE_OPTIONS = ["Architektura", "PZT", "Konstrukcja", "Elektryka", "Wod-kan", "Wentylacja", "Wiele branż", "Nieznana"];

function normalizeIndustryName(industry) {
  return industry || "Nieznana";
}
function getIndustryBadgeClass(industry) { return INDUSTRY_BADGE_STYLES[normalizeIndustryName(industry)] || INDUSTRY_BADGE_STYLES["Nieznana"]; }
function getIndustryLabel(item) {
  if (item.processingStatus === "CLASSIFYING_INDUSTRY") return "W trakcie rozpoznawania";
  if (item.processingStatus === "INDUSTRY_CLASSIFICATION_FAILED") return "Błąd klasyfikacji";
  return normalizeIndustryName(item.industryOverride || item.detectedIndustry);
}
function buildIndustryDetailsText(item) {
  const industries = Array.isArray(item.detectedIndustries) && item.detectedIndustries.length ? item.detectedIndustries.join(", ") : "—";
  const confidence = Number.isFinite(Number(item.industryConfidence)) ? `${Math.round(Number(item.industryConfidence) * 100)}%` : "—";
  const reason = item.industryClassificationReason || "Brak uzasadnienia klasyfikacji.";
  const pageResults = Array.isArray(item.pageAnalyses) ? item.pageAnalyses : [];
  const pageInfo = pageResults.length ? pageResults.map((entry) => `s.${entry.pageNumber}:${entry.detectedIndustry} (${Math.round((Number(entry.industryConfidence) || 0) * 100)}%)`).join("; ") : "—";
  const pagesSummary = Array.isArray(item.industryPagesSummary) && item.industryPagesSummary.length
    ? item.industryPagesSummary.map((entry) => `${entry.industry}:${entry.pages}`).join(", ")
    : "—";
  return [
    `Branża główna: ${getIndustryLabel(item)}`,
    `Wykryte branże: ${industries}`,
    `Pewność: ${confidence}`,
    `Sygnały: ${(item.industrySignals || []).length}`,
    `Strony / branże: ${pagesSummary}`,
    `Per strona: ${pageInfo}`,
    `System: ${item.industryDetectedBySystem || "—"}`,
    `Potwierdzenie użytkownika: ${item.industryConfirmedByUser || "—"}`,
    `Nadpisanie: ${item.industryOverride || "—"}`,
    `Uzasadnienie: ${reason}`,
  ].join("\n");
}

if (typeof window !== "undefined") window.__AT_INDUSTRY_UI__ = { getIndustryBadgeClass, getIndustryLabel, buildIndustryDetailsText };

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
  const state = { queue: [], uploading: false };
  const statusLabels = { READY: "gotowy do wysłania", UPLOADING: "wysyłanie", UPLOADED: "przesłano", CLASSIFYING_INDUSTRY: "rozpoznawanie branży", INDUSTRY_CLASSIFIED: "branża rozpoznana", INDUSTRY_CLASSIFICATION_FAILED: "błąd klasyfikacji branży", ERROR: "błąd" };

  const showMessage = (message, variant = "error") => {
    if (!message) { atValidationMessage.className = "mb-2 hidden rounded-lg border px-3 py-2 text-xs"; atValidationMessage.textContent = ""; return; }
    atValidationMessage.className = variant === "success" ? "mb-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-700" : "mb-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700";
    atValidationMessage.textContent = message;
  };
  const formatBytes = (bytes) => Number.isFinite(bytes) ? `${(bytes / 1024 / 1024).toFixed(bytes > 1024 * 1024 ? 1 : 2)} MB` : "—";
  const removeQueuedFile = (localId) => { state.queue = state.queue.filter((item) => item.localId !== localId); render(); };
  const applyIndustryResult = (item, payload) => {
    Object.assign(item, {
      status: payload.processingStatus || item.status,
      detectedIndustry: payload.detectedIndustry || item.detectedIndustry || "Nieznana",
      detectedIndustries: payload.detectedIndustries || [],
      industryConfidence: payload.industryConfidence,
      industryClassificationReason: payload.industryClassificationReason || "",
      industrySignals: payload.industrySignals || [],
      industryScoreBreakdown: payload.industryScoreBreakdown || {},
      industryPagesSummary: payload.industryPagesSummary || [],
      industryDetectedBySystem: payload.industryDetectedBySystem || payload.detectedIndustry || item.industryDetectedBySystem || null,
      industryConfirmedByUser: payload.industryConfirmedByUser || null,
      industryOverride: payload.industryOverride || null,
      industryOverrideReason: payload.industryOverrideReason || "",
      pageAnalyses: payload.pageAnalyses || [],
      industryClassificationDetails: payload.industryClassificationDetails || {},
    });
  };

  async function saveIndustryOverride(item, payload) {
    const response = await fetch(`/api/at/documents/${item.documentId}/industry-override`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Nie udało się zapisać korekty.");
    applyIndustryResult(item, result.document || {});
  }
  async function retryClassification(item) {
    item.status = "CLASSIFYING_INDUSTRY"; render();
    const response = await fetch(`/api/at/documents/${item.documentId}/classify-industry/retry`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić klasyfikacji branży.");
    applyIndustryResult(item, payload.document || {});
  }
  async function retryProcessing(item) {
    const response = await fetch(`/api/at/documents/${item.documentId}/retry`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić przetwarzania.");
    applyIndustryResult(item, payload.document || {});
  }

  function render() {
    atFileList.innerHTML = "";
    atEmptyState.classList.toggle("hidden", state.queue.length > 0);
    atStartProcessingBtn.disabled = state.queue.length === 0 || state.uploading;
    state.queue.forEach((item) => {
      const row = document.createElement("div");
      const confidence = Number.isFinite(Number(item.industryConfidence)) ? `${Math.round(Number(item.industryConfidence) * 100)}%` : "—";
      row.className = "at-file-row";
      row.innerHTML = `<div><div class="flex items-center gap-2 flex-wrap"><div class="truncate text-sm font-semibold text-zinc-900">${item.file.name}</div><span class="at-status-badge">${statusLabels[item.status] || item.status}</span><span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${getIndustryBadgeClass(getIndustryLabel(item))}">${getIndustryLabel(item)}</span></div><div class="at-file-meta"><span>Rozmiar: ${formatBytes(item.file.size)}</span><span>Pewność: ${confidence}</span><span>Potwierdzona: ${item.industryConfirmedByUser || "nie"}</span></div>${item.industryClassificationReason ? `<div class="mt-1 text-xs text-zinc-600">${item.industryClassificationReason}</div>` : ""}<div class="mt-1 text-[11px] text-zinc-600">${(item.industryPagesSummary || []).map((entry) => `${entry.industry}: ${entry.pages} str.`).join(" · ") || "Brak podsumowania stron"}</div><div class="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"><select data-role="industry-select" class="rounded-lg border border-zinc-300 bg-white px-2 py-1 text-xs"><option value="">— wybierz branżę —</option>${OVERRIDE_OPTIONS.map((option) => `<option value="${option}" ${option === (item.industryOverride || item.industryConfirmedByUser) ? "selected" : ""}>${option}</option>`).join("")}</select><input data-role="industry-reason" type="text" value="${item.industryOverrideReason || ""}" placeholder="Powód korekty" class="rounded-lg border border-zinc-300 bg-white px-2 py-1 text-xs" /></div>${item.error ? `<div class="mt-1 text-xs text-rose-600">${item.error}</div>` : ""}</div><div class="flex items-center gap-1 flex-wrap"><button type="button" class="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-gray-50" data-action="details">Szczegóły</button><button type="button" class="rounded-full border border-zinc-300 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-zinc-100" data-action="retry-classification">Klasyfikuj ponownie</button><button type="button" class="rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-100" data-action="confirm">Akceptuj</button><button type="button" class="rounded-full border border-violet-300 bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700 hover:bg-violet-100" data-action="override">Zmień</button><button type="button" class="rounded-full border border-fuchsia-300 bg-fuchsia-50 px-3 py-1 text-xs font-semibold text-fuchsia-700 hover:bg-fuchsia-100" data-action="set-multi">Wiele branż</button><button type="button" class="rounded-full border border-rose-300 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100" data-action="remove">Usuń</button></div>`;
      row.querySelector('[data-action="remove"]').addEventListener("click", () => removeQueuedFile(item.localId));
      row.querySelector('[data-action="details"]').addEventListener("click", () => showMessage(buildIndustryDetailsText(item), "success"));
      row.querySelector('[data-action="retry-classification"]').addEventListener("click", async () => { try { await retryClassification(item); render(); } catch (error) { item.status = "INDUSTRY_CLASSIFICATION_FAILED"; showMessage(error.message || "Błąd klasyfikacji."); render(); } });
      row.querySelector('[data-action="confirm"]').addEventListener("click", async () => { try { await saveIndustryOverride(item, { industryConfirmedByUser: item.industryOverride || item.detectedIndustry || "Nieznana", industryOverride: item.industryOverride || null, industryOverrideReason: item.industryOverrideReason || null }); showMessage("Zapisano potwierdzenie.", "success"); render(); } catch (error) { showMessage(error.message || "Błąd zapisu."); } });
      row.querySelector('[data-action="override"]').addEventListener("click", async () => {
        const selected = row.querySelector('[data-role="industry-select"]')?.value;
        const reason = row.querySelector('[data-role="industry-reason"]')?.value?.trim();
        try { await saveIndustryOverride(item, { industryConfirmedByUser: selected || null, industryOverride: selected || null, industryOverrideReason: reason || null }); showMessage("Zapisano korektę.", "success"); render(); } catch (error) { showMessage(error.message || "Błąd zapisu."); }
      });
      row.querySelector('[data-action="set-multi"]').addEventListener("click", async () => { try { await saveIndustryOverride(item, { industryConfirmedByUser: "Wiele branż", industryOverride: "Wiele branż", industryOverrideReason: "Ręczne ustawienie wielu branż" }); showMessage("Ustawiono wiele branż.", "success"); render(); } catch (error) { showMessage(error.message || "Błąd zapisu."); } });
      atFileList.appendChild(row);
    });
  }

  function enqueueFiles(files) {
    const incoming = Array.from(files || []);
    if (state.queue.length + incoming.length > maxFiles) return showMessage(`Limit plików został przekroczony. Maksymalnie ${maxFiles}.`);
    incoming.forEach((file) => {
      if (!file?.name?.toLowerCase?.().endsWith(".pdf")) return;
      state.queue.push({ localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`, file, status: "READY", progress: 0, addedAt: new Date().toISOString(), documentId: null, error: null, detectedIndustry: "Nieznana", detectedIndustries: [], industryConfidence: null, industryClassificationReason: "", industrySignals: [], industryScoreBreakdown: {}, industryPagesSummary: [], industryDetectedBySystem: null, industryConfirmedByUser: null, industryOverride: null, industryOverrideReason: "", industryClassificationDetails: {}, pageAnalyses: [] });
    });
    render();
  }
  async function uploadAndProcessQueue() {
    if (!state.queue.length || state.uploading) return;
    state.uploading = true;
    for (const item of state.queue) {
      if (item.documentId) continue;
      try {
        const formData = new FormData(); formData.append("file", item.file);
        const uploaded = await (await fetch("/api/at/documents", { method: "POST", body: formData })).json();
        item.documentId = uploaded.documents?.[0]?.id;
        if (!item.documentId) throw new Error(uploaded.error || uploaded.errors?.[0]?.error || "Upload failed");
        const processResponse = await fetch(`/api/at/documents/${item.documentId}/process`, { method: "POST" });
        const processPayload = await processResponse.json();
        if (!processResponse.ok) throw new Error(processPayload.error || "Nie udało się uruchomić przetwarzania.");
        applyIndustryResult(item, processPayload.document || {});
      } catch (error) { item.status = "ERROR"; item.error = error.message || "Błąd uploadu."; }
      render();
    }
    state.uploading = false;
  }

  atChooseFilesBtn?.addEventListener("click", () => atFileInput?.click());
  atFileInput?.addEventListener("change", (event) => { enqueueFiles(event.target.files); atFileInput.value = ""; });
  atClearQueueBtn?.addEventListener("click", () => { state.queue = []; render(); showMessage("Lista plików została wyczyszczona.", "success"); });
  atStartProcessingBtn?.addEventListener("click", uploadAndProcessQueue);
  atCloseWindowBtn?.addEventListener("click", async () => { await fetch("/api/at/window/close", { method: "POST", credentials: "include" }); state.queue = []; render(); });
  atDropzone?.addEventListener("dragover", (event) => { event.preventDefault(); atDropzone.classList.add("is-dragover"); });
  atDropzone?.addEventListener("dragleave", () => atDropzone.classList.remove("is-dragover"));
  atDropzone?.addEventListener("drop", (event) => { event.preventDefault(); atDropzone.classList.remove("is-dragover"); enqueueFiles(event.dataTransfer?.files); });
  render();
}
