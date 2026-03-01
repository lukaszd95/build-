import { createIdentificationAutosave, normalizeIdentificationValue } from "./projectIdentificationAutosave.js";

const menuPreviewShell = document.getElementById("menuPreviewShell");
const openMenuPreviewBtn = document.getElementById("openMenuPreviewBtn");
const closeMenuPreviewBtn = document.getElementById("closeMenuPreviewBtn");
const menuTabs = document.querySelectorAll("[data-menu-tab]");
const menuPanels = document.querySelectorAll("[data-menu-panel]");
const parcelTabs = document.querySelectorAll("[data-parcel-tab]");
const parcelPanels = document.querySelectorAll("[data-parcel-panel]");
const planAddBtn = document.getElementById("planAddBtn");
const planUploadCard = document.getElementById("planUploadCard");
const planFileInput = document.getElementById("planFileInput");
const planHelpToggle = document.querySelector(".plan-upload-help-header");
const planUploadList = document.getElementById("planUploadList");
const planUploadEmpty = document.getElementById("planUploadEmpty");
const planDeleteModal = document.getElementById("planDeleteModal");
const planDeleteName = document.getElementById("planDeleteName");
const planDeleteCancel = document.getElementById("planDeleteCancel");
const planDeleteConfirm = document.getElementById("planDeleteConfirm");


const projectIdentificationInputs = document.querySelectorAll("[data-project-identification-field]");
const projectIdentificationStatusNodes = document.querySelectorAll("[data-project-identification-status]");
const projectIdentificationRetryButtons = document.querySelectorAll("[data-project-identification-retry]");
let projectIdentificationApiId = null;
let isApplyingProjectIdentification = false;
const PROJECT_IDENTIFICATION_FIELDS = ["plot_number", "cadastral_district", "street", "city"];
let hideSavedStateTimerId = null;
let hideLandUseSavedStateTimerId = null;

const projectLandUseInputs = document.querySelectorAll("[data-project-land-use-field]");
const projectLandUseStatusNodes = document.querySelectorAll("[data-project-land-use-status]");
const projectLandUseRetryButtons = document.querySelectorAll("[data-project-land-use-retry]");
const PROJECT_LAND_USE_FIELDS = [
  "land_use_primary",
  "land_use_allowed",
  "land_use_forbidden",
  "services_allowed",
  "nuisance_services_forbidden",
];

const projectLandRegisterAreaInputs = document.querySelectorAll("[data-project-land-register-area]");
const projectLandRegisterListNodes = document.querySelectorAll("[data-project-land-register-list]");
const projectLandRegisterAddButtons = document.querySelectorAll("[data-project-land-register-add]");
const projectLandRegisterStatusNodes = document.querySelectorAll("[data-project-land-register-status]");
const projectLandRegisterRetryButtons = document.querySelectorAll("[data-project-land-register-retry]");

const LAND_REGISTER_SYMBOL_MAX_LENGTH = 64;
let hideLandRegisterSavedStateTimerId = null;
let isApplyingLandRegister = false;
let landRegisterDebounceTimerId = null;
let landRegisterInFlight = false;
let landRegisterQueued = false;
let landRegisterPersisted = { parcel_area_total: null, land_uses: [] };
let landRegisterDraft = { parcel_area_total: "", land_uses: [] };
let landRegisterHasFailed = false;

function syncProjectIdentificationFieldInputs(sourceInput) {
  if (!sourceInput) return;
  const field = sourceInput.dataset.projectIdentificationField;
  if (!field) return;

  const nextValue = sourceInput.value;
  projectIdentificationInputs.forEach((input) => {
    if (input === sourceInput) return;
    if (input.dataset.projectIdentificationField !== field) return;
    if (input.value !== nextValue) {
      input.value = nextValue;
    }
  });
}

function normalizeLandUseFieldValue(field, value) {
  if (field === "services_allowed" || field === "nuisance_services_forbidden") {
    if (value === true) return "true";
    if (value === false) return "false";
    return "";
  }
  return normalizeIdentificationValue(value);
}

