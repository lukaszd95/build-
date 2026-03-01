import { variableInsetLotPolygon, polygonAreaAbs } from "./geometry/variableInset.js";
import { init3D, update3DBuilding, set3DVisible, force3DResize } from "./view3d.js";

import { wtRules } from "./rules/wt.js";
import { mpzpRules } from "./rules/mpzp.js";
import { initRulesState, applyWT, applyMpzpWzLimits, getRuleById } from "./rules/ruleEngine.js";

import { generateBuildingVariants } from "./designEngine/shapeGenerator.js";
import { initCadUI } from "./cad/cadUI.js";
import { drawCadMap } from "./cad/cadDraw.js";
import "./upload/uploadUI.js";
import "./menuPreview.js";
import { createProject as apiCreateProject, fetchProjects as apiFetchProjects } from "./services/projectApi.js";

/* =========================
  DOM
========================= */
const canvas = document.getElementById("planCanvas");
const ctx = canvas.getContext("2d");
const viewport = document.getElementById("modelViewport");
const threeContainer = document.getElementById("threeContainer");

// Topbar pills (PZT / 3D)
const pztPill = document.getElementById("pztPill");
const d3Pill = document.getElementById("d3Pill");

const viewHud = document.getElementById("viewHud");
const scaleWidget = document.getElementById("scaleWidget");
const scaleBar = document.getElementById("scaleBar");
const scaleLabel = document.getElementById("scaleLabel");
const scaleSubLabel = document.getElementById("scaleSubLabel");
const emptyState = document.getElementById("emptyState");

const analysisContent = document.getElementById("analysisContent");
const mapSummaryContent = document.getElementById("mapSummaryContent");
const mapLayerSummary = document.getElementById("mapLayersContainer");
const mapImportStatus = document.getElementById("mapImportStatus");
const mapFileInput = document.getElementById("mapFileInput");

/* =========================
  STATE
========================= */
const state = {
  plotPolygon: null,
  plotArea: 0,

  envelopeWT: null,
  envelopeArea: 0,

  buildingPolygon: null,
  buildingArea: 0,
  chosenVariantName: "—",

  bioAreaReqPercent: 30,
  coverageMaxReqPercent: 30,
  maxHeightReqM: 12,
  roofType: "flat",

  bioAreaActual: 0,
  bioAreaActualPercent: 0,
  heightTotalM: 12,

  wtParams: { distWithOpeningsM: 4, distWithoutOpeningsM: 3 },

  lastExplain: [],
  lastGeneratorExplain: [],
  lastLimits: { maxFootprintArea: Infinity, minPbcPercent: 0, maxHeightM: Infinity },

  buildingEdgeOpenings: null,
  buildingEdgeMinDistances: null,

  baseScale: 1,
  zoomFactor: 1,
  offsetX: 0,
  offsetY: 0,

  constructionElements: [],
  selectedElementId: null,
  elementIdCounter: 1,

  is3D: false,
  threeReady: false,

  rulesState: {
    wt: initRulesState(wtRules),
    mpzp: initRulesState(mpzpRules)
  },

  mapData: null,
  mapImportFile: null,
  mapImportDraft: null,
  mapImportStatus: { level: "idle", message: "Oczekuje na plik." },
  cadMap: null,
  cadImportEnabled: true,
  cadScaleMultiplier: 1,
  cadAssistEnabled: true,
  plotImport: null
};


const userProjects = [];
let activeProjectId = null;
let projectPersistTimeout = null;

function applyAuthenticatedUser(user = {}) {
  const fullName = (user.name || user.fullName || user.full_name || "").trim();
  const initials = fullName
    ? fullName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("")
    : (user.email || "U").slice(0, 2).toUpperCase();

  window.dispatchEvent(new CustomEvent("topbar:user:update", {
    detail: {
      user: {
        name: fullName || "Użytkownik",
        email: user.email || "",
        avatarUrl: `https://ui-avatars.com/api/?name=${encodeURIComponent(initials || "U")}&background=111827&color=ffffff`,
      },
    },
  }));
}

async function requireAuthenticatedUser() {
  const response = await fetch("/api/auth/me", { credentials: "include" });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("UNAUTHORIZED");
  }
  if (!response.ok) {
    throw new Error("ME_REQUEST_FAILED");
  }

  const payload = await response.json();
  const user = payload.user || {};
  window.sessionStorage.setItem("authenticatedUser", JSON.stringify(user));
  applyAuthenticatedUser(user);
  return user;
}

async function hydrateProjectsFromApi() {
  const bootstrapProjects = Array.isArray(window.__BOOTSTRAP_PROJECTS__)
    ? window.__BOOTSTRAP_PROJECTS__
    : [];
  const apiProjects = bootstrapProjects.length ? bootstrapProjects : await apiFetchProjects();
  userProjects.splice(0, userProjects.length);
  apiProjects.forEach((project) => {
    saveProjectToCollection({
      id: `api-${project.id}`,
      apiId: project.id,
      name: project.name,
      goal: project.status || "draft",
      vertices: "",
    });
  });
  renderProjectCards();
  if (userProjects.length > 0) {
    applyProjectToWorkspace(userProjects[0]);
  }
}

function deepClone(value) {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function collectWorkspaceFormData() {
  const fields = {};
  const controls = document.querySelectorAll("#workspace input[id], #workspace select[id], #workspace textarea[id]");
  controls.forEach((control) => {
    if (!control?.id) return;
    if (control.closest("#newProjectPage")) return;
    if (control.type === "file") return;
    if (control.type === "checkbox" || control.type === "radio") {
      fields[control.id] = { checked: !!control.checked };
      return;
    }
    fields[control.id] = { value: control.value ?? "" };
  });
  return fields;
}

function applyWorkspaceFormData(fields = {}) {
  Object.entries(fields).forEach(([id, payload]) => {
    const control = document.getElementById(id);
    if (!control) return;
    if ("checked" in payload && (control.type === "checkbox" || control.type === "radio")) {
      control.checked = !!payload.checked;
      return;
    }
    if ("value" in payload) {
      control.value = payload.value ?? "";
    }
  });
}

function captureWorkspaceSnapshot(project) {
  if (!project) return null;
  return {
    form: collectWorkspaceFormData(),
    mapData: deepClone(state.mapData),
    cadMap: deepClone(state.cadMap),
    plotImport: deepClone(state.plotImport),
    mapImportDraft: deepClone(state.mapImportDraft),
    mapImportStatus: deepClone(state.mapImportStatus),
    cadScaleMultiplier: state.cadScaleMultiplier,
    cadAssistEnabled: state.cadAssistEnabled,
    rulesState: deepClone(state.rulesState),
    is3D: !!state.is3D,
    vertices: project.vertices || (document.getElementById("parcelVerticesInput")?.value || ""),
  };
}

function restoreWorkspaceSnapshot(snapshot, project) {
  const fallbackVertices = project?.vertices || "";
  const data = snapshot || {
    form: {
      parcelVerticesInput: { value: fallbackVertices },
      newProjectParcelVertices: { value: fallbackVertices },
    },
  };

  applyWorkspaceFormData(data.form || {});
  state.mapData = deepClone(data.mapData ?? null);
  state.cadMap = deepClone(data.cadMap ?? null);
  state.plotImport = deepClone(data.plotImport ?? null);
  state.mapImportDraft = deepClone(data.mapImportDraft ?? null);
  state.mapImportStatus = deepClone(data.mapImportStatus ?? { level: "idle", message: "Oczekuje na plik." });
  state.cadScaleMultiplier = Number.isFinite(data.cadScaleMultiplier) ? data.cadScaleMultiplier : 1;
  state.cadAssistEnabled = data.cadAssistEnabled !== false;
  if (data.rulesState) {
    state.rulesState = deepClone(data.rulesState);
  }
}

function persistActiveProjectWorkspace() {
  if (!activeProjectId) return;
  const project = userProjects.find((item) => item.id === activeProjectId);
  if (!project) return;
  const vertices = (document.getElementById("parcelVerticesInput")?.value || "").trim();
  if (vertices) {
    project.vertices = vertices;
  }
  project.workspaceData = captureWorkspaceSnapshot(project);
}

function schedulePersistActiveProjectWorkspace() {
  if (!activeProjectId) return;
  window.clearTimeout(projectPersistTimeout);
  projectPersistTimeout = window.setTimeout(() => {
    persistActiveProjectWorkspace();
  }, 120);
}

function renderProjectCards() {
  const grid = document.querySelector("#newProjectCardsScroll .new-project-cards-grid");
  if (!grid) return;
  const createCard = document.getElementById("openNewProjectFlowBtn");
  if (!createCard) return;

  const legacyDemo = document.getElementById("openDemoProjectBtn");
  if (legacyDemo) {
    legacyDemo.classList.add("hidden");
  }

  grid.querySelectorAll("[data-user-project-card='1']").forEach((el) => el.remove());
  userProjects.forEach((project) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "project-card project-card-demo";
    card.setAttribute("data-user-project-card", "1");
    card.setAttribute("aria-label", `Otwórz projekt ${project.name}`);
    card.innerHTML = `
      <span class="project-card-badge">PROJEKT</span>
      <div class="project-card-preview" aria-hidden="true">
        <div class="project-card-preview-roof"></div>
        <div class="project-card-preview-house"></div>
        <div class="project-card-preview-parcel"></div>
      </div>
      <div class="project-card-content">
        <span class="project-card-title"></span>
      </div>
    `;
    card.querySelector(".project-card-title").textContent = project.name;
    card.addEventListener("click", () => {
      applyProjectToWorkspace(project);
      window.dispatchEvent(new CustomEvent("topbar:notify", {
        detail: { variant: "success", message: `Otwarto projekt: ${project.name}.` },
      }));
    });
    grid.appendChild(card);
  });
}

function updateProjectLibraryCount() {
  const countEl = document.getElementById("newProjectLibraryCount");
  if (!countEl) return;
  const total = userProjects.length + 1; // + karta "Nowy projekt"
  const suffix = total === 1 ? "projekt" : (total >= 2 && total <= 4 ? "projekty" : "projektów");
  countEl.textContent = `${total} ${suffix}`;
}

function syncTopbarProjects() {
  const projects = userProjects.map((project) => project.name);
  const currentProject = userProjects.find((project) => project.id === activeProjectId)?.name || projects[0] || "Wybierz projekt";
  window.dispatchEvent(new CustomEvent("topbar:projects:update", {
    detail: { projects, currentProject },
  }));
}

