import { createIdentificationAutosave, normalizeIdentificationValue } from "./projectIdentificationAutosave.js";
import { createBoundaryEditor } from "./boundary/boundaryEditor.js";

const menuPreviewShell = document.getElementById("menuPreviewShell");
const openMenuPreviewBtn = document.getElementById("openMenuPreviewBtn");
const closeMenuPreviewBtn = document.getElementById("closeMenuPreviewBtn");
const menuTabs = document.querySelectorAll("[data-menu-tab]");
const menuPanels = document.querySelectorAll("[data-menu-panel]");
const menuMpzpOnlySections = document.querySelectorAll("[data-menu-mpzp-only-section]");
const addParcelTabBtn = document.getElementById("addParcelTabBtn");
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
const designAreaLabel = document.getElementById("designAreaLabel");
const designAreaStatusDot = document.getElementById("designAreaStatusDot");
const designAreaActions = document.getElementById("designAreaActions");
const workspaceMap = document.getElementById("workspaceMap");
const layersSearchInput = document.getElementById("layersSearchInput");
const layersPanel = document.getElementById("layersPanel");


const projectIdentificationInputs = document.querySelectorAll("[data-project-identification-field]");
const projectIdentificationStatusNodes = document.querySelectorAll("[data-project-identification-status]");
const projectIdentificationRetryButtons = document.querySelectorAll("[data-project-identification-retry]");
let projectIdentificationApiId = null;
let activeParcelTabId = null;
const conditionsByTabId = {};
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

const projectBuildingParameterInputs = document.querySelectorAll("[data-project-building-parameter-field]");
const projectBuildingParameterStatusNodes = document.querySelectorAll("[data-project-building-parameter-status]");
const projectBuildingParameterRetryButtons = document.querySelectorAll("[data-project-building-parameter-retry]");
const PROJECT_BUILDING_PARAMETER_FIELDS = [
  "max_building_height",
  "max_storeys_above",
  "max_storeys_below",
  "max_ridge_height",
  "max_eaves_height",
  "min_building_intensity",
  "max_building_intensity",
  "max_building_coverage",
  "min_biologically_active_share",
  "min_front_elevation_width",
  "max_front_elevation_width",
];
const PROJECT_BUILDING_PARAMETER_INTEGER_FIELDS = new Set(["max_storeys_above", "max_storeys_below"]);
let hideBuildingParameterSavedStateTimerId = null;

const projectRoofArchitectureInputs = document.querySelectorAll("[data-project-roof-architecture-field]");
const projectRoofArchitectureStatusNodes = document.querySelectorAll("[data-project-roof-architecture-status]");
const projectRoofArchitectureRetryButtons = document.querySelectorAll("[data-project-roof-architecture-retry]");
const PROJECT_ROOF_ARCHITECTURE_FIELDS = [
  "roof_type_allowed",
  "roof_slope_min_deg",
  "roof_slope_max_deg",
  "ridge_direction_required",
  "roof_cover_material_limits",
  "facade_roof_color_limits",
];
const PROJECT_ROOF_ARCHITECTURE_DECIMAL_FIELDS = new Set(["roof_slope_min_deg", "roof_slope_max_deg"]);
let hideRoofArchitectureSavedStateTimerId = null;

const projectParkingEnvironmentInputs = document.querySelectorAll("[data-project-parking-environment-field]");
const projectParkingEnvironmentStatusNodes = document.querySelectorAll("[data-project-parking-environment-status]");
const projectParkingEnvironmentRetryButtons = document.querySelectorAll("[data-project-parking-environment-retry]");
const PROJECT_PARKING_ENVIRONMENT_FIELDS = [
  "parking_required_info",
  "parking_spaces_per_unit",
  "parking_spaces_per_100sqm_services",
  "parking_disability_requirement",
  "conservation_protection_zone",
  "nature_protection_zone",
  "noise_emission_limits",
  "min_biologically_active_share",
];
const PROJECT_PARKING_ENVIRONMENT_DECIMAL_FIELDS = new Set([
  "parking_spaces_per_unit",
  "parking_spaces_per_100sqm_services",
  "min_biologically_active_share",
]);
let hideParkingEnvironmentSavedStateTimerId = null;

const projectLandRegisterAreaInputs = document.querySelectorAll("[data-project-land-register-area]");
const projectLandRegisterListNodes = document.querySelectorAll("[data-project-land-register-list]");
const projectLandRegisterAddButtons = document.querySelectorAll("[data-project-land-register-add]");
const projectLandRegisterStatusNodes = document.querySelectorAll("[data-project-land-register-status]");
const projectLandRegisterRetryButtons = document.querySelectorAll("[data-project-land-register-retry]");

const LAND_REGISTER_SYMBOL_MAX_LENGTH = 64;
const LAND_REGISTER_SYMBOL_PATTERN = /^[A-Za-zĄĆĘŁŃÓŚŹŻ]{1,3}(?:[IVX]{1,3}[AB]?)?$/;
let hideLandRegisterSavedStateTimerId = null;
let isApplyingLandRegister = false;
let landRegisterDebounceTimerId = null;
let landRegisterInFlight = false;
let landRegisterQueued = false;
let landRegisterPersisted = { parcel_area_total: null, land_uses: [] };
let landRegisterDraft = { parcel_area_total: "", land_uses: [] };
let landRegisterHasFailed = false;