function parseLandUsePayloadValue(field, value) {
  if (field === "services_allowed" || field === "nuisance_services_forbidden") {
    if (value === "true") return true;
    if (value === "false") return false;
    return null;
  }
  const normalized = normalizeIdentificationValue(value);
  return normalized || null;
}

function syncProjectLandUseFieldInputs(sourceInput) {
  if (!sourceInput) return;
  const field = sourceInput.dataset.projectLandUseField;
  if (!field) return;

  const nextValue = sourceInput.value;
  projectLandUseInputs.forEach((input) => {
    if (input === sourceInput) return;
    if (input.dataset.projectLandUseField !== field) return;
    if (input.value !== nextValue) {
      input.value = nextValue;
    }
  });
}

function applyProjectLandUseToDom(data = {}) {
  isApplyingProjectIdentification = true;
  try {
    const normalized = Object.fromEntries(PROJECT_LAND_USE_FIELDS.map((key) => [key, normalizeLandUseFieldValue(key, data?.[key])]));

    projectLandUseInputs.forEach((input) => {
      const field = input.dataset.projectLandUseField;
      if (!field) return;
      const value = normalized[field] ?? "";
      if (input.value !== value) {
        input.value = value;
      }
    });
  } finally {
    isApplyingProjectIdentification = false;
  }
}

function setProjectLandUseStatus(status, message = "") {
  projectLandUseStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectLandUseRetryButtons.forEach((button) => {
    button.classList.toggle("hidden", status !== "error");
  });

  globalThis.clearTimeout(hideLandUseSavedStateTimerId);
  if (status === "saved") {
    hideLandUseSavedStateTimerId = globalThis.setTimeout(() => {
      setProjectLandUseStatus("idle", "");
    }, 1200);
  }
}


function normalizeLandRegisterArea(value) {
  if (value === null || value === undefined || value === "") return "";
  const asNumber = Number(value);
  if (!Number.isFinite(asNumber) || asNumber < 0) return "";
  return asNumber.toFixed(2).replace(/\.00$/, "");
}

function normalizeLandUses(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => ({
      symbol: normalizeIdentificationValue(item?.symbol || item?.category_symbol),
      area: normalizeLandRegisterArea(item?.area),
    }))
    .filter((item) => item.symbol || item.area);
}

function renderLandRegisterRows() {
  const rows = landRegisterDraft.land_uses.length ? landRegisterDraft.land_uses : [{ symbol: "", area: "" }];
  const rowsHtml = rows
    .map(
      (row, index) => `<div class="group inline-flex items-center justify-between gap-2 rounded-full bg-white/70 px-2.5 py-1.5 ring-1 ring-black/5 shadow-[0_1px_0_rgba(255,255,255,0.75)_inset]" data-land-use-row="${index}">
          <input value="${row.symbol}" data-land-use-symbol="${index}" maxlength="${LAND_REGISTER_SYMBOL_MAX_LENGTH}" class="w-[68px] bg-transparent text-right text-[13px] font-semibold tracking-[-0.01em] text-zinc-800 outline-none" aria-label="Rodzaj użytku" />
          <input value="${row.area}" data-land-use-area="${index}" class="w-[56px] bg-transparent text-right text-[13px] font-semibold tracking-[-0.01em] text-zinc-800 outline-none" aria-label="Powierzchnia użytku" />
          <span class="rounded-full bg-zinc-900/5 px-2 py-1 text-[11px] font-semibold text-zinc-700">m²</span>
          <button type="button" data-land-use-remove="${index}" class="rounded-full border border-zinc-200 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 hover:bg-zinc-50">Usuń</button>
        </div>`
    )
    .join("");
  projectLandRegisterListNodes.forEach((node) => {
    node.innerHTML = rowsHtml;
  });
}