function applyProjectToWorkspace(project) {
  if (!project) return;
  persistActiveProjectWorkspace();
  activeProjectId = project.id;
  restoreWorkspaceSnapshot(project.workspaceData, project);

  const nameInput = document.getElementById("newProjectNameInput");
  if (nameInput && project.name) {
    nameInput.value = project.name;
  }

  compute(false);
  set3DMode(project.workspaceData?.is3D === true);
  if (state.is3D) {
    update3DFromState();
  } else {
    draw2D();
  }

  closeCreateProjectPage();
  syncTopbarProjects();
  window.dispatchEvent(new CustomEvent("project:active:changed", {
    detail: {
      id: project.id,
      apiId: project.apiId ?? null,
      name: project.name,
    },
  }));
}

function saveProjectToCollection(project) {
  if (!project?.name) return;
  const normalizedProject = {
    ...project,
    workspaceData: project.workspaceData || captureWorkspaceSnapshot(project),
  };
  const existingIndex = userProjects.findIndex((item) => item.id === project.id || item.name === project.name);
  if (existingIndex >= 0) {
    userProjects[existingIndex] = { ...userProjects[existingIndex], ...normalizedProject };
  } else {
    userProjects.push(normalizedProject);
  }
  updateProjectLibraryCount();
  syncTopbarProjects();
  renderProjectCards();
  if (userProjects.length > 0) {
    applyProjectToWorkspace(userProjects[0]);
  }
}

/* =========================
  MODALS
========================= */
function openModal(id){ document.getElementById(id)?.classList.add("active"); }
function closeModal(id){ document.getElementById(id)?.classList.remove("active"); }

window.openSettingsModal = () => openModal("settingsModal");
function openCreateProjectPage() {
  switchNewProjectStep("name");
  setNewProjectMode("chooser");
  document.body.classList.add("project-page-active");
  const page = document.getElementById("newProjectPage");
  page?.setAttribute("aria-hidden", "false");
  const chooserBtn = document.getElementById("openNewProjectFlowBtn");
  if (chooserBtn) {
    window.setTimeout(() => chooserBtn.focus(), 0);
  }
}

function closeCreateProjectPage() {
  document.body.classList.remove("project-page-active");
  const page = document.getElementById("newProjectPage");
  page?.setAttribute("aria-hidden", "true");
}

window.openCreateProjectModal = openCreateProjectPage;

function setNewProjectMode(mode) {
  const chooser = document.getElementById("newProjectChooser");
  const editor = document.getElementById("newProjectEditor");
  const title = document.getElementById("newProjectTopbarTitle");
  const windowTitle = document.getElementById("newProjectWindowTitle");
  const showEditor = mode === "editor";
  chooser?.classList.toggle("hidden", showEditor);
  editor?.classList.toggle("hidden", !showEditor);
  if (title) {
    title.textContent = showEditor ? "NOWY PROJEKT" : "PROJEKTY";
  }
  if (windowTitle) {
    windowTitle.textContent = showEditor ? "NOWY PROJEKT" : "PROJEKTY";
  }
}

function switchNewProjectStep(step) {
  const normalized = step === "parcel" ? "parcel" : "name";
  document.querySelectorAll("[data-project-step]").forEach((button) => {
    const isActive = button.getAttribute("data-project-step") === normalized;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  document.querySelectorAll("[data-project-panel]").forEach((panel) => {
    const isActive = panel.getAttribute("data-project-panel") === normalized;
    panel.classList.toggle("active", isActive);
  });
}

const testPdfInput = document.getElementById("testPdfInput");
const testPdfList = document.getElementById("testPdfList");
const testPdfError = document.getElementById("testPdfError");
const testParcelIdValue = document.getElementById("testParcelIdValue");
const testObrebValue = document.getElementById("testObrebValue");
const testStreetValue = document.getElementById("testStreetValue");
const testLocalityValue = document.getElementById("testLocalityValue");
const integrationStatus = document.getElementById("integrationStatus");
const tesseractStatusNote = document.getElementById("tesseractStatusNote");
const ollamaStatusNote = document.getElementById("ollamaStatusNote");
const testPdfItems = [];

function setTestPdfError(message) {
  if (!testPdfError) return;
  testPdfError.textContent = message || "";
}

function isSupportedTestFile(file) {
  if (!file) return false;
  const name = file.name || "";
  const lower = name.toLowerCase();
  const isPdf = file.type === "application/pdf" || lower.endsWith(".pdf");
  const isImage =
    file.type === "image/png" ||
    file.type === "image/jpeg" ||
    file.type === "image/tiff" ||
    file.type === "image/heic" ||
    file.type === "image/heif" ||
    lower.endsWith(".png") ||
    lower.endsWith(".jpg") ||
    lower.endsWith(".jpeg") ||
    lower.endsWith(".tif") ||
    lower.endsWith(".tiff") ||
    lower.endsWith(".heic") ||
    lower.endsWith(".heif");
  return isPdf || isImage;
}

function setParcelIdValue(value) {
  if (!testParcelIdValue) return;
  testParcelIdValue.textContent = value || "—";
}

function setObrebValue(value) {
  if (!testObrebValue) return;
  testObrebValue.textContent = value || "—";
}

function setStreetValue(value) {
  if (!testStreetValue) return;
  testStreetValue.textContent = value || "—";
}

function setLocalityValue(value) {
  if (!testLocalityValue) return;
  testLocalityValue.textContent = value || "—";
}

function setPurposeValue(value) {
  setTableValue("testPurposeValue", value);
}

function setBioActiveValue(value) {
  setTableValue("testBioActiveValue", value);
}

function setTableValue(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = value || "—";
}

async function extractParcelDataViaOcr(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/ocr-preview", { method: "POST", body: formData });
  if (!response.ok) {
    let errorMessage = "Nie udało się odczytać dokumentu.";
    try {
      const payload = await response.json();
      if (payload?.error) {
        errorMessage = payload.error;
      }
    } catch (error) {
      // ignore JSON parsing issues
    }
    throw new Error(errorMessage);
  }
  return response.json();
}

function pickFirstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return null;
}

function normalizeOcrPreviewData(payload) {
  const safePayload = payload || {};
  const documentClassification = safePayload.documentClassification || safePayload.document_classification || {};
  return {
    parcelId: pickFirstDefined(safePayload.parcelId, safePayload.parcel_id),
    obreb: pickFirstDefined(safePayload.obreb, safePayload.precinct),
    street: pickFirstDefined(safePayload.street, safePayload.ulica),
    locality: pickFirstDefined(safePayload.locality, safePayload.city, safePayload.miejscowosc),
    purpose: safePayload.purpose,
    purposePrimary: safePayload.purposePrimary,
    purposeAllowed: safePayload.purposeAllowed,
    purposeForbidden: safePayload.purposeForbidden,
    maxBuildingHeight: safePayload.maxBuildingHeight,
    maxAboveGroundStoreys: safePayload.maxAboveGroundStoreys,
    maxBelowGroundStoreys: safePayload.maxBelowGroundStoreys,
    maxRidgeHeight: safePayload.maxRidgeHeight,
    maxEavesHeight: safePayload.maxEavesHeight,
    minIntensity: safePayload.minIntensity,
    maxIntensity: safePayload.maxIntensity,
    maxCoverage: safePayload.maxCoverage,
    bioActive: safePayload.bioActive,
    minFacadeWidth: safePayload.minFacadeWidth,
    maxFacadeWidth: safePayload.maxFacadeWidth,
    sourceFile: safePayload.sourceFile,
    docType: pickFirstDefined(
      safePayload.fileType,
      safePayload.file_type,
      safePayload.docType,
      safePayload.documentType,
      safePayload.document_type,
      documentClassification.fileType,
      documentClassification.file_type,
      documentClassification.docType,
      documentClassification.documentType,
      documentClassification.document_type,
    ),
  };
}

function applyOcrPreviewToTestModal(data) {
  setParcelIdValue(data.parcelId);
  setObrebValue(data.obreb);
  setStreetValue(data.street);
  setLocalityValue(data.locality);
  setPurposeValue(data.purpose);
  setTableValue("testPurposePrimaryValue", data.purposePrimary);
  setTableValue("testPurposeAllowedValue", data.purposeAllowed);
  setTableValue("testPurposeForbiddenValue", data.purposeForbidden);
  setTableValue("testMaxBuildingHeightValue", data.maxBuildingHeight);
  setTableValue("testMaxAboveGroundFloorsValue", data.maxAboveGroundStoreys);
  setTableValue("testMaxBelowGroundFloorsValue", data.maxBelowGroundStoreys);
  setTableValue("testMaxRidgeHeightValue", data.maxRidgeHeight);
  setTableValue("testMaxEavesHeightValue", data.maxEavesHeight);
  setTableValue("testMinIntensityValue", data.minIntensity);
  setTableValue("testMaxIntensityValue", data.maxIntensity);
  setTableValue("testMaxCoverageValue", data.maxCoverage);
  setBioActiveValue(data.bioActive);
  setTableValue("testMinFacadeWidthValue", data.minFacadeWidth);
  setTableValue("testMaxFacadeWidthValue", data.maxFacadeWidth);
  setTableValue("testSourceFileValue", data.sourceFile);
  setTableValue("testDocTypeValue", data.docType);
}

function buildMissingLocationWarning(data) {
  const missing = [];
  if (!data.parcelId) missing.push("nr działki");
  if (!data.obreb) missing.push("obręb");
  if (!data.street) missing.push("ulica");
  if (!data.locality) missing.push("miasto/miejscowość");
  if (!missing.length) return "";
  return `Nie znaleziono części danych: ${missing.join(", ")}.`;
}

async function extractParcelDataFromPdf(file) {
  return extractParcelDataViaOcr(file);
}

function renderTestPdfList() {
  if (!testPdfList) return;
  testPdfList.innerHTML = "";
  if (!testPdfItems.length) {
    testPdfList.innerHTML = "<li class=\"muted\">Brak wgranych plików.</li>";
    return;
  }

  testPdfItems.forEach((item) => {
    const row = document.createElement("li");
    row.className = "test-upload-item";

    const name = document.createElement("div");
    name.className = "test-upload-item-name";
    name.textContent = item.name;

    const actions = document.createElement("div");
    actions.className = "test-upload-item-actions";

    const load = document.createElement("button");
    load.type = "button";
    load.className = "btn-primary";
    load.textContent = "Zaczytaj";
    load.addEventListener("click", async () => {
      if (!item.file) return;
      setTestPdfError("Szukam danych działki i rozpoznaję typ dokumentu...");
      try {
        const apiPayload = await extractParcelDataFromPdf(item.file);
        const normalizedData = normalizeOcrPreviewData({ ...apiPayload, sourceFile: apiPayload?.sourceFile || item.name });
        applyOcrPreviewToTestModal(normalizedData);
        const warningMessage = buildMissingLocationWarning(normalizedData);
        setTestPdfError(warningMessage);
      } catch (error) {
        console.error("PDF parse error:", error);
        const message = error?.message || "Nie udało się odczytać dokumentu.";
        setTestPdfError(message);
      }
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn-secondary";
    remove.textContent = "Usuń";
    remove.addEventListener("click", () => {
      const index = testPdfItems.findIndex((entry) => entry.id === item.id);
      if (index >= 0) {
        testPdfItems.splice(index, 1);
        renderTestPdfList();
      }
    });

    actions.appendChild(load);
    actions.appendChild(remove);
    row.appendChild(name);
    row.appendChild(actions);
    testPdfList.appendChild(row);
  });
}

testPdfInput?.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;

  const invalid = files.find((file) => !isSupportedTestFile(file));
  if (invalid) {
    setTestPdfError("Dozwolone są pliki PDF/JPG/PNG/HEIC/TIFF.");
    testPdfInput.value = "";
    return;
  }

  setTestPdfError("");
  files.forEach((file) => {
    testPdfItems.push({
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: file.name,
      file,
    });
  });
  testPdfInput.value = "";
  renderTestPdfList();
});

function setIntegrationStatus(key, available, message) {
  if (!integrationStatus) return;
  const icon = integrationStatus.querySelector(`[data-status-key="${key}"]`);
  if (icon) {
    icon.dataset.status = available ? "ok" : "error";
  }
  if (key === "tesseract" && tesseractStatusNote) {
    tesseractStatusNote.textContent = message || (available ? "Dostępny." : "Niedostępny.");
  }
  if (key === "ollama" && ollamaStatusNote) {
    ollamaStatusNote.textContent = message || (available ? "Dostępny." : "Niedostępny.");
  }
}

async function refreshIntegrationStatus() {
  if (!integrationStatus) return;
  integrationStatus
    .querySelectorAll("[data-status-key]")
    .forEach((icon) => (icon.dataset.status = "unknown"));
  if (tesseractStatusNote) tesseractStatusNote.textContent = "Sprawdzanie...";
  if (ollamaStatusNote) ollamaStatusNote.textContent = "Sprawdzanie...";

  try {
    const response = await fetch("/api/integration-status");
    if (!response.ok) {
      throw new Error("Nie udało się pobrać statusu.");
    }
    const payload = await response.json();
    const tesseract = payload?.tesseract || {};
    const ollama = payload?.ollama || {};
    setIntegrationStatus("tesseract", Boolean(tesseract.available), tesseract.message);
    setIntegrationStatus("ollama", Boolean(ollama.available), ollama.message);
  } catch (error) {
    setIntegrationStatus("tesseract", false, "Brak informacji o statusie.");
    setIntegrationStatus("ollama", false, "Brak informacji o statusie.");
    console.error("Integration status error:", error);
  }
}

document.querySelectorAll("[data-open-modal]").forEach((button) => {
  const modalId = button.getAttribute("data-open-modal");
  if (!modalId) return;
  const handleOpen = () => {
    openModal(modalId);
    if (modalId === "testModal") {
      refreshIntegrationStatus();
    }
  };
  button.addEventListener("click", handleOpen);
  button.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleOpen();
    }
  });
});