let designArea = null;
let boundaryEditor = null;
let layerRows = [
  { id: "plot_boundary", name: "Granica działki", group: "Granice i obszary bazowe", visible: true },
  { id: "land_use_boundary", name: "Granica przeznaczenia terenu", group: "Granice i obszary bazowe", visible: true },
  { id: "site_boundary", name: "Obszar analizy", group: "Granice i obszary bazowe", visible: true },

  { id: "building_setback_line", name: "Nieprzekraczalna linia zabudowy", group: "Ograniczenia zabudowy", visible: true },
  { id: "mandatory_building_line", name: "Obowiązująca linia zabudowy", group: "Ograniczenia zabudowy", visible: true },
  { id: "offset_from_boundary_zone", name: "Strefa odsunięcia od granicy", group: "Ograniczenia zabudowy", visible: true },
  { id: "no_build_zone", name: "Strefa zakazu zabudowy", group: "Ograniczenia zabudowy", visible: true },
  { id: "limited_build_zone", name: "Strefa ograniczonej zabudowy", group: "Ograniczenia zabudowy", visible: true },

  { id: "road_edge", name: "Krawędź drogi", group: "Drogi i dostęp", visible: true },
  { id: "road_centerline", name: "Oś drogi", group: "Drogi i dostęp", visible: true },
  { id: "road_right_of_way", name: "Pas drogowy", group: "Drogi i dostęp", visible: true },
  { id: "access_point", name: "Punkt wjazdu / wejścia", group: "Drogi i dostęp", visible: true },
  { id: "driveway", name: "Dojazd", group: "Drogi i dostęp", visible: true },
  { id: "fire_access_route", name: "Droga pożarowa", group: "Drogi i dostęp", visible: true },
  { id: "parking_zone", name: "Strefa parkingu / manewrowa", group: "Drogi i dostęp", visible: true },

  { id: "elevation_point", name: "Punkt wysokościowy", group: "Teren i wysokości", visible: true },
  { id: "contour_line", name: "Warstwica", group: "Teren i wysokości", visible: true },
  { id: "terrain_break_line", name: "Linia załamania terenu", group: "Teren i wysokości", visible: true },
  { id: "slope_zone", name: "Strefa spadku", group: "Teren i wysokości", visible: true },
  { id: "embankment", name: "Nasyp", group: "Teren i wysokości", visible: true },
  { id: "cut_slope", name: "Wykop / skarpa", group: "Teren i wysokości", visible: true },
  { id: "retaining_wall", name: "Mur oporowy", group: "Teren i wysokości", visible: true },

  { id: "existing_building", name: "Istniejący budynek", group: "Istniejące obiekty", visible: true },
  { id: "adjacent_building", name: "Budynek sąsiedni", group: "Istniejące obiekty", visible: true },
  { id: "outbuilding", name: "Budynek pomocniczy", group: "Istniejące obiekty", visible: true },
  { id: "canopy_structure", name: "Wiata", group: "Istniejące obiekty", visible: true },
  { id: "fence_line", name: "Ogrodzenie", group: "Istniejące obiekty", visible: true },
  { id: "gate", name: "Brama / furtka", group: "Istniejące obiekty", visible: true },

  { id: "water_pipe", name: "Sieć wodociągowa", group: "Sieci uzbrojenia", visible: true },
  { id: "sanitary_sewer", name: "Kanalizacja sanitarna", group: "Sieci uzbrojenia", visible: true },
  { id: "storm_sewer", name: "Kanalizacja deszczowa", group: "Sieci uzbrojenia", visible: true },
  { id: "gas_pipe", name: "Gazociąg", group: "Sieci uzbrojenia", visible: true },
  { id: "power_line_underground", name: "Kabel energetyczny podziemny", group: "Sieci uzbrojenia", visible: true },
  { id: "power_line_overhead", name: "Linia energetyczna napowietrzna", group: "Sieci uzbrojenia", visible: true },
  { id: "telecom_line", name: "Sieć teletechniczna", group: "Sieci uzbrojenia", visible: true },
  { id: "utility_connection", name: "Przyłącze", group: "Sieci uzbrojenia", visible: true },
  { id: "utility_node", name: "Obiekt punktowy sieci", group: "Sieci uzbrojenia", visible: true },
  { id: "transformer_station", name: "Stacja transformatorowa", group: "Sieci uzbrojenia", visible: true },
  { id: "utility_protection_zone", name: "Strefa ochronna sieci", group: "Sieci uzbrojenia", visible: true },

  { id: "watercourse", name: "Ciek wodny", group: "Woda i odwodnienie", visible: true },
  { id: "drainage_ditch", name: "Rów odwadniający", group: "Woda i odwodnienie", visible: true },
  { id: "pond", name: "Zbiornik wodny", group: "Woda i odwodnienie", visible: true },
  { id: "flood_zone", name: "Strefa zalewowa", group: "Woda i odwodnienie", visible: true },
  { id: "soakaway_zone", name: "Strefa retencji / rozsączania", group: "Woda i odwodnienie", visible: true },

  { id: "tree", name: "Drzewo", group: "Zieleń", visible: true },
  { id: "tree_canopy", name: "Zasięg korony drzewa", group: "Zieleń", visible: true },
  { id: "root_protection_zone", name: "Strefa ochrony korzeni", group: "Zieleń", visible: true },
  { id: "shrub_area", name: "Krzewy / zieleń niska", group: "Zieleń", visible: true },
  { id: "protected_tree", name: "Drzewo chronione", group: "Zieleń", visible: true },
  { id: "biologically_active_area", name: "Powierzchnia biologicznie czynna", group: "Zieleń", visible: true },
  { id: "forest_boundary", name: "Granica lasu", group: "Zieleń", visible: true },

  { id: "conservation_zone", name: "Strefa ochrony konserwatorskiej", group: "Strefy ochronne", visible: true },
  { id: "environmental_protection_zone", name: "Strefa ochrony środowiskowej", group: "Strefy ochronne", visible: true },
  { id: "noise_impact_zone", name: "Strefa hałasu", group: "Strefy ochronne", visible: true },
  { id: "height_limit_zone", name: "Strefa ograniczenia wysokości", group: "Strefy ochronne", visible: true },
  { id: "special_restriction_zone", name: "Strefa kolejowa / drogowa / sanitarna", group: "Strefy ochronne", visible: true },
];
let layerQuery = "";
const openLayerGroups = Object.fromEntries([...new Set(layerRows.map((row) => row.group))].map((group) => [group, true]));
const VECTOR_DRAW_ACTIONS = {
  plot_boundary: "create_plot",
  land_use_boundary: "create_land_use_polygon",
  site_boundary: "create_site",
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderWorkspaceMap() {
  if (!workspaceMap) return;
  if (!boundaryEditor) {
    boundaryEditor = createBoundaryEditor({
      container: workspaceMap,
      onStateChange: ({ grouped, analysis }) => {
        const hasAnalysisScope = !!grouped.siteBoundary;
        setDesignArea(
          hasAnalysisScope
            ? { id: grouped.siteBoundary.id, name: `Obszar analizy · ${analysis.plotArea.toFixed(1)} m² działki` }
            : null
        );
      },
    });
  }
}

function setDesignArea(next) {
  const hasChanged = designArea?.id !== next?.id || designArea?.name !== next?.name;
  designArea = next;
  if (designAreaLabel) {
    designAreaLabel.textContent = designArea?.name || "Brak obszaru";
  }
  if (designAreaStatusDot) {
    designAreaStatusDot.classList.toggle("bg-red-400", !designArea);
    designAreaStatusDot.classList.toggle("bg-emerald-200", !!designArea);
  }
  if (designAreaActions) {
    designAreaActions.innerHTML = designArea
      ? `
        <div class="flex items-center gap-2">
          <button type="button" data-design-area-action="replace" class="h-9 rounded-xl bg-white px-3 text-xs font-semibold text-emerald-700 shadow hover:bg-emerald-50">Rysuj site</button>
          <button type="button" data-design-area-action="clear" class="h-9 rounded-xl border border-white/35 bg-white/15 px-3 text-xs font-semibold text-white hover:bg-white/20">Wyczyść</button>
        </div>
      `
      : `<button type="button" data-design-area-action="add" class="flex items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-[11px] font-semibold tracking-[0.04em] text-emerald-700 shadow-sm hover:bg-emerald-50"><svg viewBox="0 0 24 24" class="h-[14px] w-[14px]" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14"/><path d="M5 12h14"/></svg>DODAJ SITE</button>`;
  }
  if (hasChanged && !boundaryEditor) {
    renderWorkspaceMap();
  }
}

function renderLayers() {
  if (!layersPanel) return;
  const groups = [...new Set(layerRows.map((row) => row.group))];
  const query = layerQuery.trim().toLowerCase();
  layersPanel.innerHTML = groups
    .map((group) => {
      const list = layerRows.filter((row) => row.group === group && (!query || row.name.toLowerCase().includes(query)));
      const isOpen = openLayerGroups[group] !== false;
      return `
        <div class="space-y-1">
          <button type="button" data-layer-group="${escapeHtml(group)}" class="mx-[5px] flex w-[calc(100%-10px)] items-center justify-between rounded-2xl border border-black/30 bg-gradient-to-r from-neutral-950 via-neutral-900 to-neutral-950 px-3 py-1.5 text-white shadow-md">
            <div class="flex min-w-0 items-center gap-2">
              <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/10">
                ${isOpen ? "▾" : "▸"}
              </span>
              <span class="truncate text-[11px] font-semibold uppercase tracking-widest">${escapeHtml(group)}</span>
            </div>
            <span class="rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[11px] font-semibold">${list.length}</span>
          </button>
          ${
            isOpen
              ? `<div class="space-y-1.5">${
                  list.length
                    ? list
                        .map(
                          (row) => `
                      <div class="ml-[5px] flex w-[calc(100%-10px)] items-center justify-between rounded-2xl border border-gray-200 bg-white px-3 py-1 shadow-[0_1px_0_rgba(17,24,39,0.06)]">
                        <div class="flex min-w-0 items-center gap-2">
                          <span class="h-2 w-2 rounded-full ${row.visible ? "bg-emerald-500" : "bg-gray-300"}"></span>
                          <span class="truncate text-sm text-gray-900">${escapeHtml(row.name)}</span>
                        </div>
                        <div class="flex shrink-0 items-center gap-1">
                          ${
                            VECTOR_DRAW_ACTIONS[row.id]
                              ? `<button type="button" data-layer-draw="${row.id}" class="inline-flex h-6 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 px-2 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100" title="Rysuj wektorowo na obszarze roboczym">Rysuj</button>`
                              : ""
                          }
                          <button type="button" data-layer-toggle="${row.id}" class="flex h-6 w-6 items-center justify-center rounded-lg hover:bg-gray-100" title="${row.visible ? "Ukryj" : "Pokaż"}">${row.visible ? "👁" : "🙈"}</button>
                          <button type="button" data-layer-delete="${row.id}" class="flex h-6 w-6 items-center justify-center rounded-lg text-gray-500 hover:bg-rose-50 hover:text-rose-600" title="Usuń">🗑</button>
                        </div>
                      </div>`
                        )
                        .join("")
                    : '<div class="rounded-2xl border border-gray-200 bg-white px-3 py-2 text-xs text-gray-500">brak wyników</div>'
                }</div>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

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

function syncProjectBuildingParameterFieldInputs(sourceInput) {
  if (!sourceInput) return;
  const field = sourceInput.dataset.projectBuildingParameterField;
  if (!field) return;

  const nextValue = sourceInput.value;
  projectBuildingParameterInputs.forEach((input) => {
    if (input === sourceInput) return;
    if (input.dataset.projectBuildingParameterField !== field) return;
    if (input.value !== nextValue) input.value = nextValue;
  });
}

function normalizeProjectBuildingParameterFieldValue(field, value) {
  const normalized = normalizeIdentificationValue(value).replace(",", ".");
  if (!normalized) return "";
  if (PROJECT_BUILDING_PARAMETER_INTEGER_FIELDS.has(field)) {
    const asInt = Number.parseInt(normalized, 10);
    if (!Number.isInteger(asInt) || asInt < 0) return "";
    return String(asInt);
  }
  const asNumber = Number(normalized);
  if (!Number.isFinite(asNumber) || asNumber < 0) return "";
  if (field === "min_biologically_active_share" && asNumber > 100) return "";
  return String(asNumber);
}

function parseProjectBuildingParameterPayloadValue(field, value) {
  const normalized = normalizeProjectBuildingParameterFieldValue(field, value);
  if (!normalized) return null;
  if (PROJECT_BUILDING_PARAMETER_INTEGER_FIELDS.has(field)) {
    return Number.parseInt(normalized, 10);
  }
  return Number(normalized);
}

function applyProjectBuildingParametersToDom(data = {}) {
  isApplyingProjectIdentification = true;
  try {
    const normalized = Object.fromEntries(
      PROJECT_BUILDING_PARAMETER_FIELDS.map((key) => [key, normalizeProjectBuildingParameterFieldValue(key, data?.[key])])
    );

    projectBuildingParameterInputs.forEach((input) => {
      const field = input.dataset.projectBuildingParameterField;
      if (!field) return;
      const value = normalized[field] ?? "";
      if (input.value !== value) input.value = value;
    });
  } finally {
    isApplyingProjectIdentification = false;
  }
}

function setProjectBuildingParameterStatus(status, message = "") {
  projectBuildingParameterStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectBuildingParameterRetryButtons.forEach((button) => {
    button.classList.toggle("hidden", status !== "error");
  });
  globalThis.clearTimeout(hideBuildingParameterSavedStateTimerId);
  if (status === "saved") {
    hideBuildingParameterSavedStateTimerId = globalThis.setTimeout(() => {
      setProjectBuildingParameterStatus("idle", "");
    }, 1200);
  }
}


function syncProjectRoofArchitectureFieldInputs(sourceInput) {
  if (!sourceInput) return;
  const field = sourceInput.dataset.projectRoofArchitectureField;
  if (!field) return;

  const nextValue = sourceInput.value;
  projectRoofArchitectureInputs.forEach((input) => {
    if (input === sourceInput) return;
    if (input.dataset.projectRoofArchitectureField !== field) return;
    if (input.value !== nextValue) input.value = nextValue;
  });
}

function normalizeProjectRoofArchitectureFieldValue(field, value) {
  const normalized = normalizeIdentificationValue(value).replace(",", ".");
  if (!normalized) return "";
  if (!PROJECT_ROOF_ARCHITECTURE_DECIMAL_FIELDS.has(field)) return normalized;

  const asNumber = Number(normalized);
  if (!Number.isFinite(asNumber) || asNumber < 0 || asNumber > 90) return "";
  return String(asNumber);
}

function parseProjectRoofArchitecturePayloadValue(field, value) {
  const normalized = normalizeProjectRoofArchitectureFieldValue(field, value);
  if (!normalized) return null;
  if (PROJECT_ROOF_ARCHITECTURE_DECIMAL_FIELDS.has(field)) return Number(normalized);
  return normalized;
}

function applyProjectRoofArchitectureToDom(data = {}) {
  isApplyingProjectIdentification = true;
  try {
    const normalized = Object.fromEntries(
      PROJECT_ROOF_ARCHITECTURE_FIELDS.map((key) => [key, normalizeProjectRoofArchitectureFieldValue(key, data?.[key])])
    );

    projectRoofArchitectureInputs.forEach((input) => {
      const field = input.dataset.projectRoofArchitectureField;
      if (!field) return;
      const value = normalized[field] ?? "";
      if (input.value !== value) input.value = value;
    });
  } finally {
    isApplyingProjectIdentification = false;
  }
}

function setProjectRoofArchitectureStatus(status, message = "") {
  projectRoofArchitectureStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectRoofArchitectureRetryButtons.forEach((button) => {
    button.classList.toggle("hidden", status !== "error");
  });
  globalThis.clearTimeout(hideRoofArchitectureSavedStateTimerId);
  if (status === "saved") {
    hideRoofArchitectureSavedStateTimerId = globalThis.setTimeout(() => {
      setProjectRoofArchitectureStatus("idle", "");
    }, 1200);
  }
}


function syncProjectParkingEnvironmentFieldInputs(sourceInput) {
  if (!sourceInput) return;
  const field = sourceInput.dataset.projectParkingEnvironmentField;
  if (!field) return;

  const nextValue = sourceInput.value;
  projectParkingEnvironmentInputs.forEach((input) => {
    if (input === sourceInput) return;
    if (input.dataset.projectParkingEnvironmentField !== field) return;
    if (input.value !== nextValue) input.value = nextValue;
  });
}

function normalizeProjectParkingEnvironmentFieldValue(field, value) {
  const normalized = normalizeIdentificationValue(value).replace(",", ".");
  if (!normalized) return "";
  if (!PROJECT_PARKING_ENVIRONMENT_DECIMAL_FIELDS.has(field)) return normalized;

  const asNumber = Number(normalized);
  if (!Number.isFinite(asNumber) || asNumber < 0) return "";
  if (field === "min_biologically_active_share" && asNumber > 100) return "";
  return String(asNumber);
}

function parseProjectParkingEnvironmentPayloadValue(field, value) {
  const normalized = normalizeProjectParkingEnvironmentFieldValue(field, value);
  if (!normalized) return null;
  if (PROJECT_PARKING_ENVIRONMENT_DECIMAL_FIELDS.has(field)) return Number(normalized);
  return normalized;
}

function applyProjectParkingEnvironmentToDom(data = {}) {
  isApplyingProjectIdentification = true;
  try {
    const normalized = Object.fromEntries(
      PROJECT_PARKING_ENVIRONMENT_FIELDS.map((key) => [key, normalizeProjectParkingEnvironmentFieldValue(key, data?.[key])])
    );

    projectParkingEnvironmentInputs.forEach((input) => {
      const field = input.dataset.projectParkingEnvironmentField;
      if (!field) return;
      const value = normalized[field] ?? "";
      if (input.value !== value) input.value = value;
    });
  } finally {
    isApplyingProjectIdentification = false;
  }
}

function setProjectParkingEnvironmentStatus(status, message = "") {
  projectParkingEnvironmentStatusNodes.forEach((node) => {
    node.textContent = message;
    node.dataset.state = status;
    node.classList.toggle("text-red-600", status === "error");
    node.classList.toggle("text-emerald-700", status === "saved");
    node.classList.toggle("text-zinc-500", status !== "error" && status !== "saved");
  });
  projectParkingEnvironmentRetryButtons.forEach((button) => {
    button.classList.toggle("hidden", status !== "error");
  });

  globalThis.clearTimeout(hideParkingEnvironmentSavedStateTimerId);
  if (status === "saved") {
    hideParkingEnvironmentSavedStateTimerId = globalThis.setTimeout(() => {
      setProjectParkingEnvironmentStatus("idle", "");
    }, 1200);
  }
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

function normalizeLandUseSymbol(value) {
  const normalized = normalizeIdentificationValue(value).replace(/\s+/g, "").toUpperCase();
  return normalized;
}

function isValidLandUseSymbol(value) {
  if (!value) return false;
  return LAND_REGISTER_SYMBOL_PATTERN.test(value);
}

function normalizeLandUses(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => ({
      symbol: normalizeLandUseSymbol(item?.symbol || item?.category_symbol),
      area: normalizeLandRegisterArea(item?.area),
    }))
    .filter((item) => item.symbol || item.area);
}

function renderLandRegisterRows() {
  const rows = landRegisterDraft.land_uses.length ? landRegisterDraft.land_uses : [{ symbol: "", area: "" }];
  const rowsHtml = rows
    .map(
      (row, index) => `<div class="grid grid-cols-[1fr_auto] items-center gap-2" data-land-use-row="${index}">
          <div class="group inline-flex items-center gap-2 rounded-full bg-white/70 px-2.5 py-1.5 ring-1 ring-black/5 shadow-[0_1px_0_rgba(255,255,255,0.75)_inset]">
            <input value="${row.symbol}" data-land-use-symbol="${index}" maxlength="${LAND_REGISTER_SYMBOL_MAX_LENGTH}" class="w-[92px] bg-transparent text-right text-[13px] font-semibold tracking-[-0.01em] text-zinc-800 outline-none" aria-label="Użytek i klasa bonitacyjna" placeholder="RIIIa" />
            <input value="${row.area}" data-land-use-area="${index}" inputmode="decimal" class="w-[64px] bg-transparent text-right text-[13px] font-semibold tracking-[-0.01em] text-zinc-800 outline-none" aria-label="Powierzchnia użytku" placeholder="0.00" />
            <span class="rounded-full bg-zinc-900/5 px-2 py-1 text-[11px] font-semibold text-zinc-700">m²</span>
          </div>
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

  const landUses = [];
  for (const item of landRegisterDraft.land_uses) {
    const symbol = normalizeLandUseSymbol(item.symbol);
    const normalizedAreaValue = normalizeIdentificationValue(item.area);
    if (!symbol && normalizedAreaValue === "") {
      continue;
    }
    if (!symbol || normalizedAreaValue === "") {
      continue;
    }
    const area = Number(normalizedAreaValue.replace(",", "."));
    if (symbol.length > LAND_REGISTER_SYMBOL_MAX_LENGTH || !isValidLandUseSymbol(symbol) || !Number.isFinite(area) || area < 0) {
      return null;
    }
    landUses.push({ symbol, area });
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
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
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
    if (!projectIdentificationApiId || !activeParcelTabId) return {};
    const parsedPayload = Object.fromEntries(
      Object.entries(payload).map(([field, value]) => [field, parseLandUsePayloadValue(field, value)])
    );
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
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

const projectBuildingParametersAutosave = createIdentificationAutosave({
  fields: PROJECT_BUILDING_PARAMETER_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectBuildingParameterStatus,
  async persist(payload) {
    if (!projectIdentificationApiId || !activeParcelTabId) return {};
    const parsedPayload = Object.fromEntries(
      Object.entries(payload).map(([field, value]) => [field, parseProjectBuildingParameterPayloadValue(field, value)])
    );
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsedPayload),
    });
    if (!response.ok) throw new Error("PROJECT_BUILDING_PARAMETERS_SAVE_FAILED");
    return response.json();
  },
  onPersisted(persisted) {
    applyProjectBuildingParametersToDom(persisted || {});
  },
});

const projectRoofArchitectureAutosave = createIdentificationAutosave({
  fields: PROJECT_ROOF_ARCHITECTURE_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectRoofArchitectureStatus,
  async persist(payload) {
    if (!projectIdentificationApiId || !activeParcelTabId) return {};
    const parsedPayload = Object.fromEntries(
      Object.entries(payload).map(([field, value]) => [field, parseProjectRoofArchitecturePayloadValue(field, value)])
    );
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsedPayload),
    });
    if (!response.ok) throw new Error("PROJECT_ROOF_ARCHITECTURE_SAVE_FAILED");
    return response.json();
  },
  onPersisted(persisted) {
    applyProjectRoofArchitectureToDom(persisted || {});
  },
});


const projectParkingEnvironmentAutosave = createIdentificationAutosave({
  fields: PROJECT_PARKING_ENVIRONMENT_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectParkingEnvironmentStatus,
  async persist(payload) {
    if (!projectIdentificationApiId || !activeParcelTabId) return {};
    const parsedPayload = Object.fromEntries(
      Object.entries(payload).map(([field, value]) => [field, parseProjectParkingEnvironmentPayloadValue(field, value)])
    );
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsedPayload),
    });
    if (!response.ok) throw new Error("PROJECT_PARKING_ENVIRONMENT_SAVE_FAILED");
    return response.json();
  },
  onPersisted(persisted) {
    applyProjectParkingEnvironmentToDom(persisted || {});
  },
});

const projectIdentificationAutosave = createIdentificationAutosave({
  fields: PROJECT_IDENTIFICATION_FIELDS,
  debounceMs: 550,
  retryDelayMs: 1600,
  onStatus: setProjectIdentificationStatus,
  async persist(payload) {
    if (!projectIdentificationApiId || !activeParcelTabId) return {};
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, {
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
    const tabs = await loadParcelTabs();
    renderParcelTabs(tabs);
    activeParcelTabId = String(activeParcelTabId || tabs?.[0]?.id || "");
    setParcelTab(activeParcelTabId);
    await loadActiveParcelConditions();
  } catch (_error) {
    projectIdentificationAutosave.setPersisted({});
    applyProjectIdentificationToDom({});
    projectLandUseAutosave.setPersisted({});
    applyProjectLandUseToDom({});
    projectBuildingParametersAutosave.setPersisted({});
    applyProjectBuildingParametersToDom({});
    projectRoofArchitectureAutosave.setPersisted({});
    applyProjectRoofArchitectureToDom({});
    projectParkingEnvironmentAutosave.setPersisted({});
    applyProjectParkingEnvironmentToDom({});
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



projectBuildingParameterInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectBuildingParameterFieldInputs(input);
    const field = input.dataset.projectBuildingParameterField;
    if (!field) return;
    projectBuildingParametersAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("blur", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectBuildingParameterFieldInputs(input);
    projectBuildingParametersAutosave.flushOnBlur();
  });
});

projectBuildingParameterRetryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    projectBuildingParametersAutosave.retryNow();
  });
});

projectRoofArchitectureInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectRoofArchitectureFieldInputs(input);
    const field = input.dataset.projectRoofArchitectureField;
    if (!field) return;
    projectRoofArchitectureAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("blur", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectRoofArchitectureFieldInputs(input);
    projectRoofArchitectureAutosave.flushOnBlur();
  });
});

projectRoofArchitectureRetryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    projectRoofArchitectureAutosave.retryNow();
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
    scheduleLandRegisterFlush();
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
      landRegisterDraft.land_uses[index].symbol = normalizeLandUseSymbol(target.value);
      if (target.value !== landRegisterDraft.land_uses[index].symbol) target.value = landRegisterDraft.land_uses[index].symbol;
      scheduleLandRegisterFlush();
      return;
    }
    if (target.dataset.landUseArea !== undefined) {
      const index = Number(target.dataset.landUseArea);
      if (!Number.isInteger(index) || !landRegisterDraft.land_uses[index]) return;
      landRegisterDraft.land_uses[index].area = target.value;
      scheduleLandRegisterFlush();
    }
  });


  node.addEventListener("blur", (event) => {
    if (isApplyingLandRegister) return;
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.dataset.landUseSymbol !== undefined) {
      const index = Number(target.dataset.landUseSymbol);
      if (!Number.isInteger(index) || !landRegisterDraft.land_uses[index]) return;
      const normalized = normalizeLandUseSymbol(target.value);
      landRegisterDraft.land_uses[index].symbol = normalized;
      if (target.value !== normalized) target.value = normalized;
      scheduleLandRegisterFlush(0);
      return;
    }
    if (target.dataset.landUseArea !== undefined) {
      const index = Number(target.dataset.landUseArea);
      if (!Number.isInteger(index) || !landRegisterDraft.land_uses[index]) return;
      const normalizedArea = normalizeLandRegisterArea(target.value);
      landRegisterDraft.land_uses[index].area = normalizedArea;
      if (target.value !== normalizedArea) target.value = normalizedArea;
      scheduleLandRegisterFlush(0);
    }
  }, true);

  node.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const removeIndexRaw = target.dataset.landUseRemove;
    if (removeIndexRaw === undefined) return;
    const index = Number(removeIndexRaw);
    if (!Number.isInteger(index)) return;
    landRegisterDraft.land_uses.splice(index, 1);
    renderLandRegisterRows();
    scheduleLandRegisterFlush();
  });
});

projectLandRegisterAddButtons.forEach((button) => {
  button.addEventListener("click", () => {
    landRegisterDraft.land_uses.push({ symbol: "", area: "" });
    renderLandRegisterRows();
    scheduleLandRegisterFlush();
  });
});

projectLandRegisterRetryButtons.forEach((button) => {
  button.addEventListener("click", () => scheduleLandRegisterFlush(0));
});

window.addEventListener("project:active:changed", (event) => {
  projectIdentificationApiId = event?.detail?.apiId || null;
  loadProjectIdentificationFromApi();
});


projectParkingEnvironmentInputs.forEach((input) => {
  input.addEventListener("input", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectParkingEnvironmentFieldInputs(input);
    const field = input.dataset.projectParkingEnvironmentField;
    if (!field) return;
    projectParkingEnvironmentAutosave.updateDraftField(field, input.value);
  });
  input.addEventListener("blur", () => {
    if (isApplyingProjectIdentification) return;
    syncProjectParkingEnvironmentFieldInputs(input);
    projectParkingEnvironmentAutosave.flushOnBlur();
  });
});

projectParkingEnvironmentRetryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    projectParkingEnvironmentAutosave.retryNow();
  });
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
    const shouldHide = panel.dataset.menuPanel !== nextTab;
    panel.classList.toggle("hidden", shouldHide);
    panel.toggleAttribute("hidden", shouldHide);
  });
  menuMpzpOnlySections.forEach((section) => {
    const shouldHide = nextTab !== "mpzp";
    section.classList.toggle("hidden", shouldHide);
    section.toggleAttribute("hidden", shouldHide);
  });
  menuTabs.forEach((tab) => {
    const isActive = tab.dataset.menuTab === nextTab;
    setTabActive(tab, isActive, activeTabClasses, inactiveTabClasses);
  });
}


function getParcelTabs() {
  return Array.from(document.querySelectorAll("[data-parcel-tab]"));
}

async function loadParcelTabs() {
  if (!projectIdentificationApiId) return [];
  const response = await fetch(`/api/projects/${projectIdentificationApiId}/parcel-tabs`, { credentials: "include" });
  if (!response.ok) throw new Error("PARCEL_TABS_FETCH_FAILED");
  return response.json();
}

function renderParcelTabs(tabs = []) {
  const strip = addParcelTabBtn?.parentElement;
  if (!strip) return;
  getParcelTabs().forEach((tab) => tab.remove());
  tabs.forEach((tab, index) => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "menu-preview-parcel-tab h-7 rounded-full px-3 text-[12px] font-semibold";
    el.dataset.parcelTab = String(tab.id);
    el.textContent = tab.label;
    el.setAttribute("aria-pressed", index === 0 ? "true" : "false");
    strip.insertBefore(el, addParcelTabBtn);
  });
}

async function loadActiveParcelConditions() {
  if (!activeParcelTabId) return;
  if (!conditionsByTabId[activeParcelTabId]) {
    const response = await fetch(`/api/parcel-tabs/${activeParcelTabId}/mpzp-conditions`, { credentials: "include" });
    if (!response.ok) throw new Error("PARCEL_CONDITIONS_FETCH_FAILED");
    conditionsByTabId[activeParcelTabId] = await response.json();
  }
  const payload = conditionsByTabId[activeParcelTabId] || {};
  projectIdentificationAutosave.setPersisted(payload);
  applyProjectIdentificationToDom(payload);
  projectLandUseAutosave.setPersisted(payload);
  applyProjectLandUseToDom(payload);
  projectBuildingParametersAutosave.setPersisted(payload);
  applyProjectBuildingParametersToDom(payload);
  projectRoofArchitectureAutosave.setPersisted(payload);
  applyProjectRoofArchitectureToDom(payload);
  projectParkingEnvironmentAutosave.setPersisted(payload);
  applyProjectParkingEnvironmentToDom(payload);
  applyProjectLandRegisterToDom(payload);
}

function setParcelTab(nextTab) {
  const panelList = Array.from(parcelPanels);
  const matchedPanel = panelList.find((panel) => panel.dataset.parcelPanel === nextTab) || panelList[0] || null;
  panelList.forEach((panel) => {
    panel.toggleAttribute("hidden", panel !== matchedPanel);
  });
  getParcelTabs().forEach((tab) => {
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

document.addEventListener("click", (event) => {
  const tab = event.target?.closest?.("[data-parcel-tab]");
  if (!tab) return;
  const next = tab.dataset.parcelTab;
  if (!next) return;
  activeParcelTabId = next;
  setParcelTab(next);
  loadActiveParcelConditions();
});

addParcelTabBtn?.addEventListener("click", async () => {
  if (!projectIdentificationApiId) {
    notifyTopbar("Najpierw wybierz aktywny projekt, aby dodać działkę.", "error", 8000);
    return;
  }
  const label = window.prompt("Podaj numer działki");
  if (!label) return;
  try {
    const response = await fetch(`/api/projects/${projectIdentificationApiId}/parcel-tabs`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      if (response.status === 409 || payload?.error === "PARCEL_TAB_LABEL_CONFLICT") {
        throw new Error("Działka o tym numerze już istnieje w projekcie.");
      }
      if (response.status === 400 && payload?.error === "LABEL_REQUIRED") {
        throw new Error("Podaj numer działki.");
      }
      throw new Error("Nie udało się dodać nowej działki.");
    }
    const created = await response.json();
    const tabs = await loadParcelTabs();
    renderParcelTabs(tabs);
    activeParcelTabId = String(created?.tab?.id || "");
    if (activeParcelTabId) {
      conditionsByTabId[activeParcelTabId] = created?.conditions || {};
      setParcelTab(activeParcelTabId);
      await loadActiveParcelConditions();
    }
  } catch (error) {
    notifyTopbar(error?.message || "Nie udało się dodać nowej działki.", "error", 8000);
  }
});

setMenuTab("dzialka");
renderPlanDocuments();
setDesignArea(null);
renderLayers();

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

designAreaActions?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-design-area-action]");
  if (!button || !boundaryEditor) return;
  const action = button.dataset.designAreaAction;
  if (action === "add" || action === "replace") {
    boundaryEditor.handleAction("create_site");
  } else if (action === "clear") {
    boundaryEditor.objects = boundaryEditor.objects.filter((item) => item.type !== "site_boundary");
    boundaryEditor.requestRender();
    setDesignArea(null);
  }
});

layersSearchInput?.addEventListener("input", (event) => {
  layerQuery = event.target.value || "";
  renderLayers();
});

layersPanel?.addEventListener("click", (event) => {
  const groupButton = event.target.closest("[data-layer-group]");
  if (groupButton) {
    const group = groupButton.dataset.layerGroup;
    openLayerGroups[group] = !(openLayerGroups[group] !== false);
    renderLayers();
    return;
  }

  const toggleButton = event.target.closest("[data-layer-toggle]");
  const drawButton = event.target.closest("[data-layer-draw]");

  if (drawButton) {
    const layerId = drawButton.dataset.layerDraw;
    const action = VECTOR_DRAW_ACTIONS[layerId];
    if (action) {
      renderWorkspaceMap();
      boundaryEditor?.handleAction(action);
    }
    return;
  }

  if (toggleButton) {
    const id = toggleButton.dataset.layerToggle;
    layerRows = layerRows.map((row) => (row.id === id ? { ...row, visible: !row.visible } : row));
    renderLayers();
    return;
  }

  const deleteButton = event.target.closest("[data-layer-delete]");
  if (deleteButton) {
    const id = deleteButton.dataset.layerDelete;
    layerRows = layerRows.filter((row) => row.id !== id);
    renderLayers();
  }
});

if (menuPreviewShell?.dataset.autoOpen === "true") {
  setMenuPreviewView(true);
}