function setProjectLandRegisterStatus(status, message = "") {
  projectLandRegisterStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectLandRegisterRetryButtons.forEach((button) => button.classList.toggle("hidden", status !== "error"));

  globalThis.clearTimeout(hideLandRegisterSavedStateTimerId);
  if (status === "saved") {
    hideLandRegisterSavedStateTimerId = globalThis.setTimeout(() => setProjectLandRegisterStatus("idle", ""), 1200);
  }
}

function syncLandRegisterAreaInputs(source) {
  const next = source.value;
  projectLandRegisterAreaInputs.forEach((input) => {
    if (input !== source && input.value !== next) input.value = next;
  });
}

function computeLandRegisterPayload() {
  const areaValue = normalizeIdentificationValue(landRegisterDraft.parcel_area_total);
  const area = areaValue === "" ? null : Number(areaValue.replace(",", "."));
  if (area !== null && (!Number.isFinite(area) || area < 0)) return null;

  const landUses = landRegisterDraft.land_uses
    .map((item) => ({
      symbol: normalizeIdentificationValue(item.symbol),
      area: Number(normalizeIdentificationValue(item.area).replace(",", ".")),
    }))
    .filter((item) => item.symbol || Number.isFinite(item.area));

  for (const item of landUses) {
    if (!item.symbol || item.symbol.length > LAND_REGISTER_SYMBOL_MAX_LENGTH || !Number.isFinite(item.area) || item.area < 0) {
      return null;
    }
  }

  const persistedArea = landRegisterPersisted.parcel_area_total;
  const persistedLandUses = JSON.stringify(landRegisterPersisted.land_uses || []);
  const nextLandUses = JSON.stringify(landUses);
  const payload = {};
  if ((persistedArea ?? null) !== (area ?? null)) payload.parcel_area_total = area;
  if (persistedLandUses !== nextLandUses) payload.land_uses = landUses;
  return Object.keys(payload).length ? payload : {};
}