document.getElementById("openMpzpBtn")?.addEventListener("click", () => {
  openModal("mpzpModal");
  renderMPZPPanel();
  renderMPZPModalPanel();
});
document.getElementById("openMapImportBtn")?.addEventListener("click", () => openModal("mapImportModal"));

document.getElementById("openLawBtn")?.addEventListener("click", () => {
  openModal("lawModal");
  renderWT12Panel();
  renderMPZPPanel();
  renderMPZPModalPanel();
});

document.querySelectorAll("[data-close-modal]").forEach(btn => {
  btn.addEventListener("click", () => closeModal(btn.getAttribute("data-close-modal")));
});
document.querySelectorAll(".modal-overlay").forEach(overlay => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.classList.remove("active");
  });
});

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.data?.type === "wModal:close") {
    closeModal("wModal");
  }
});

mapFileInput?.addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  state.mapImportFile = file || null;
  state.mapImportDraft = null;
  renderMapLayerSummary(null);

  if (!file) {
    setMapStatus("warn", "Nie wybrano pliku.");
    return;
  }
  setMapStatus("info", `Wybrano plik: ${file.name}`);
});

/* =========================
  PRAWO: tabs
========================= */
function initLawTabs() {
  const modal = document.getElementById("lawModal");
  if (!modal) return;

  const tabButtons = modal.querySelectorAll(".tab-btn[data-tab]");
  const panels = modal.querySelectorAll(".tab-panel");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.toggle("active", b === btn));
      panels.forEach(p => p.classList.toggle("active", p.id === targetId));
    });
  });
}

/* =========================
  WT §12 PANEL
========================= */
function renderWT12Panel() {
  const rule = getRuleById(wtRules, "WT_12");
  const rs = state.rulesState?.wt?.["WT_12"];
  if (!rule || !rs) return;

  const textEl = document.getElementById("wt12Text");
  const usedEl = document.getElementById("wt12UsedLabel");
  const enabledEl = document.getElementById("wt12Enabled");
  const openEl = document.getElementById("wt12DistOpen");
  const noEl = document.getElementById("wt12DistNo");

  if (textEl) textEl.textContent = rule.text;

  if (usedEl) {
    usedEl.textContent = `Użyty w projekcie: ${rs.usedLastRun ? "TAK" : "NIE"}`;
    usedEl.style.fontWeight = "800";
    usedEl.style.color = rs.usedLastRun ? "#16a34a" : "#b45309";
  }

  if (enabledEl) enabledEl.checked = !!rs.enabled;

  // ✅ bezpieczne odczyty (fallbacki)
  const dOpen = Number.isFinite(+rs.params?.distWithOpeningsM) ? +rs.params.distWithOpeningsM : 4;
  const dNo   = Number.isFinite(+rs.params?.distWithoutOpeningsM) ? +rs.params.distWithoutOpeningsM : 3;

  if (openEl) openEl.value = String(dOpen);
  if (noEl) noEl.value = String(dNo);
}

function bindWT12Panel() {
  const enabledEl = document.getElementById("wt12Enabled");
  const openEl = document.getElementById("wt12DistOpen");
  const noEl = document.getElementById("wt12DistNo");

  enabledEl?.addEventListener("change", () => {
    if (!state.rulesState?.wt?.["WT_12"]) return;
    state.rulesState.wt["WT_12"].enabled = enabledEl.checked;
    generateAfterRuleChange();
    renderWT12Panel();
  });

  function onNumsChanged() {
    const v1 = parseFloat(openEl?.value);
    const v2 = parseFloat(noEl?.value);
    const s = state.rulesState?.wt?.["WT_12"];
    if (!s) return;

    if (!s.params) s.params = { distWithOpeningsM: 4, distWithoutOpeningsM: 3 };

    if (Number.isFinite(v1)) s.params.distWithOpeningsM = Math.max(0, v1);
    if (Number.isFinite(v2)) s.params.distWithoutOpeningsM = Math.max(0, v2);

    generateAfterRuleChange();
    renderWT12Panel();
  }

  openEl?.addEventListener("input", onNumsChanged);
  noEl?.addEventListener("input", onNumsChanged);
}

/* =========================
  MPZP/WZ UI
========================= */
function renderMPZPPanel() {
  const rCov = getRuleById(mpzpRules, "MPZP_COVERAGE_MAX");
  const sCov = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];

  const rPbc = getRuleById(mpzpRules, "MPZP_PBC_MIN");
  const sPbc = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];

  if (rCov && sCov) {
    const textEl = document.getElementById("mpzpCoverageText");
    const usedEl = document.getElementById("mpzpCoverageUsedLabel");
    const enEl = document.getElementById("mpzpCoverageEnabled");
    const pctEl = document.getElementById("mpzpCoveragePercent");

    if (textEl) textEl.textContent = rCov.text;
    if (usedEl) {
      usedEl.textContent = `Użyty w projekcie: ${sCov.usedLastRun ? "TAK" : "NIE"}`;
      usedEl.style.fontWeight = "800";
      usedEl.style.color = sCov.usedLastRun ? "#16a34a" : "#b45309";
    }
    if (enEl) enEl.checked = !!sCov.enabled;
    if (pctEl) pctEl.value = String(sCov.params?.coverageMaxPercent ?? 30);
  }

  if (rPbc && sPbc) {
    const textEl = document.getElementById("mpzpPbcText");
    const usedEl = document.getElementById("mpzpPbcUsedLabel");
    const enEl = document.getElementById("mpzpPbcEnabled");
    const pctEl = document.getElementById("mpzpPbcPercent");

    if (textEl) textEl.textContent = rPbc.text;
    if (usedEl) {
      usedEl.textContent = `Użyty w projekcie: ${sPbc.usedLastRun ? "TAK" : "NIE"}`;
      usedEl.style.fontWeight = "800";
      usedEl.style.color = sPbc.usedLastRun ? "#16a34a" : "#b45309";
    }
    if (enEl) enEl.checked = !!sPbc.enabled;
    if (pctEl) pctEl.value = String(sPbc.params?.pbcMinPercent ?? 30);
  }
}

