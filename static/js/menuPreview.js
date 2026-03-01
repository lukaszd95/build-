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
  } catch (_error) {
    projectIdentificationAutosave.setPersisted({});
    applyProjectIdentificationToDom({});
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

window.addEventListener("project:active:changed", (event) => {
  projectIdentificationApiId = event?.detail?.apiId || null;
  loadProjectIdentificationFromApi();
});

window.addEventListener("project:identification:updated", (event) => {
  const detail = event?.detail || {};
  if (!projectIdentificationApiId || detail.projectId !== projectIdentificationApiId) return;
  applyProjectIdentificationToDom(detail.identification || {});
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