async function flushLandRegisterNow() {
  if (landRegisterInFlight) {
    landRegisterQueued = true;
    return;
  }

  const payload = computeLandRegisterPayload();
  if (payload === null) {
    setProjectLandRegisterStatus("error", "Błąd walidacji danych");
    landRegisterHasFailed = true;
    return;
  }
  if (!payload || !Object.keys(payload).length) {
    if (!landRegisterHasFailed) setProjectLandRegisterStatus("idle", "");
    return;
  }

  landRegisterInFlight = true;
  setProjectLandRegisterStatus("saving", "Zapisywanie…");
  try {
    const response = await fetch(`/api/projects/${projectIdentificationApiId}/mpzp`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("PROJECT_LAND_REGISTER_SAVE_FAILED");
    const persisted = await response.json();
    landRegisterPersisted = {
      parcel_area_total: persisted?.parcel_area_total ?? null,
      land_uses: normalizeLandUses(persisted?.land_uses).map((item) => ({ symbol: item.symbol, area: Number(item.area) })),
    };
    applyProjectLandRegisterToDom(persisted || {});
    setProjectLandRegisterStatus("saved", "Zapisano");
    landRegisterHasFailed = false;
  } catch (_error) {
    setProjectLandRegisterStatus("error", "Błąd zapisu. Ponów.");
    landRegisterHasFailed = true;
  } finally {
    landRegisterInFlight = false;
    if (landRegisterQueued) {
      landRegisterQueued = false;
      scheduleLandRegisterFlush(0);
    }
  }
}

function scheduleLandRegisterFlush(waitMs = 550) {
  globalThis.clearTimeout(landRegisterDebounceTimerId);
  landRegisterDebounceTimerId = globalThis.setTimeout(() => {
    if (!projectIdentificationApiId) return;
    flushLandRegisterNow();
  }, waitMs);
}

function applyProjectLandRegisterToDom(data = {}) {
  isApplyingLandRegister = true;
  try {
    const area = normalizeLandRegisterArea(data?.parcel_area_total);
    landRegisterPersisted.parcel_area_total = area === "" ? null : Number(area);
    landRegisterPersisted.land_uses = normalizeLandUses(data?.land_uses).map((item) => ({ symbol: item.symbol, area: Number(item.area) }));
    landRegisterDraft.parcel_area_total = area;
    landRegisterDraft.land_uses = normalizeLandUses(data?.land_uses);

    projectLandRegisterAreaInputs.forEach((input) => {
      if (input.value !== area) input.value = area;
    });
    renderLandRegisterRows();
    setProjectLandRegisterStatus("idle", "");
    landRegisterHasFailed = false;
  } finally {
    isApplyingLandRegister = false;
  }
}

function applyProjectIdentificationToDom(data = {}) {
  isApplyingProjectIdentification = true;
  try {
    const normalized = Object.fromEntries(PROJECT_IDENTIFICATION_FIELDS.map((key) => [key, normalizeIdentificationValue(data?.[key])]))

    projectIdentificationInputs.forEach((input) => {
      const field = input.dataset.projectIdentificationField;
      if (!field) return;
      const value = normalized[field] ?? "";
      if (input.value !== value) {
        input.value = value;
      }
    });
  } finally {
    isApplyingProjectIdentification = false;
  }
}

function setProjectIdentificationStatus(status, message = "") {
  projectIdentificationStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectIdentificationRetryButtons.forEach((button) => {
    button.classList.toggle("hidden", status !== "error");
  });

  globalThis.clearTimeout(hideSavedStateTimerId);
  if (status === "saved") {
    hideSavedStateTimerId = globalThis.setTimeout(() => {
      setProjectIdentificationStatus("idle", "");
    }, 1200);
  }
}

const projectLandUseAutosave = createIdentificationAutosave({
  fields: PROJECT_LAND_USE_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectLandUseStatus,
  async persist(payload) {
    if (!projectIdentificationApiId) return {};
    const parsedPayload = Object.fromEntries(
      Object.entries(payload).map(([field, value]) => [field, parseLandUsePayloadValue(field, value)])
    );
    const response = await fetch(`/api/projects/${projectIdentificationApiId}/mpzp`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsedPayload),
    });
    if (!response.ok) {
      throw new Error("PROJECT_LAND_USE_SAVE_FAILED");
    }
    return response.json();
  },
  onPersisted(persisted) {
    applyProjectLandUseToDom(persisted || {});
  },
});

const projectIdentificationAutosave = createIdentificationAutosave({
  fields: PROJECT_IDENTIFICATION_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectIdentificationStatus,
  async persist(payload) {
    if (!projectIdentificationApiId) return {};
    const response = await fetch(`/api/projects/${projectIdentificationApiId}/mpzp`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("PROJECT_IDENTIFICATION_SAVE_FAILED");
    }
    return response.json();
  },
  onPersisted(persisted) {
    applyProjectIdentificationToDom(persisted || {});
    window.dispatchEvent(
      new CustomEvent("project:identification:updated", {
        detail: { projectId: projectIdentificationApiId, identification: persisted || {} },
      })
    );
  },
});

async function loadProjectIdentificationFromApi() {
  if (!projectIdentificationApiId) {
    applyProjectIdentificationToDom({});
    return;
  }
  try {
    const response = await fetch(`/api/projects/${projectIdentificationApiId}/mpzp`, {
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error("PROJECT_IDENTIFICATION_FETCH_FAILED");
    }
    const payload = await response.json();
    projectIdentificationAutosave.setPersisted(payload || {});
    applyProjectIdentificationToDom(payload || {});
    projectLandUseAutosave.setPersisted(payload || {});
    applyProjectLandUseToDom(payload || {});
    applyProjectLandRegisterToDom(payload || {});
  } catch (_error) {
    projectIdentificationAutosave.setPersisted({});
    applyProjectIdentificationToDom({});
    projectLandUseAutosave.setPersisted({});
    applyProjectLandUseToDom({});
    applyProjectLandRegisterToDom({});
  }
}

projectIdentificationInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectIdentificationFieldInputs(input);
    const field = input.dataset.projectIdentificationField;
    if (!field) return;
    projectIdentificationAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("blur", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectIdentificationFieldInputs(input);
    projectIdentificationAutosave.flushOnBlur();
  });
});

projectIdentificationRetryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    projectIdentificationAutosave.retryNow();
  });
});

projectLandUseInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectLandUseFieldInputs(input);
    const field = input.dataset.projectLandUseField;
    if (!field) return;
    projectLandUseAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("change", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectLandUseFieldInputs(input);
    const field = input.dataset.projectLandUseField;
    if (!field) return;
    projectLandUseAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("blur", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectLandUseFieldInputs(input);
    projectLandUseAutosave.flushOnBlur();
  });
});

projectLandUseRetryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    projectLandUseAutosave.retryNow();
  });
});


projectLandRegisterAreaInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingLandRegister) return;
    syncLandRegisterAreaInputs(input);
    landRegisterDraft.parcel_area_total = input.value;
    scheduleLandRegisterFlush();
  });
  input.addEventListener("blur", () => {
    if (isApplyingLandRegister) return;
    syncLandRegisterAreaInputs(input);
    scheduleLandRegisterFlush(0);
  });
});

projectLandRegisterListNodes.forEach((node) => {
  node.addEventListener("input", (event) => {
    if (isApplyingLandRegister) return;
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.dataset.landUseSymbol !== undefined) {
      const index = Number(target.dataset.landUseSymbol);
      if (!Number.isInteger(index) || !landRegisterDraft.land_uses[index]) return;
      landRegisterDraft.land_uses[index].symbol = target.value;
      renderLandRegisterRows();
      scheduleLandRegisterFlush();
      return;
    }
    if (target.dataset.landUseArea !== undefined) {
      const index = Number(target.dataset.landUseArea);
      if (!Number.isInteger(index) || !landRegisterDraft.land_uses[index]) return;
      landRegisterDraft.land_uses[index].area = target.value;
      renderLandRegisterRows();
      scheduleLandRegisterFlush();
    }
  });

  node.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const removeIndexRaw = target.dataset.landUseRemove;
    if (removeIndexRaw === undefined) return;
    const index = Number(removeIndexRaw);
    if (!Number.isInteger(index)) return;
    landRegisterDraft.land_uses.splice(index, 1);
    renderLandRegisterRows();
    scheduleLandRegisterFlush(0);
  });
});

projectLandRegisterAddButtons.forEach((button) => {
  button.addEventListener("click", () => {
    landRegisterDraft.land_uses.push({ symbol: "", area: "" });
    renderLandRegisterRows();
    scheduleLandRegisterFlush(0);
  });
});

projectLandRegisterRetryButtons.forEach((button) => {
  button.addEventListener("click", () => scheduleLandRegisterFlush(0));
});

window.addEventListener("project:active:changed", (event) => {
  projectIdentificationApiId = event?.detail?.apiId || null;
  loadProjectIdentificationFromApi();
});

window.addEventListener("project:identification:updated", (event) => {
  const detail = event?.detail || {};
  if (!projectIdentificationApiId || detail.projectId !== projectIdentificationApiId) return;
  applyProjectIdentificationToDom(detail.identification || {});
  applyProjectLandUseToDom(detail.identification || {});
  applyProjectLandRegisterToDom(detail.identification || {});
});

const planState = {
  documents: [],
  pendingDeleteId: null,
};

const planAllowedExtensions = new Set([".dxf", ".dwg", ".pdf"]);
const planAllowedMime = {
  ".pdf": new Set(["application/pdf"]),
  ".dxf": new Set(["application/dxf", "image/vnd.dxf", "application/octet-stream"]),
  ".dwg": new Set(["application/acad", "image/vnd.dwg", "application/octet-stream"]),
};