function renderMPZPModalPanel() {
  const rCov = getRuleById(mpzpRules, "MPZP_COVERAGE_MAX");
  const sCov = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];

  const rPbc = getRuleById(mpzpRules, "MPZP_PBC_MIN");
  const sPbc = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];

  if (rCov && sCov) {
    const usedEl = document.getElementById("mpzpModalCoverageUsed");
    const textEl = document.getElementById("mpzpModalCoverageText");
    const enEl = document.getElementById("mpzpModalCoverageEnabled");
    const pctEl = document.getElementById("coverageMaxReq");

    if (usedEl) {
      usedEl.textContent = `Użyty w projekcie: ${sCov.usedLastRun ? "TAK" : "NIE"}`;
      usedEl.style.fontWeight = "800";
      usedEl.style.color = sCov.usedLastRun ? "#16a34a" : "#b45309";
    }
    if (textEl) textEl.textContent = rCov.text;
    if (enEl) enEl.checked = !!sCov.enabled;
    if (pctEl) pctEl.value = String(sCov.params?.coverageMaxPercent ?? 30);
  }

  if (rPbc && sPbc) {
    const usedEl = document.getElementById("mpzpModalPbcUsed");
    const textEl = document.getElementById("mpzpModalPbcText");
    const enEl = document.getElementById("mpzpModalPbcEnabled");
    const pctEl = document.getElementById("bioAreaReq");

    if (usedEl) {
      usedEl.textContent = `Użyty w projekcie: ${sPbc.usedLastRun ? "TAK" : "NIE"}`;
      usedEl.style.fontWeight = "800";
      usedEl.style.color = sPbc.usedLastRun ? "#16a34a" : "#b45309";
    }
    if (textEl) textEl.textContent = rPbc.text;
    if (enEl) enEl.checked = !!sPbc.enabled;
    if (pctEl) pctEl.value = String(sPbc.params?.pbcMinPercent ?? 30);
  }
}

function syncMpzpUiEverywhereFromRules() {
  renderMPZPModalPanel();
  renderMPZPPanel();
}

function bindMPZPPanel() {
  const covEnabled = document.getElementById("mpzpCoverageEnabled");
  const covPct = document.getElementById("mpzpCoveragePercent");

  const pbcEnabled = document.getElementById("mpzpPbcEnabled");
  const pbcPct = document.getElementById("mpzpPbcPercent");

  covEnabled?.addEventListener("change", () => {
    const s = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];
    if (!s) return;
    s.enabled = covEnabled.checked;
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  covPct?.addEventListener("input", () => {
    const s = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];
    if (!s) return;
    const v = parseFloat(covPct.value);
    if (Number.isFinite(v)) s.params.coverageMaxPercent = clamp(v, 0, 100);
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  pbcEnabled?.addEventListener("change", () => {
    const s = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];
    if (!s) return;
    s.enabled = pbcEnabled.checked;
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  pbcPct?.addEventListener("input", () => {
    const s = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];
    if (!s) return;
    const v = parseFloat(pbcPct.value);
    if (Number.isFinite(v)) s.params.pbcMinPercent = clamp(v, 0, 100);
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });
}

function bindMPZPModalPanel() {
  const covEnabled = document.getElementById("mpzpModalCoverageEnabled");
  const covPct = document.getElementById("coverageMaxReq");

  const pbcEnabled = document.getElementById("mpzpModalPbcEnabled");
  const pbcPct = document.getElementById("bioAreaReq");

  covEnabled?.addEventListener("change", () => {
    const s = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];
    if (!s) return;
    s.enabled = covEnabled.checked;
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  covPct?.addEventListener("input", () => {
    const s = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];
    if (!s) return;
    const v = parseFloat(covPct.value);
    if (Number.isFinite(v)) s.params.coverageMaxPercent = clamp(v, 0, 100);
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  pbcEnabled?.addEventListener("change", () => {
    const s = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];
    if (!s) return;
    s.enabled = pbcEnabled.checked;
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });

  pbcPct?.addEventListener("input", () => {
    const s = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];
    if (!s) return;
    const v = parseFloat(pbcPct.value);
    if (Number.isFinite(v)) s.params.pbcMinPercent = clamp(v, 0, 100);
    syncMpzpUiEverywhereFromRules();
    generateAfterRuleChange();
  });
}

/* =========================
  VIEW MODE PZT / 3D
========================= */
function syncViewPills(){
  pztPill?.classList.toggle("active", !state.is3D);
  d3Pill?.classList.toggle("active", state.is3D);
  window.dispatchEvent(new CustomEvent("view:mode:sync", { detail: { mode: state.is3D ? "3D" : "PZT" } }));
}
function set3DMode(on){
  state.is3D = on;
  syncViewPills();

  canvas.style.display = on ? "none" : "block";
  threeContainer.style.display = on ? "block" : "none";
  set3DVisible(on);

  const sw = document.getElementById("scaleWidget");
  if (sw) sw.style.display = on ? "none" : "flex";
}
async function ensure3D(){
  if (state.threeReady) return;
  await init3D(threeContainer);
  state.threeReady = true;
}
function update3DFromState(){
  if (!state.threeReady) return;
  update3DBuilding({
    footprint: state.buildingPolygon,
    heightTotal: state.heightTotalM,
    lot: state.plotPolygon,
    lotLabels: state.plotPolygon ? state.plotPolygon.map((_,i)=>String.fromCharCode(65+(i%26))) : []
  });
}

pztPill?.addEventListener("click", () => {
  if (state.is3D) set3DMode(false);
  draw2D();
});
d3Pill?.addEventListener("click", async () => {
  if (state.is3D) return;
  set3DMode(true);
  await ensure3D();
  force3DResize();
  update3DFromState();
});

window.addEventListener("topbar:view:change", async (event) => {
  const mode = event?.detail?.mode;
  if (mode === "PZT") {
    if (state.is3D) set3DMode(false);
    draw2D();
    return;
  }
  if (mode === "3D") {
    if (!state.is3D) {
      set3DMode(true);
    }
    await ensure3D();
    force3DResize();
    update3DFromState();
  }
});

/* =========================
  2D PAN + ZOOM
========================= */
let isPanning=false;
let panStartX=0, panStartY=0, panOX=0, panOY=0;

canvas.addEventListener("mousedown",(e)=>{
  if (e.button !== 0) return;
  if (state.is3D) return;
  isPanning=true;
  canvas.style.cursor="grabbing";
  panStartX=e.clientX; panStartY=e.clientY;
  panOX=state.offsetX; panOY=state.offsetY;
});
window.addEventListener("mousemove",(e)=>{
  if(!isPanning) return;
  state.offsetX = panOX + (e.clientX-panStartX);
  state.offsetY = panOY + (e.clientY-panStartY);
  draw2D();
});
window.addEventListener("mouseup",()=>{
  if(!isPanning) return;
  isPanning=false;
  canvas.style.cursor="grab";
});
canvas.addEventListener("wheel",(e)=>{
  if(state.is3D) return;
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  const oldScale = state.baseScale * state.zoomFactor;
  const wx = (mx - state.offsetX) / oldScale;
  const wy = (my - state.offsetY) / oldScale;

  const factor = 1.12;
  if (e.deltaY < 0) state.zoomFactor = Math.min(state.zoomFactor * factor, 24);
  else state.zoomFactor = Math.max(state.zoomFactor / factor, 0.05);

  const newScale = state.baseScale * state.zoomFactor;
  state.offsetX = mx - wx * newScale;
  state.offsetY = my - wy * newScale;

  draw2D();
},{passive:false});

/* =========================
  CANVAS SIZE
========================= */
function resizeCanvas(){
  const r = viewport.getBoundingClientRect();
  canvas.width = Math.max(10, Math.floor(r.width));
  canvas.height = Math.max(10, Math.floor(r.height));
  compute(true);
  if (state.is3D) update3DFromState();
  else draw2D();
}
window.addEventListener("resize", resizeCanvas);

/* =========================
  INPUTS
========================= */
function parsePlotPolygon(){
  const plotInput = document.getElementById("plotVertices") || document.getElementById("parcelVerticesInput");
  const text = (plotInput?.value || "").trim();
  if(!text) return null;

  const pts=[];
  for(const line of text.split("\n")){
    const parts=line.split(",");
    if(parts.length<2) continue;
    const x=parseFloat(parts[0]);
    const y=parseFloat(parts[1]);
    if(Number.isFinite(x)&&Number.isFinite(y)) pts.push({x,y});
  }
  if(pts.length<3) return null;

  let minX=pts[0].x, minY=pts[0].y;
  pts.forEach(p=>{ minX=Math.min(minX,p.x); minY=Math.min(minY,p.y); });
  return pts.map(p=>({ x:p.x-minX, y:p.y-minY }));
}

function setPlotVerticesText(text) {
  const plotInput = document.getElementById("plotVertices");
  const parcelInput = document.getElementById("parcelVerticesInput");
  if (plotInput && plotInput.value !== text) {
    plotInput.value = text;
  }
  if (parcelInput && parcelInput.value !== text) {
    parcelInput.value = text;
  }
}

function readMpzpInputs() {
  const bio = parseFloat(document.getElementById("bioAreaReq")?.value);
  const cov = parseFloat(document.getElementById("coverageMaxReq")?.value);
  const mh  = parseFloat(document.getElementById("maxHeightReq")?.value);

  state.bioAreaReqPercent = Number.isFinite(bio) ? bio : 30;
  state.coverageMaxReqPercent = Number.isFinite(cov) ? cov : 30;
  state.maxHeightReqM = Number.isFinite(mh) ? mh : 12;

  state.roofType = document.getElementById("roofTypeReq")?.value || "flat";

  const sCov = state.rulesState?.mpzp?.["MPZP_COVERAGE_MAX"];
  const sPbc = state.rulesState?.mpzp?.["MPZP_PBC_MIN"];

  if (sCov) {
    if (!sCov.params) sCov.params = {};
    sCov.params.coverageMaxPercent = state.coverageMaxReqPercent;
  }
  if (sPbc) {
    if (!sPbc.params) sPbc.params = {};
    sPbc.params.pbcMinPercent = state.bioAreaReqPercent;
  }
}

/* =========================
  GEOMETRY HELPERS
========================= */
function polygonPerimeter(poly){
  if(!poly || poly.length<2) return 0;
  let per=0;
  for(let i=0;i<poly.length;i++){
    const a=poly[i];
    const b=poly[(i+1)%poly.length];
    per += Math.hypot(b.x-a.x, b.y-a.y);
  }
  return per;
}
function worldToCanvas(x,y,scale){
  return { x: state.offsetX + x*scale, y: state.offsetY + y*scale };
}
function niceGridStepMeters(ppm){
  const targetPx=48;
  const steps=[0.05,0.1,0.2,0.5,1,2,5,10,20,50,100];
  let best=steps[0], bestDiff=Infinity;
  for(const s of steps){
    const diff=Math.abs(s*ppm-targetPx);
    if(diff<bestDiff){ bestDiff=diff; best=s; }
  }
  return best;
}
function drawGrid(scale){
  const stepMinor = niceGridStepMeters(scale);
  const stepMajor = stepMinor*5;

  const minX_m = (-state.offsetX)/scale;
  const minY_m = (-state.offsetY)/scale;
  const maxX_m = (canvas.width - state.offsetX)/scale;
  const maxY_m = (canvas.height - state.offsetY)/scale;

  const startMinorX = Math.floor(minX_m/stepMinor)*stepMinor;
  const startMinorY = Math.floor(minY_m/stepMinor)*stepMinor;

  ctx.save();
  ctx.strokeStyle="rgba(148,163,184,0.30)";
  ctx.lineWidth=1;

  for(let x=startMinorX; x<=maxX_m; x+=stepMinor){
    const cx=state.offsetX + x*scale;
    ctx.beginPath(); ctx.moveTo(cx,0); ctx.lineTo(cx,canvas.height); ctx.stroke();
  }
  for(let y=startMinorY; y<=maxY_m; y+=stepMinor){
    const cy=state.offsetY + y*scale;
    ctx.beginPath(); ctx.moveTo(0,cy); ctx.lineTo(canvas.width,cy); ctx.stroke();
  }

  ctx.strokeStyle="rgba(100,116,139,0.45)";
  ctx.lineWidth=1.2;

  const startMajorX = Math.floor(minX_m/stepMajor)*stepMajor;
  const startMajorY = Math.floor(minY_m/stepMajor)*stepMajor;

  for(let x=startMajorX; x<=maxX_m; x+=stepMajor){
    const cx=state.offsetX + x*scale;
    ctx.beginPath(); ctx.moveTo(cx,0); ctx.lineTo(cx,canvas.height); ctx.stroke();
  }
  for(let y=startMajorY; y<=maxY_m; y+=stepMajor){
    const cy=state.offsetY + y*scale;
    ctx.beginPath(); ctx.moveTo(0,cy); ctx.lineTo(canvas.width,cy); ctx.stroke();
  }
  ctx.restore();
}

function updateScaleWidget(scale){
  const metersPerPixel = 1/scale;
  const targetPx = 120;
  const steps=[0.1,0.2,0.5,1,2,5,10,20,50,100,200];
  let bestM=steps[0], bestDiff=Infinity;
  for(const m of steps){
    const diff=Math.abs(m*scale-targetPx);
    if(diff<bestDiff){ bestDiff=diff; bestM=m; }
  }
  const pxLen = Math.max(50, Math.min(220, bestM*scale));
  scaleBar.style.width = `${pxLen}px`;
  scaleLabel.textContent = `${bestM} m`;
  scaleSubLabel.textContent = `100 px ≈ ${(100*metersPerPixel).toFixed(2)} m · zoom ${state.zoomFactor.toFixed(2)}×`;
}

function drawPlot(scale){
  if(!state.plotPolygon || state.plotPolygon.length<3) return;

  ctx.strokeStyle="#f97316";
  ctx.lineWidth=2;
  ctx.setLineDash([10,6]);
  ctx.beginPath();
  state.plotPolygon.forEach((p,i)=>{
    const c=worldToCanvas(p.x,p.y,scale);
    if(i===0) ctx.moveTo(c.x,c.y);
    else ctx.lineTo(c.x,c.y);
  });
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle="#f97316";
  ctx.font="bold 14px Arial";
  state.plotPolygon.forEach((p,i)=>{
    const c=worldToCanvas(p.x,p.y,scale);
    const letter = String.fromCharCode(65 + (i%26));
    ctx.fillText(letter, c.x+4, c.y-4);
  });
}

function drawEnvelope(scale){
  if(!state.envelopeWT || state.envelopeWT.length<3) return;

  ctx.save();
  ctx.strokeStyle="rgba(59,130,246,0.90)";
  ctx.lineWidth=2;
  ctx.setLineDash([6,6]);
  ctx.beginPath();
  state.envelopeWT.forEach((p,i)=>{
    const c=worldToCanvas(p.x,p.y,scale);
    if(i===0) ctx.moveTo(c.x,c.y);
    else ctx.lineTo(c.x,c.y);
  });
  ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

function clamp(v,a,b){ return Math.max(a, Math.min(b, v)); }

function getPlotBounds(points) {
  if (!points?.length) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  points.forEach(p => {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) return;
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  });
  if (!Number.isFinite(minX)) return null;
  return { minX, minY, maxX, maxY };
}

function getCadBoundsScaled() {
  if (!state.cadMap?.bbox) return null;
  const m = Number.isFinite(state.cadScaleMultiplier) ? state.cadScaleMultiplier : 1;
  return {
    minX: state.cadMap.bbox.minX * m,
    minY: state.cadMap.bbox.minY * m,
    maxX: state.cadMap.bbox.maxX * m,
    maxY: state.cadMap.bbox.maxY * m,
  };
}

function fitViewToBounds(bounds, skipResetZoom = false) {
  if (!bounds) return false;
  const w = bounds.maxX - bounds.minX;
  const h = bounds.maxY - bounds.minY;
  const margin = 40;
  const usableW = canvas.width - 2 * margin;
  const usableH = canvas.height - 2 * margin;
  state.baseScale = Math.min(usableW / Math.max(1e-6, w), usableH / Math.max(1e-6, h));

  if (!skipResetZoom) {
    state.zoomFactor = 1;
    const s = state.baseScale;
    state.offsetX = (canvas.width - w * s) / 2 - bounds.minX * s;
    state.offsetY = (canvas.height - h * s) / 2 - bounds.minY * s;
  }
  return true;
}

/* =========================
  MAP IMPORT (DWG/DXF)
========================= */
function setMapStatus(level, message) {
  state.mapImportStatus = { level, message };
  if (!mapImportStatus) return;
  mapImportStatus.textContent = message;
  mapImportStatus.classList.remove("ok", "warn", "bad", "info");
  if (level === "ok") mapImportStatus.classList.add("ok");
  if (level === "warn") mapImportStatus.classList.add("warn");
  if (level === "bad") mapImportStatus.classList.add("bad");
  if (level === "info") mapImportStatus.classList.add("info");
}

function classifyLayer(layerName = "") {
  const name = layerName.toLowerCase();
  if (/(granica|dzialk|działk|boundary|plot|parcel)/.test(name)) return "plot";
  if (/(droga|road|street)/.test(name)) return "road";
  if (/(budynek|building|neighbor|sasiad|sąsiad)/.test(name)) return "building";
  if (/(woda|water|hydrant)/.test(name)) return "water";
  if (/(gaz|gas)/.test(name)) return "gas";
  if (/(prad|prąd|electric|power|elek)/.test(name)) return "power";
  if (/(kanal|kanaliz|sewer|sanit)/.test(name)) return "sewer";
  if (/(teren|height|elev|contour|rzędn)/.test(name)) return "terrain";
  return "other";
}

function parseDxfText(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const entities = [];
  let currentSection = null;
  let awaitingSectionName = false;
  let currentEntity = null;
  let currentPolyline = null;

  const finalizeEntity = () => {
    if (!currentEntity) return;
    if (currentEntity.type === "VERTEX") {
      if (currentPolyline && currentEntity.point) {
        currentPolyline.points.push(currentEntity.point);
      }
    } else if (currentEntity.type !== "SEQEND") {
      entities.push(currentEntity);
    }
    currentEntity = null;
  };

  for (let i = 0; i < lines.length - 1; i += 2) {
    const code = lines[i].trim();
    const value = lines[i + 1]?.trim() ?? "";

    if (code === "0") {
      if (value === "SECTION") {
        finalizeEntity();
        awaitingSectionName = true;
        continue;
      }
      if (value === "ENDSEC") {
        finalizeEntity();
        if (currentPolyline) {
          entities.push(currentPolyline);
          currentPolyline = null;
        }
        currentSection = null;
        continue;
      }
      if (value === "EOF") break;

      if (currentSection !== "ENTITIES") {
        continue;
      }

      finalizeEntity();

      if (value === "SEQEND") {
        if (currentPolyline) {
          entities.push(currentPolyline);
          currentPolyline = null;
        }
        continue;
      }

      if (value === "VERTEX" && currentPolyline) {
        currentEntity = { type: "VERTEX", layer: currentPolyline.layer || "", point: null };
        continue;
      }

      if (["LWPOLYLINE", "POLYLINE", "LINE", "POINT"].includes(value)) {
        const base = { type: value, layer: "", points: [], closed: false };
        currentEntity = base;
        if (value === "POLYLINE") currentPolyline = base;
      }
      continue;
    }

    if (code === "2" && awaitingSectionName) {
      currentSection = value;
      awaitingSectionName = false;
      continue;
    }

    if (currentSection !== "ENTITIES" || !currentEntity) continue;

    if (code === "8") {
      currentEntity.layer = value || currentEntity.layer;
      if (currentPolyline && currentPolyline.layer === "" && currentEntity.type === "POLYLINE") {
        currentPolyline.layer = value;
      }
      continue;
    }

    if (currentEntity.type === "LWPOLYLINE") {
      if (code === "70") {
        currentEntity.closed = (parseInt(value, 10) & 1) === 1;
      }
      if (code === "10") {
        currentEntity.points.push({ x: parseFloat(value), y: 0, z: 0 });
      }
      if (code === "20") {
        const last = currentEntity.points[currentEntity.points.length - 1];
        if (last) last.y = parseFloat(value);
      }
      if (code === "30") {
        const last = currentEntity.points[currentEntity.points.length - 1];
        if (last) last.z = parseFloat(value);
      }
    }

    if (currentEntity.type === "POLYLINE" && code === "70") {
      currentEntity.closed = (parseInt(value, 10) & 1) === 1;
    }

    if (currentEntity.type === "LINE") {
      if (code === "10") currentEntity.start = { x: parseFloat(value), y: 0, z: 0 };
      if (code === "20" && currentEntity.start) currentEntity.start.y = parseFloat(value);
      if (code === "30" && currentEntity.start) currentEntity.start.z = parseFloat(value);
      if (code === "11") currentEntity.end = { x: parseFloat(value), y: 0, z: 0 };
      if (code === "21" && currentEntity.end) currentEntity.end.y = parseFloat(value);
      if (code === "31" && currentEntity.end) currentEntity.end.z = parseFloat(value);
    }

    if (currentEntity.type === "POINT") {
      if (code === "10") currentEntity.point = { x: parseFloat(value), y: 0, z: 0 };
      if (code === "20" && currentEntity.point) currentEntity.point.y = parseFloat(value);
      if (code === "30" && currentEntity.point) currentEntity.point.z = parseFloat(value);
    }

    if (currentEntity.type === "VERTEX") {
      if (code === "10") currentEntity.point = { x: parseFloat(value), y: 0, z: 0 };
      if (code === "20" && currentEntity.point) currentEntity.point.y = parseFloat(value);
      if (code === "30" && currentEntity.point) currentEntity.point.z = parseFloat(value);
    }
  }

  finalizeEntity();
  if (currentPolyline) entities.push(currentPolyline);

  return entities;
}

function computeBounds(points) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  points.forEach(p => {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) return;
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  });
  if (!Number.isFinite(minX)) {
    return null;
  }
  return { minX, minY, maxX, maxY };
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
      const area = Math.abs(polygonAreaAbs(points));
      if (area > bestArea) {
        bestArea = area;
        best = points;
      }
    });
    return best;
  }
  return null;
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