const activeTabClasses = [
  "bg-emerald-600",
  "text-white",
  "shadow-[0_10px_18px_rgba(16,185,129,0.22)]",
];
const inactiveTabClasses = [
  "text-zinc-700",
  "hover:bg-emerald-500/10",
];
const activeParcelClasses = [
  "bg-emerald-600",
  "text-white",
  "shadow-[0_8px_14px_rgba(16,185,129,0.22)]",
];
const inactiveParcelClasses = [
  "text-zinc-700",
  "hover:bg-emerald-500/10",
];

function setMenuPreviewView(active) {
  if (!menuPreviewShell) return;
  menuPreviewShell.classList.toggle("active", active);
  document.body.classList.toggle("menu-preview-open", active);
  if (active) {
    loadPlanDocuments();
  }
}

function setTabActive(tab, isActive, activeClasses, inactiveClasses) {
  if (!tab) return;
  activeClasses.forEach((cls) => tab.classList.toggle(cls, isActive));
  inactiveClasses.forEach((cls) => tab.classList.toggle(cls, !isActive));
  tab.setAttribute("aria-pressed", isActive ? "true" : "false");
}

function setMenuTab(nextTab) {
  menuPanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.menuPanel !== nextTab);
  });
  menuTabs.forEach((tab) => {
    const isActive = tab.dataset.menuTab === nextTab;
    setTabActive(tab, isActive, activeTabClasses, inactiveTabClasses);
  });
}

function setParcelTab(nextTab) {
  parcelPanels.forEach((panel) => {
    panel.toggleAttribute("hidden", panel.dataset.parcelPanel !== nextTab);
  });
  parcelTabs.forEach((tab) => {
    const isActive = tab.dataset.parcelTab === nextTab;
    setTabActive(tab, isActive, activeParcelClasses, inactiveParcelClasses);
  });
}

function notifyTopbar(message, variant = "success", durationMs) {
  if (!message) return;
  window.dispatchEvent(
    new CustomEvent("topbar:notify", {
      detail: { message, variant, durationMs },
    })
  );
}

function getFileExtension(name) {
  const idx = name.lastIndexOf(".");
  return idx === -1 ? "" : name.slice(idx).toLowerCase();
}

function validatePlanFile(file) {
  if (!file) return { ok: false, message: "Nie wybrano pliku." };
  const ext = getFileExtension(file.name);
  if (!planAllowedExtensions.has(ext)) {
    return { ok: false, message: "Dozwolone formaty: DWG, DXF lub PDF." };
  }
  const allowedMimes = planAllowedMime[ext];
  if (allowedMimes && file.type && !allowedMimes.has(file.type)) {
    return { ok: false, message: "Nieobsługiwany typ pliku. Wgraj poprawny format." };
  }
  return { ok: true };
}

function renderPlanDocuments() {
  if (!planUploadList) return;
  planUploadList.innerHTML = "";
  const hasDocs = planState.documents.length > 0;
  if (planUploadEmpty) {
    planUploadEmpty.classList.toggle("hidden", hasDocs);
  }
  planState.documents.forEach((doc) => {
    const row = document.createElement("div");
    row.className = "grid grid-cols-[1fr_auto] items-center gap-3 px-4 py-1.5";

    const name = document.createElement("div");
    name.className = "min-w-0";
    name.innerHTML = `<div class="truncate text-[13px] font-semibold tracking-[-0.01em] text-zinc-900">${doc.fileName}</div>`;

    const actions = document.createElement("div");
    actions.className = "flex items-center gap-1";
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.setAttribute("aria-label", "Usuń");
    deleteBtn.className =
      "grid h-7 w-7 place-items-center rounded-full text-rose-600 transition hover:bg-rose-500/10 hover:text-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300";
    deleteBtn.innerHTML = `
      <svg viewBox="0 0 24 24" class="h-[14px] w-[14px]" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 6h18" />
        <path d="M8 6V4.5A1.5 1.5 0 0 1 9.5 3h5A1.5 1.5 0 0 1 16 4.5V6" />
        <path d="M6.5 6l1 15h9l1-15" />
        <path d="M10 10v8" />
        <path d="M14 10v8" />
      </svg>
    `;
    deleteBtn.addEventListener("click", () => openPlanDeleteModal(doc));
    actions.appendChild(deleteBtn);

    row.appendChild(name);
    row.appendChild(actions);
    planUploadList.appendChild(row);
  });
}