function buildMapDataFromPlotImport(details) {
  const candidates = details?.candidates || [];
  const selected = details?.selectedBoundary || candidates[0] || null;
  const boundaries = candidates
    .map((candidate) => {
      const points = geojsonToPoints(candidate.geometry);
      if (!points || points.length < 3) return null;
      return {
        id: candidate.id,
        layer: candidate.metadata?.layer || "plot",
        points,
        metadata: candidate.metadata || {},
      };
    })
    .filter(Boolean);

  const plotBoundary = boundaries.find((boundary) => boundary.id === selected?.id) || boundaries[0] || null;
  const bounds = details?.bbox || computeBounds(boundaries.flatMap((boundary) => boundary.points));

  return {
    plotBoundary,
    plotBoundaries: boundaries,
    layerCounts: {},
    bounds,
  };
}

function scalePoints(points, multiplier) {
  return points.map((point) => ({ x: point.x * multiplier, y: point.y * multiplier }));
}

function scaleMapData(mapData, multiplier) {
  if (!mapData) return null;
  const plotBoundaries = mapData.plotBoundaries?.map((boundary) => ({
    ...boundary,
    points: scalePoints(boundary.points, multiplier),
  })) || [];
  const plotBoundary = mapData.plotBoundary
    ? {
        ...mapData.plotBoundary,
        points: scalePoints(mapData.plotBoundary.points, multiplier),
      }
    : null;
  const bounds = mapData.bounds
    ? {
        minX: mapData.bounds.minX * multiplier,
        minY: mapData.bounds.minY * multiplier,
        maxX: mapData.bounds.maxX * multiplier,
        maxY: mapData.bounds.maxY * multiplier,
      }
    : null;
  return {
    ...mapData,
    plotBoundary,
    plotBoundaries,
    bounds,
  };
}

function buildMapData(entities) {
  const layerCounts = {};
  const polylines = [];
  const lines = [];
  const points = [];

  entities.forEach(entity => {
    const layer = entity.layer || "0";
    layerCounts[layer] = (layerCounts[layer] || 0) + 1;

    if (entity.type === "LINE" && entity.start && entity.end) {
      lines.push({ layer, points: [entity.start, entity.end] });
    }
    if ((entity.type === "LWPOLYLINE" || entity.type === "POLYLINE") && entity.points?.length >= 2) {
      polylines.push({ layer, points: entity.points, closed: !!entity.closed });
    }
    if (entity.type === "POINT" && entity.point) {
      points.push({ layer, point: entity.point });
    }
  });

  const classify = (layer) => classifyLayer(layer || "");

  const closedPolylines = polylines.filter(poly => poly.closed);
  const plotBoundaries = closedPolylines.filter(poly => classify(poly.layer) === "plot");

  const candidateBoundaries = plotBoundaries.length ? plotBoundaries : closedPolylines;

  let plotCandidate = null;
  let plotArea = 0;
  candidateBoundaries.forEach(poly => {
    const area = Math.abs(polygonAreaAbs(poly.points));
    if (area > plotArea) {
      plotCandidate = poly;
      plotArea = area;
    }
  });

  const allPoints = [
    ...polylines.flatMap(p => p.points),
    ...lines.flatMap(l => l.points),
    ...points.map(p => p.point)
  ].filter(Boolean);

  const bounds = computeBounds(allPoints);

  return {
    plotBoundary: plotCandidate,
    plotBoundaries: candidateBoundaries,
    layerCounts,
    bounds
  };
}

function renderMapLayerSummary(mapData) {
  if (!mapLayerSummary) return;
  if (!mapData) {
    mapLayerSummary.textContent = "—";
    return;
  }
  const layers = Object.entries(mapData.layerCounts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([name, count]) => `<div class="muted">• ${escapeHtml(name)} — ${count}</div>`)
    .join("");
  mapLayerSummary.innerHTML = layers || "<div class=\"muted\">Brak warstw.</div>";
}

function renderMapSummary() {
  if (!mapSummaryContent) return;
  if (!state.mapData && !state.cadMap) {
    mapSummaryContent.textContent = "Brak mapy.";
    return;
  }

  const boundaryCount = state.mapData?.plotBoundaries?.length || 0;
  const cadBoundaryCount = state.cadMap?.parcelBoundaryCount
    ?? state.cadMap?.parcelBoundaries?.length
    ?? 0;
  const cadSources = state.cadMap?.parcelSourceLayers || [];
  const plotImport = state.plotImport;
  const plotMeta = plotImport?.selectedMeta || null;
  const plotArea = plotMeta?.area ? `${plotMeta.area.toFixed(2)} m²` : "—";
  const plotLayer = plotMeta?.layer || "—";
  const plotUnits = plotImport?.units || "—";
  const plotScale = Number.isFinite(plotImport?.unitScale) ? plotImport.unitScale.toFixed(4) : "—";
  const plotConfidence = Number.isFinite(plotImport?.confidence)
    ? `${Math.round(plotImport.confidence * 100)}%`
    : "—";

  mapSummaryContent.innerHTML = `
    <div><b>Granice działek:</b> ${boundaryCount || "brak"}</div>
    <div><b>Granice z CAD:</b> ${cadBoundaryCount || "brak"}</div>
    <div><b>Warstwy źródłowe:</b> ${cadSources.length ? cadSources.join(", ") : "brak"}</div>
    <div><b>Warstwa granicy:</b> ${plotLayer}</div>
    <div><b>Powierzchnia granicy:</b> ${plotArea}</div>
    <div><b>Jednostka:</b> ${plotUnits}</div>
    <div><b>Skala → m:</b> ${plotScale}</div>
    <div><b>Pewność:</b> ${plotConfidence}</div>
    <div class="muted">Mapa CAD jest warstwą podglądu (bez edycji).</div>
  `;
}

function applyMapDataToProject(mapData) {
  if (!mapData) return;
  state.mapData = mapData;
  renderMapSummary();

  compute(false);
  if (state.is3D) update3DFromState();
  else draw2D();
}

window.addEventListener("plot-imported", (event) => {
  const details = event.detail;
  if (!details) return;
  const mapData = buildMapDataFromPlotImport(details);
  const selectedMeta = details.selectedBoundary?.metadata
    || details.candidates?.[0]?.metadata
    || null;
  state.plotImport = {
    units: details.importJob?.units,
    unitScale: details.importJob?.unitScale,
    confidence: details.importJob?.confidence,
    selectedMeta,
    originalMapData: mapData,
    scaleMultiplier: 1,
  };
  if (details.cadMap) {
    state.cadMap = details.cadMap;
    state.cadScaleMultiplier = 1;
  }
  applyMapDataToProject(mapData);
});

window.addEventListener("plot-cleared", () => {
  state.mapData = null;
  state.plotImport = null;
  state.cadMap = null;
  renderMapSummary();

  compute(false);
  if (state.is3D) update3DFromState();
  else draw2D();
});

window.addEventListener("plot-scale-adjusted", (event) => {
  const multiplier = event.detail?.multiplier;
  if (!Number.isFinite(multiplier) || multiplier <= 0) return;
  if (!state.plotImport?.originalMapData) return;
  state.plotImport.scaleMultiplier = multiplier;
  state.cadScaleMultiplier = multiplier;

  const scaledMapData = scaleMapData(state.plotImport.originalMapData, multiplier);
  const selectedMeta = state.plotImport.selectedMeta;
  if (selectedMeta?.area) {
    state.plotImport.selectedMeta = {
      ...selectedMeta,
      area: selectedMeta.area * multiplier * multiplier,
    };
  }
  applyMapDataToProject(scaledMapData);
});

function drawPolyline(points, scale, closePath = false) {
  if (!points || points.length < 2) return;
  ctx.beginPath();
  points.forEach((p, i) => {
    const c = worldToCanvas(p.x, p.y, scale);
    if (i === 0) ctx.moveTo(c.x, c.y);
    else ctx.lineTo(c.x, c.y);
  });
  if (closePath) ctx.closePath();
}

function drawMapLayers(scale) {
  if (state.mapData) {
    const { plotBoundaries } = state.mapData;

    ctx.save();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(249,115,22,0.9)";

    plotBoundaries?.forEach(boundary => {
      drawPolyline(boundary.points, scale, true);
      ctx.stroke();
    });

    const mainBoundary = state.mapData.plotBoundary;
    if (mainBoundary?.points?.length) {
      const centroid = mainBoundary.points.reduce((acc, point) => {
        acc.x += point.x;
        acc.y += point.y;
        return acc;
      }, { x: 0, y: 0 });
      centroid.x /= mainBoundary.points.length;
      centroid.y /= mainBoundary.points.length;
      const labelPos = worldToCanvas(centroid.x, centroid.y, scale);
      ctx.fillStyle = "rgba(249,115,22,0.95)";
      ctx.font = "bold 12px Arial";
      ctx.fillText("Granica działki", labelPos.x + 6, labelPos.y - 6);
    }

    ctx.restore();
  }

}

/* =========================
  COMPUTE
========================= */
function compute(skipResetZoom=false){
  readMpzpInputs();

  state.plotPolygon = parsePlotPolygon();
  if(!state.plotPolygon){
    state.plotArea = 0;
    state.envelopeWT = null;
    state.envelopeArea = 0;
    state.buildingPolygon = null;
    state.buildingArea = 0;
    state.chosenVariantName = "—";
    if (analysisContent) analysisContent.textContent = "Brak obrysu działki.";
  } else {
    state.plotArea = polygonAreaAbs(state.plotPolygon);
  }

  const plotBounds = getPlotBounds(state.plotPolygon);
  const mapBounds = state.mapData?.bounds || getCadBoundsScaled() || null;
  fitViewToBounds(plotBounds || mapBounds, skipResetZoom);

  if (!state.plotPolygon) {
    renderAnalysis();
    renderWT12Panel();
    renderMPZPPanel();
    renderMPZPModalPanel();
    return;
  }

  // ✅ WT params (zawsze z fallbackiem)
  const outWT = applyWT({
    rulebookWT: wtRules,
    rulesStateWT: state.rulesState.wt
  });
  state.wtParams = outWT?.params || { distWithOpeningsM: 4, distWithoutOpeningsM: 3 };

  // minimal envelope from min(WT)
  const minSetback = Math.min(
    Number(state.wtParams.distWithOpeningsM) || 4,
    Number(state.wtParams.distWithoutOpeningsM) || 3
  );

  let envelope = null;
  try {
    envelope = variableInsetLotPolygon(
      state.plotPolygon,
      Array(state.plotPolygon.length).fill(minSetback),
      { resolution: 0.25, simplifyEps: 0.35 }
    );
    if (!envelope || envelope.length < 3) envelope = null;
  } catch (e) {
    console.error("WT envelope error:", e);
    envelope = null;
  }

  state.envelopeWT = envelope;
  state.envelopeArea = envelope ? polygonAreaAbs(envelope) : 0;

  // ✅ MPZP/WZ limits (zawsze {limits:{maxFootprintArea}})
  const mpzpOut = applyMpzpWzLimits({
    plotArea: state.plotArea,
    rulebookMPZP: mpzpRules,
    rulesStateMPZP: state.rulesState.mpzp
  });

  const maxFootprintArea = mpzpOut?.limits?.maxFootprintArea ?? Infinity;

  state.lastLimits = {
    maxFootprintArea,
    minPbcPercent: state.bioAreaReqPercent,
    maxHeightM: state.maxHeightReqM
  };

  state.lastExplain = [
    ...(outWT?.explain || []),
    ...(mpzpOut?.explain || [])
  ];
  state.lastGeneratorExplain = [];

  state.buildingEdgeOpenings = null;
  state.buildingEdgeMinDistances = null;

  let bestPoly = null;
  let bestArea = 0;
  let bestName = "—";

  if (envelope && envelope.length >= 3) {
    const gen = generateBuildingVariants({
      envelope,
      plotPolygon: state.plotPolygon,
      limits: { maxFootprintArea },
      wtParams: state.wtParams,
      edgeOpeningsMode: "all_openings", // MVP safe
      objective: "max_area"
    });

    state.lastGeneratorExplain = gen.explain || [];

    if (gen.best?.poly) {
      bestPoly = gen.best.poly;
      bestArea = gen.best.area;
      bestName = gen.best.name;

      state.buildingEdgeOpenings = gen.best.meta?.edgeOpenings || null;
      state.buildingEdgeMinDistances = gen.best.meta?.wtMinDistances || null;
    } else {
      // fallback: pokaż envelope jako „największy możliwy”
      bestPoly = envelope;
      bestArea = polygonAreaAbs(envelope);
      bestName = "Fallback: envelope";
      state.lastGeneratorExplain.push({ summary: "Fallback: generator nie zwrócił best → pokazuję envelope." });
    }
  }

  state.buildingPolygon = bestPoly;
  state.buildingArea = bestArea;
  state.chosenVariantName = bestName;

  state.bioAreaActual = Math.max(0, state.plotArea - state.buildingArea);
  state.bioAreaActualPercent = state.plotArea > 0 ? (state.bioAreaActual / state.plotArea) * 100 : 0;

  state.heightTotalM = Math.max(3, state.maxHeightReqM);

  renderAnalysis();
  renderWT12Panel();
  renderMPZPPanel();
  renderMPZPModalPanel();
}