async function loadPlanDocuments() {
  if (!planUploadList) return;
  try {
    const response = await fetch("/api/plan-documents");
    if (!response.ok) {
      throw new Error("Nie udało się pobrać listy plików.");
    }
    const payload = await response.json();
    planState.documents = payload.documents || [];
    renderPlanDocuments();
  } catch (error) {
    notifyTopbar(error.message, "error");
  }
}

async function uploadPlanDocument(file) {
  if (!file) return;
  const validation = validatePlanFile(file);
  if (!validation.ok) {
    notifyTopbar(validation.message, "error", 10000);
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch("/api/plan-documents", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Nie udało się wgrać pliku.");
    }
    await loadPlanDocuments();
    notifyTopbar("Plik planistyczny został wgrany prawidłowo.", "success", 10000);
  } catch (error) {
    notifyTopbar(error.message, "error", 10000);
  }
}

function openPlanDeleteModal(doc) {
  if (!planDeleteModal) return;
  planState.pendingDeleteId = doc.id;
  if (planDeleteName) {
    planDeleteName.textContent = doc.fileName;
  }
  planDeleteModal.classList.remove("hidden");
}

function closePlanDeleteModal() {
  if (!planDeleteModal) return;
  planState.pendingDeleteId = null;
  planDeleteModal.classList.add("hidden");
}

async function confirmPlanDelete() {
  if (!planState.pendingDeleteId) return;
  try {
    const response = await fetch(`/api/plan-documents/${planState.pendingDeleteId}`, { method: "DELETE" });
    if (!response.ok) {
      throw new Error("Nie udało się usunąć pliku.");
    }
    await loadPlanDocuments();
    notifyTopbar("Plik planistyczny został usunięty.", "success");
  } catch (error) {
    notifyTopbar(error.message, "error");
  } finally {
    closePlanDeleteModal();
  }
}

openMenuPreviewBtn?.addEventListener("click", () => setMenuPreviewView(true));
closeMenuPreviewBtn?.addEventListener("click", () => setMenuPreviewView(false));
menuPreviewShell?.addEventListener("click", (event) => {
  if (event.target === menuPreviewShell) {
    setMenuPreviewView(false);
  }
});

menuTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setMenuTab(tab.dataset.menuTab);
  });
});

parcelTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setParcelTab(tab.dataset.parcelTab);
  });
});

setMenuTab("dzialka");
setParcelTab("138-1");
renderPlanDocuments();

planAddBtn?.addEventListener("click", () => planFileInput?.click());
planHelpToggle?.addEventListener("click", (event) => {
  event.stopPropagation();
  const isActive = planHelpToggle.classList.toggle("is-active");
  planHelpToggle.setAttribute("aria-pressed", isActive ? "true" : "false");
});
document.addEventListener("click", (event) => {
  if (!planHelpToggle || !planHelpToggle.classList.contains("is-active")) return;
  if (planHelpToggle.contains(event.target)) return;
  planHelpToggle.classList.remove("is-active");
  planHelpToggle.setAttribute("aria-pressed", "false");
});
planFileInput?.addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (file) {
    uploadPlanDocument(file);
  }
  event.target.value = "";
});
planDeleteCancel?.addEventListener("click", closePlanDeleteModal);
planDeleteConfirm?.addEventListener("click", confirmPlanDelete);
planDeleteModal?.addEventListener("click", (event) => {
  if (event.target === planDeleteModal) {
    closePlanDeleteModal();
  }
});

if (menuPreviewShell?.dataset.autoOpen === "true") {
  setMenuPreviewView(true);
}