/* =========================
  ANALYSIS + COST (minimal)
========================= */
function escapeHtml(s){
  return String(s)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

function renderAnalysis(){
  if (!analysisContent) return;
  if(!state.plotPolygon){
    analysisContent.textContent="—";
    return;
  }

  const maxArea = state.lastLimits?.maxFootprintArea ?? Infinity;
  const covOk = state.buildingArea <= maxArea + 1e-6;

  const pbcMin = state.bioAreaReqPercent ?? 30;
  const pbcOk = state.bioAreaActualPercent + 1e-6 >= pbcMin;

  const explainLines = (state.lastExplain || [])
    .map(e => `<div class="muted">• ${escapeHtml(e.summary)}</div>`)
    .join("");

  const genLines = (state.lastGeneratorExplain || [])
    .map(e => `<div class="muted">• ${escapeHtml(e.summary)}</div>`)
    .join("");

  analysisContent.innerHTML = `
    <div><b>Działka:</b> ${state.plotArea.toFixed(2)} m²</div>
    <div><b>Envelope (min WT):</b> ${state.envelopeArea.toFixed(2)} m²</div>
    <div><b>Wariant:</b> ${escapeHtml(state.chosenVariantName)}</div>

    <div style="height:8px"></div>
    <div><b>Pow. zabudowy:</b> ${state.buildingArea.toFixed(2)} m² (max ${Number.isFinite(maxArea) ? maxArea.toFixed(2) : "∞"} m²)
      → <b class="${covOk ? "ok" : "bad"}">${covOk ? "OK" : "NIE OK"}</b>
    </div>

    <div><b>PBC:</b> ${state.bioAreaActual.toFixed(2)} m² (${state.bioAreaActualPercent.toFixed(2)}%) min ${pbcMin.toFixed(0)}%
      → <b class="${pbcOk ? "ok" : "bad"}">${pbcOk ? "OK" : "NIE OK"}</b>
    </div>

    <div><b>Wysokość:</b> ${state.heightTotalM.toFixed(2)} / ${state.maxHeightReqM.toFixed(2)} m</div>

    <div style="height:10px"></div>
    <div><b>Wyjaśnienia (Rules):</b></div>
    ${explainLines || `<div class="muted">Brak</div>`}

    <div style="height:10px"></div>
    <div><b>Wyjaśnienia (Generator):</b></div>
    ${genLines || `<div class="muted">Brak</div>`}
  `;
}

/* =========================
  DRAW 2D
========================= */
function draw2D(){
  if(state.is3D) return;

  ctx.clearRect(0,0,canvas.width,canvas.height);
  const hasMap = !!state.mapData?.bounds || !!state.cadMap?.bbox;
  const hasPlot = !!(state.plotPolygon && state.plotPolygon.length >= 3);
  const hasGeometry = hasMap || hasPlot;

  if (!hasGeometry) {
    emptyState?.classList.add("hidden");
    viewHud?.classList.add("hidden");
    scaleWidget?.classList.remove("hidden");
    const scale = state.baseScale * state.zoomFactor;
    drawGrid(scale);
    return;
  }

  emptyState?.classList.add("hidden");
  viewHud?.classList.remove("hidden");
  scaleWidget?.classList.remove("hidden");

  const scale = state.baseScale * state.zoomFactor;

  drawGrid(scale);
  const cadScale = Number.isFinite(state.cadScaleMultiplier) ? state.cadScaleMultiplier : 1;
  drawCadMap(ctx, state.cadMap, worldToCanvas, scale, canvas, cadScale);
  drawMapLayers(scale);
  drawPlot(scale);
  drawEnvelope(scale);

  if(state.buildingPolygon && state.buildingPolygon.length>=3){
    ctx.save();
    ctx.fillStyle="rgba(17,24,39,0.06)";
    ctx.strokeStyle="#111827";
    ctx.lineWidth=3;

    ctx.beginPath();
    state.buildingPolygon.forEach((p,i)=>{
      const c=worldToCanvas(p.x,p.y,scale);
      if(i===0) ctx.moveTo(c.x,c.y);
      else ctx.lineTo(c.x,c.y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  if (hasPlot) {
    viewHud.innerHTML = `
      <span class="label">TRYB</span><span class="value">PZT</span>
      <span class="label">ZABUD.</span><span class="value">${state.buildingArea.toFixed(1)} m²</span>
      <span class="label">PBC</span><span class="value">${state.bioAreaActualPercent.toFixed(1)}%</span>
      <span class="label">H</span><span class="value">${state.heightTotalM.toFixed(2)} / ${state.maxHeightReqM.toFixed(2)} m</span>
    `;
  } else {
    viewHud.innerHTML = `
      <span class="label">TRYB</span><span class="value">PZT</span>
      <span class="label">MAPA</span><span class="value">granice działek</span>
    `;
  }

  updateScaleWidget(scale);
}

/* =========================
  RECALC helper
========================= */
function generateAfterRuleChange() {
  compute(true);
  if (state.is3D) update3DFromState();
  else draw2D();
}

/* =========================
  BUTTONS: ZAPISZ
========================= */
document.getElementById("applyParcelVerticesBtn")?.addEventListener("click", ()=>{
  compute(false);
  if(state.is3D) update3DFromState();
  else draw2D();
});

document.getElementById("openNewProjectFlowBtn")?.addEventListener("click", () => {
  setNewProjectMode("editor");
  switchNewProjectStep("name");
  const nameInput = document.getElementById("newProjectNameInput");
  if (nameInput) {
    window.setTimeout(() => nameInput.focus(), 0);
  }
});


function getNewProjectMeta() {
  const nameInput = document.getElementById("newProjectNameInput");
  const title = (nameInput?.value || "").trim();
  return {
    nameInput,
    title,
    isTitleValid: /^([\p{L}\d ]{1,20})$/u.test(title),
  };
}

document.getElementById("saveNewProjectBtn")?.addEventListener("click", async () => {
  const meta = getNewProjectMeta();
  if (!meta.title || !meta.isTitleValid) {
    switchNewProjectStep("name");
    if (!meta.title || !meta.isTitleValid) meta.nameInput?.focus();
    window.dispatchEvent(new CustomEvent("topbar:notify", {
      detail: { variant: "error", message: "Uzupełnij formularz: poprawna nazwa projektu." },
    }));
    return;
  }

  let project;
  try {
    const created = await apiCreateProject({ name: meta.title, description: "" });
    project = { id: `api-${created.id}`, apiId: created.id, name: meta.title };
  } catch (_err) {
    window.dispatchEvent(new CustomEvent("topbar:notify", {
      detail: { variant: "error", message: "Nie udało się utworzyć projektu. Sprawdź sesję i spróbuj ponownie." },
    }));
    return;
  }

  saveProjectToCollection(project);
  applyProjectToWorkspace(project);

  window.dispatchEvent(new CustomEvent("topbar:notify", {
    detail: { variant: "success", message: `Utworzono projekt: ${meta.title}` },
  }));
});

document.querySelectorAll("#workspace input[id], #workspace select[id], #workspace textarea[id]").forEach((control) => {
  if (control.closest("#newProjectPage")) return;
  if (control.type === "file") return;
  control.addEventListener("input", schedulePersistActiveProjectWorkspace);
  control.addEventListener("change", schedulePersistActiveProjectWorkspace);
});

window.addEventListener("plot-imported", schedulePersistActiveProjectWorkspace);
window.addEventListener("plot-import-removed", schedulePersistActiveProjectWorkspace);
window.addEventListener("plot-layers-updated", schedulePersistActiveProjectWorkspace);

updateProjectLibraryCount();
syncTopbarProjects();

try {
  const cachedUser = JSON.parse(window.sessionStorage.getItem("authenticatedUser") || "null");
  const bootstrapUser = window.__BOOTSTRAP_USER__ || null;
  const userToApply = cachedUser || bootstrapUser;
  if (userToApply) {
    applyAuthenticatedUser(userToApply);
    window.sessionStorage.setItem("authenticatedUser", JSON.stringify(userToApply));
  }
} catch (_err) {
  // ignore malformed session cache
}

(async () => {
  try {
    await requireAuthenticatedUser();
    await hydrateProjectsFromApi();
  } catch (_err) {
    // Redirect handled for 401 in requireAuthenticatedUser
  }
})();

const startupParams = new URLSearchParams(window.location.search);
if (startupParams.get("open") === "projects") {
  openCreateProjectPage();
  const cleanUrl = `${window.location.pathname}${window.location.hash || ""}`;
  window.history.replaceState({}, "", cleanUrl);
}

window.addEventListener("topbar:project:selected", (event) => {
  const selectedName = event?.detail?.name;
  if (!selectedName) return;
  const selectedProject = userProjects.find((project) => project.name === selectedName);
  if (!selectedProject) return;
  applyProjectToWorkspace(selectedProject);
});

document.getElementById("applyMpzpBtn")?.addEventListener("click", ()=>{
  compute(true);
  closeModal("mpzpModal");
  if(state.is3D) update3DFromState();
  else draw2D();
  syncMpzpUiEverywhereFromRules();
});

document.getElementById("applyMapImportBtn")?.addEventListener("click", () => {
  if (state.cadImportEnabled) return;
  if (!state.mapImportDraft) {
    setMapStatus("warn", "Brak wczytanego DXF. Wybierz plik i poczekaj na analizę.");
    return;
  }
  applyMapDataToProject(state.mapImportDraft);
  closeModal("mapImportModal");
  setMapStatus("ok", "Mapa wczytana do projektu.");
});

/* =========================
  START
========================= */
window.addEventListener("load", ()=>{
  initLawTabs();
  bindWT12Panel();
  bindMPZPPanel();
  bindMPZPModalPanel();

  canvas.style.cursor="grab";

  const r = viewport.getBoundingClientRect();
  canvas.width = Math.max(10, Math.floor(r.width));
  canvas.height = Math.max(10, Math.floor(r.height));

  if (userProjects.length > 0) {
    applyProjectToWorkspace(userProjects[0]);
  } else {
    compute(false);
    draw2D();
  }

  syncMpzpUiEverywhereFromRules();
  renderWT12Panel();
  renderMapSummary();
  initCadUI({
    state,
    setStatus: setMapStatus,
    onCadMapApplied: () => {
      renderMapSummary();
      compute(true);
      if (state.is3D) update3DFromState();
      else draw2D();
    },
    onCadMapUpdated: () => {
      renderMapSummary();
      compute(true);
      if (state.is3D) update3DFromState();
      else draw2D();
    },
  });
});

/* =========================
  MAP MODULE (MapLibre + backend /api/map)
========================= */
const mapResolveBtn = document.getElementById("mapResolveBtn");
const mapExportGeoJsonBtn = document.getElementById("mapExportGeoJsonBtn");
const mapSources = document.getElementById("mapSources");
const mapWarnings = document.getElementById("mapWarnings");
let mapView = null;
let mapSessionId = null;
let mapWmsLayers = [];

function ensureMap() {
  if (mapView || !window.maplibregl) return;
  const geoportalBaseTiles = "https://mapy.geoportal.gov.pl/ArcGIS/rest/services/ORTOFOTOMAPA/MapServer/tile/{z}/{y}/{x}";
  mapView = new window.maplibregl.Map({
    container: "mapLibreContainer",
    style: {
      version: 8,
      sources: {
        "geoportal-base": {
          type: "raster",
          tiles: [geoportalBaseTiles],
          tileSize: 256,
          attribution: "© Geoportal.gov.pl",
        },
      },
      layers: [
        {
          id: "geoportal-base",
          type: "raster",
          source: "geoportal-base",
        },
      ],
    },
    center: [19.4, 52.1],
    zoom: 6,
  });
}

function addVectorLayers(sessionId) {
  const sourceId = "map-session-source";
  if (mapView.getLayer("plot")) {
    ["plot","neighbors","buildings","roads","utilities"].forEach((id)=>{ if (mapView.getLayer(id)) mapView.removeLayer(id); });
  }
  if (mapView.getSource(sourceId)) mapView.removeSource(sourceId);

  mapView.addSource(sourceId, {
    type: "vector",
    tiles: [`/api/map/tiles/{z}/{x}/{y}.mvt?sessionId=${sessionId}`],
    minzoom: 0,
    maxzoom: 22,
  });

  mapView.addLayer({ id: "plot", type: "line", source: sourceId, "source-layer": "plot", paint: { "line-color": "#ef4444", "line-width": 3 } });
  mapView.addLayer({ id: "neighbors", type: "line", source: sourceId, "source-layer": "neighbors", paint: { "line-color": "#f59e0b", "line-width": 2 } });
  mapView.addLayer({ id: "buildings", type: "fill", source: sourceId, "source-layer": "buildings", paint: { "fill-color": "#334155", "fill-opacity": 0.5 } });
  mapView.addLayer({ id: "roads", type: "line", source: sourceId, "source-layer": "roads", paint: { "line-color": "#2563eb", "line-width": 2 } });
  mapView.addLayer({ id: "utilities", type: "line", source: sourceId, "source-layer": "utilities", paint: { "line-color": "#9333ea", "line-width": 2, "line-dasharray": [2,1] } });
}

function bindLayerToggles() {
  document.querySelectorAll("[data-map-layer]").forEach((el) => {
    el.addEventListener("change", () => {
      const id = el.getAttribute("data-map-layer");
      if (id === "utilities-wms") {
        mapWmsLayers.forEach((layerId) => {
          if (mapView?.getLayer(layerId)) mapView.setLayoutProperty(layerId, "visibility", el.checked ? "visible" : "none");
        });
        return;
      }
      if (mapView?.getLayer(id)) {
        mapView.setLayoutProperty(id, "visibility", el.checked ? "visible" : "none");
      }
    });
  });
}

function addWmsOverlays(overlays) {
  mapWmsLayers.forEach((layerId) => { if (mapView.getLayer(layerId)) mapView.removeLayer(layerId); if (mapView.getSource(layerId)) mapView.removeSource(layerId); });
  mapWmsLayers = [];
  (overlays || []).forEach((overlay, idx) => {
    if (!overlay.url || !overlay.layers) return;
    const layerId = `utilities-wms-${idx}`;
    const srcUrl = `${overlay.url}?service=WMS&request=GetMap&version=1.1.1&layers=${overlay.layers}&styles=&format=image/png&transparent=true&srs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256`;
    mapView.addSource(layerId, { type: "raster", tiles: [srcUrl], tileSize: 256 });
    mapView.addLayer({ id: layerId, type: "raster", source: layerId, paint: { "raster-opacity": 0.75 } });
    mapWmsLayers.push(layerId);
  });
}

document.getElementById("openMapBtn")?.addEventListener("click", () => {
  openModal("mapModal");
  setTimeout(() => { ensureMap(); mapView?.resize(); }, 120);
});

mapResolveBtn?.addEventListener("click", async () => {
  ensureMap();
  const body = {
    nrDzialki: document.getElementById("mapNrDzialki")?.value || "",
    obreb: document.getElementById("mapObreb")?.value || "",
    miejscowosc: document.getElementById("mapMiejscowosc")?.value || "",
    bufferMeters: 30,
  };
  const res = await fetch("/api/map/parcel/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    alert("Brak dostępu do działek lub błąd providera. Przejście do trybu ręcznego.");
    return;
  }
  mapSessionId = data.sessionId;
  addVectorLayers(mapSessionId);
  addWmsOverlays(data.wmsOverlays || []);
  const [minx, miny, maxx, maxy] = data.bbox4326 || [18,50,22,54];
  mapView.fitBounds([[minx, miny], [maxx, maxy]], { padding: 30 });
  mapSources.textContent = JSON.stringify(data.sources || {}, null, 2);
  mapWarnings.textContent = (data.warnings || []).join("\n") || "Brak ostrzeżeń.";
});

mapExportGeoJsonBtn?.addEventListener("click", async () => {
  if (!mapSessionId) return;
  const res = await fetch(`/api/map/export?sessionId=${mapSessionId}&format=geojson`);
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/geo+json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `map-export-${mapSessionId}.geojson`;
  a.click();
  URL.revokeObjectURL(a.href);
});

bindLayerToggles();
