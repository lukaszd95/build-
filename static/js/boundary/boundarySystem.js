const LAND_USE_COLORS = {
  building: "#2563eb",
  greenery: "#16a34a",
  access: "#f59e0b",
  infrastructure: "#7c3aed",
  protection: "#dc2626",
  other: "#475569",
};

const EPS = 1e-9;
const STORAGE_KEY = "plotBoundariesByProject";

/** @typedef {'point'|'line'|'polygon'} GeometryType */

/**
 * @typedef {Object} BaseSpatialObject
 * @property {string} id
 * @property {string} type
 * @property {string} group
 * @property {string} label
 * @property {GeometryType} geometryType
 * @property {any} geometry
 * @property {Record<string, any>} attributes
 * @property {boolean} isVisible
 * @property {boolean} isLocked
 * @property {boolean} isEditable
 * @property {boolean} isBlocking
 * @property {'user'|'system'|'import'} createdBy
 * @property {string} createdAt
 * @property {string} updatedAt
 */

export const boundaryObjectDefinitions = {
  plot_boundary: {
    label: "Granica działki",
    geometryType: "polygon",
    createMode: "polygon_draw",
    blocking: true,
    editable: true,
    snappable: true,
    requiresClosedGeometry: true,
  },
  land_use_boundary: {
    label: "Granica przeznaczenia terenu",
    geometryType: ["line", "polygon"],
    createMode: ["line_draw", "polygon_draw"],
    blocking: true,
    editable: true,
    snappable: true,
    requiresLandUseType: true,
  },
  site_boundary: {
    label: "Obszar analizy",
    geometryType: "polygon",
    createMode: ["polygon_draw", "buffer_from_plot"],
    blocking: false,
    editable: true,
    snappable: true,
    requiresClosedGeometry: true,
  },
};

function getStorageAdapter() {
  if (typeof window !== "undefined" && window.localStorage) return window.localStorage;
  return null;
}

function normalizeProjectId(projectId) {
  if (projectId === null || projectId === undefined) return "";
  return String(projectId).trim();
}

export class ProjectContextService {
  constructor() {
    this.context = { projectId: "", projectName: "", isActive: false };
  }

  setActiveProject(context = {}) {
    const projectId = normalizeProjectId(context.projectId);
    this.context = {
      projectId,
      projectName: context.projectName || "",
      isActive: !!projectId,
    };
    return this.getActiveProject();
  }

  clearActiveProject() {
    this.context = { projectId: "", projectName: "", isActive: false };
  }

  getActiveProject() {
    return { ...this.context };
  }
}

export class PlotBoundaryGeometryService {
  calculateBoundaryArea(geometry) {
    const polygon = this.fromGeoJson(geometry);
    return calculateArea(polygon);
  }

  calculateBoundaryPerimeter(geometry) {
    const polygon = this.fromGeoJson(geometry);
    return calculatePerimeter(polygon);
  }

  fromGeoJson(geometry) {
    if (Array.isArray(geometry)) return geometry;
    const coords = geometry?.coordinates?.[0] || [];
    const points = coords.map(([x, y]) => ({ x: Number(x), y: Number(y) }));
    if (points.length > 2) {
      const first = points[0];
      const last = points[points.length - 1];
      if (Math.hypot(first.x - last.x, first.y - last.y) < EPS) points.pop();
    }
    return points;
  }

  toGeoJsonPolygon(points = []) {
    const ring = points.map((p) => [Number(p.x), Number(p.y)]);
    if (!ring.length) return { type: "Polygon", coordinates: [] };
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) ring.push([...first]);
    return { type: "Polygon", coordinates: [ring] };
  }
}

export class PlotBoundaryValidationService {
  constructor(geometryService = new PlotBoundaryGeometryService()) {
    this.geometryService = geometryService;
  }

  validatePlotBoundary(geometry, projectId = "") {
    const points = this.geometryService.fromGeoJson(geometry);
    const errors = [];
    const uniquePoints = new Set(points.map((p) => `${p.x.toFixed(6)}:${p.y.toFixed(6)}`));
    if (points.length < 3 || uniquePoints.size < 3) errors.push("Granica działki musi mieć co najmniej 3 punkty.");

    if (!Array.isArray(geometry)) {
      const ring = geometry?.coordinates?.[0] || [];
      if (ring.length < 4) {
        errors.push("Granica działki musi być zamknięta.");
      } else {
        const first = ring[0] || [];
        const last = ring[ring.length - 1] || [];
        if (first[0] !== last[0] || first[1] !== last[1]) errors.push("Granica działki musi być zamknięta.");
      }
    }

    if (polygonHasSelfIntersection(points)) errors.push("Nie można zapisać granicy z samoprzecięciem.");
    if (this.geometryService.calculateBoundaryArea(points) <= 0) errors.push("Granica działki musi mieć dodatnią powierzchnię.");

    for (let i = 1; i < points.length; i += 1) {
      if (Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y) < EPS) {
        errors.push("Granica działki nie może zawierać odcinków zerowej długości.");
        break;
      }
    }

    if (!normalizeProjectId(projectId)) errors.push("Granica działki musi być przypisana do projektu.");
    return { valid: errors.length === 0, errors };
  }
}

export class PlotBoundaryService {
  constructor({ storage = getStorageAdapter(), geometryService = new PlotBoundaryGeometryService(), validationService = new PlotBoundaryValidationService(geometryService) } = {}) {
    this.storage = storage;
    this.geometry = geometryService;
    this.validation = validationService;
  }

  readAll() {
    if (!this.storage) return {};
    const raw = this.storage.getItem(STORAGE_KEY);
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  writeAll(value) {
    if (!this.storage) return;
    this.storage.setItem(STORAGE_KEY, JSON.stringify(value));
  }

  async loadProjectPlotBoundaries(projectId) {
    const id = normalizeProjectId(projectId);
    if (!id) return [];
    const all = this.readAll();
    return Array.isArray(all[id]) ? all[id] : [];
  }

  async savePlotBoundary(boundary) {
    const id = normalizeProjectId(boundary?.projectId);
    const result = this.validation.validatePlotBoundary(boundary?.geometry, id);
    if (!result.valid) throw new Error(result.errors.join(" "));
    const all = this.readAll();
    const list = Array.isArray(all[id]) ? all[id] : [];
    const next = { ...boundary, updatedAt: nowIso(), createdAt: boundary.createdAt || nowIso() };
    all[id] = [...list.filter((item) => item.id !== next.id), next];
    this.writeAll(all);
  }

  async updatePlotBoundary(boundary) {
    return this.savePlotBoundary(boundary);
  }

  async deletePlotBoundary(boundaryId, projectId) {
    const id = normalizeProjectId(projectId);
    if (!id) throw new Error("Granica działki musi być przypisana do projektu.");
    const all = this.readAll();
    const list = Array.isArray(all[id]) ? all[id] : [];
    all[id] = list.filter((item) => item.id !== boundaryId);
    this.writeAll(all);
  }
}

export class WorkspaceInteractionService {
  constructor() {
    this.activeProjectId = "";
    this.isDrawing = false;
    this.points = [];
  }

  startPlotBoundaryDrawing(projectId) {
    this.activeProjectId = normalizeProjectId(projectId);
    if (!this.activeProjectId) throw new Error("Najpierw wybierz lub utwórz projekt.");
    this.isDrawing = true;
    this.points = [];
  }

  addBoundaryVertex(point) {
    if (!this.isDrawing) return;
    this.points.push({ x: Number(point.x), y: Number(point.y) });
  }

  closeBoundaryPolygon() {
    this.isDrawing = false;
    return [...this.points];
  }

  cancelBoundaryDrawing() {
    this.isDrawing = false;
    this.points = [];
  }
}

const __plotGeometryService = new PlotBoundaryGeometryService();
const __plotValidationService = new PlotBoundaryValidationService(__plotGeometryService);
const __plotBoundaryService = new PlotBoundaryService({ geometryService: __plotGeometryService, validationService: __plotValidationService });
const __workspaceInteractionService = new WorkspaceInteractionService();

export function startPlotBoundaryDrawing(projectId) { __workspaceInteractionService.startPlotBoundaryDrawing(projectId); }
export function addBoundaryVertex(point) { __workspaceInteractionService.addBoundaryVertex(point); }
export function closeBoundaryPolygon() { return __workspaceInteractionService.closeBoundaryPolygon(); }
export function cancelBoundaryDrawing() { __workspaceInteractionService.cancelBoundaryDrawing(); }
export function savePlotBoundary(boundary) { return __plotBoundaryService.savePlotBoundary(boundary); }
export function updatePlotBoundary(boundary) { return __plotBoundaryService.updatePlotBoundary(boundary); }
export function deletePlotBoundary(boundaryId, projectId) { return __plotBoundaryService.deletePlotBoundary(boundaryId, projectId); }
export function calculateBoundaryArea(geometry) { return __plotGeometryService.calculateBoundaryArea(geometry); }
export function calculateBoundaryPerimeter(geometry) { return __plotGeometryService.calculateBoundaryPerimeter(geometry); }
export function validatePlotBoundary(geometry, projectId = "") { return __plotValidationService.validatePlotBoundary(geometry, projectId); }
export function loadProjectPlotBoundaries(projectId) { return __plotBoundaryService.loadProjectPlotBoundaries(projectId); }

function nowIso() {
  return new Date().toISOString();
}

export function createBoundaryObject(type, payload = {}) {
  const definition = boundaryObjectDefinitions[type];
  if (!definition) throw new Error(`Unsupported boundary type: ${type}`);
  const ts = nowIso();
  const geometryType = payload.geometryType || (Array.isArray(definition.geometryType) ? definition.geometryType[0] : definition.geometryType);
  return {
    id: payload.id || `${type}_${Math.random().toString(36).slice(2, 10)}`,
    type,
    group: "boundaries",
    label: payload.label || definition.label,
    geometryType,
    geometry: payload.geometry || [],
    attributes: payload.attributes || {},
    isVisible: payload.isVisible !== false,
    isLocked: !!payload.isLocked,
    isEditable: payload.isEditable !== false,
    isBlocking: payload.isBlocking ?? definition.blocking,
    createdBy: payload.createdBy || "user",
    createdAt: payload.createdAt || ts,
    updatedAt: payload.updatedAt || ts,
  };
}

export function calculateArea(polygon = []) {
  if (!Array.isArray(polygon) || polygon.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < polygon.length; i += 1) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

export function calculatePerimeter(polygon = []) {
  if (!Array.isArray(polygon) || polygon.length < 2) return 0;
  let length = 0;
  for (let i = 0; i < polygon.length; i += 1) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    length += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return length;
}

function pointInPolygon(point, polygon = []) {
  if (!point || polygon.length < 3) return false;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x; const yi = polygon[i].y;
    const xj = polygon[j].x; const yj = polygon[j].y;
    const intersect = ((yi > point.y) !== (yj > point.y))
      && (point.x < ((xj - xi) * (point.y - yi)) / ((yj - yi) || EPS) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function lineSegmentsIntersect(p1, p2, p3, p4) {
  const det = (a, b, c, d) => a * d - b * c;
  const r = { x: p2.x - p1.x, y: p2.y - p1.y };
  const s = { x: p4.x - p3.x, y: p4.y - p3.y };
  const denom = det(r.x, r.y, s.x, s.y);
  if (Math.abs(denom) < EPS) return false;
  const qp = { x: p3.x - p1.x, y: p3.y - p1.y };
  const t = det(qp.x, qp.y, s.x, s.y) / denom;
  const u = det(qp.x, qp.y, r.x, r.y) / denom;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}

function polygonHasSelfIntersection(poly = []) {
  if (poly.length < 4) return false;
  const n = poly.length;
  for (let i = 0; i < n; i += 1) {
    const a1 = poly[i];
    const a2 = poly[(i + 1) % n];
    for (let j = i + 1; j < n; j += 1) {
      if (Math.abs(i - j) <= 1 || (i === 0 && j === n - 1)) continue;
      const b1 = poly[j];
      const b2 = poly[(j + 1) % n];
      if (lineSegmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  return false;
}

function normalizePolygon(points = []) {
  const cleaned = [];
  for (let i = 0; i < points.length; i += 1) {
    const p = points[i];
    const prev = cleaned[cleaned.length - 1];
    if (!prev || Math.hypot(prev.x - p.x, prev.y - p.y) > EPS) {
      cleaned.push({ x: Number(p.x), y: Number(p.y) });
    }
  }
  if (cleaned.length > 2) {
    const first = cleaned[0];
    const last = cleaned[cleaned.length - 1];
    if (Math.hypot(first.x - last.x, first.y - last.y) < EPS) cleaned.pop();
  }
  if (signedArea(cleaned) < 0) cleaned.reverse();
  return cleaned;
}

function signedArea(poly = []) {
  let sum = 0;
  for (let i = 0; i < poly.length; i += 1) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return sum / 2;
}

export function contains(container, geometry) {
  if (!container?.length) return false;
  if (Array.isArray(geometry)) {
    return geometry.every((point) => pointInPolygon(point, container));
  }
  return pointInPolygon(geometry, container);
}

export function intersects(a = [], b = []) {
  if (!a.length || !b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const a1 = a[i];
    const a2 = a[(i + 1) % a.length];
    for (let j = 0; j < b.length; j += 1) {
      const b1 = b[j];
      const b2 = b[(j + 1) % b.length];
      if (lineSegmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  return contains(a, b[0]) || contains(b, a[0]);
}

function bbox(poly = []) {
  const xs = poly.map((p) => p.x);
  const ys = poly.map((p) => p.y);
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

export function clipGeometryToPlot(geometry = [], plotBoundary = []) {
  return geometry.filter((point) => contains(plotBoundary, point));
}

export function bufferGeometry(geometry = [], distance = 0) {
  if (!geometry.length) return [];
  const box = bbox(geometry);
  return [
    { x: box.minX - distance, y: box.minY - distance },
    { x: box.maxX + distance, y: box.minY - distance },
    { x: box.maxX + distance, y: box.maxY + distance },
    { x: box.minX - distance, y: box.maxY + distance },
  ];
}

export function splitPolygonByLine(polygon = [], line = []) {
  if (line.length < 2) return [polygon];
  const axis = Math.abs(line[1].x - line[0].x) >= Math.abs(line[1].y - line[0].y) ? "x" : "y";
  const divider = (line[0][axis] + line[1][axis]) / 2;
  const left = polygon.filter((p) => p[axis] <= divider + EPS);
  const right = polygon.filter((p) => p[axis] >= divider - EPS);
  return [left.length >= 3 ? left : polygon, right.length >= 3 ? right : polygon];
}

export function unionPolygons(polygons = []) {
  if (!polygons.length) return [];
  const box = bbox(polygons.flat());
  return [
    { x: box.minX, y: box.minY },
    { x: box.maxX, y: box.minY },
    { x: box.maxX, y: box.maxY },
    { x: box.minX, y: box.maxY },
  ];
}

export function differencePolygon(base = [], cut = []) {
  if (!base.length) return [];
  if (!intersects(base, cut)) return base;
  const baseBox = bbox(base);
  const cutBox = bbox(cut);
  if (cutBox.minX <= baseBox.minX && cutBox.maxX >= baseBox.maxX) return [];
  return base.filter((p) => !contains(cut, p));
}

export function validateBoundaryTopology(object) {
  const issues = [];
  const warnings = [];
  if (!object) return { valid: false, issues: ["Brak obiektu"], warnings };
  const geometry = object.geometry || [];

  if (object.geometryType === "polygon") {
    if (geometry.length < 3) issues.push("Poligon musi mieć minimum 3 unikalne wierzchołki.");
    if (calculateArea(geometry) <= 0) issues.push("Poligon musi mieć dodatnie pole powierzchni.");
    if (polygonHasSelfIntersection(geometry)) issues.push("Poligon ma samoprzecięcia.");
    if (signedArea(geometry) < 0) warnings.push("Poligon ma orientację clockwise.");
  }

  if (object.geometryType === "line" && geometry.length < 2) {
    issues.push("Linia musi mieć minimum 2 punkty.");
  }

  const duplicates = new Set();
  geometry.forEach((p, idx) => {
    const key = `${p.x.toFixed(6)}:${p.y.toFixed(6)}`;
    if (duplicates.has(key)) warnings.push(`Duplikat wierzchołka na pozycji ${idx + 1}.`);
    duplicates.add(key);
  });

  for (let i = 1; i < geometry.length; i += 1) {
    if (Math.hypot(geometry[i].x - geometry[i - 1].x, geometry[i].y - geometry[i - 1].y) < EPS) {
      warnings.push(`Odcinek zerowej długości między punktami ${i} i ${i + 1}.`);
    }
  }

  return { valid: issues.length === 0, issues, warnings };
}

export function normalizeBoundaryGeometry(object) {
  if (!object) return object;
  if (object.geometryType === "polygon") {
    return { ...object, geometry: normalizePolygon(object.geometry || []), updatedAt: nowIso() };
  }
  if (object.geometryType === "line") {
    const line = normalizePolygon(object.geometry || []);
    return { ...object, geometry: line, updatedAt: nowIso() };
  }
  return object;
}

export function isInsidePlotBoundary(object, plotBoundary) {
  return contains(plotBoundary?.geometry || [], object?.geometry || []);
}

export function isInsideSiteBoundary(object, siteBoundary) {
  return contains(siteBoundary?.geometry || [], object?.geometry || []);
}

export function doesSiteContainPlot(siteBoundary, plotBoundary) {
  return contains(siteBoundary?.geometry || [], plotBoundary?.geometry || []);
}

export function splitPlotByLandUse(plotBoundary, landUseBoundaries = []) {
  if (!plotBoundary?.geometry?.length) return [];
  let chunks = [plotBoundary.geometry];
  landUseBoundaries.forEach((boundary) => {
    if (boundary.geometryType === "line") {
      chunks = chunks.flatMap((chunk) => splitPolygonByLine(chunk, boundary.geometry));
    } else if (boundary.geometryType === "polygon") {
      chunks.push(boundary.geometry.filter((p) => contains(plotBoundary.geometry, p)));
    }
  });
  return chunks.filter((chunk) => chunk.length >= 3);
}

export function getBuildableSubAreas(plotBoundary, landUseBoundaries = []) {
  const buildingZones = landUseBoundaries.filter((boundary) => boundary.attributes?.landUseType === "building");
  if (!buildingZones.length) return [plotBoundary?.geometry || []];
  return buildingZones
    .map((zone) => zone.geometryType === "polygon" ? zone.geometry : clipGeometryToPlot(zone.geometry, plotBoundary.geometry))
    .filter((zone) => zone.length >= 3);
}

export class BoundaryGeometryService {
  calculateArea = calculateArea;
  calculatePerimeter = calculatePerimeter;
  contains = contains;
  intersects = intersects;
  clipGeometryToPlot = clipGeometryToPlot;
  bufferGeometry = bufferGeometry;
  splitPolygonByLine = splitPolygonByLine;
  unionPolygons = unionPolygons;
  differencePolygon = differencePolygon;
}

export class BoundaryValidationService {
  validateBoundaryTopology = validateBoundaryTopology;
  normalizeBoundaryGeometry = normalizeBoundaryGeometry;

  validateRelations({ plotBoundary, landUseBoundaries = [], siteBoundary }) {
    const issues = [];
    const warnings = [];

    if (plotBoundary && plotBoundary.geometryType !== "polygon") {
      issues.push("plot_boundary musi być poligonem.");
    }
    if (siteBoundary && !doesSiteContainPlot(siteBoundary, plotBoundary)) {
      warnings.push("site_boundary nie zawiera w pełni plot_boundary.");
    }

    landUseBoundaries.forEach((landUse) => {
      const insidePlot = plotBoundary ? isInsidePlotBoundary(landUse, plotBoundary) : false;
      const insideSite = siteBoundary ? isInsideSiteBoundary(landUse, siteBoundary) : false;
      if (!(insidePlot || insideSite)) {
        warnings.push(`land_use_boundary ${landUse.label} znajduje się poza zakresem plot/site.`);
      }
    });

    return { valid: issues.length === 0, issues, warnings };
  }
}

export class BoundaryReasoningService {
  evaluate({ plotBoundary, siteBoundary, landUseBoundaries = [] }) {
    const results = [];
    if (plotBoundary) {
      results.push({
        objectId: plotBoundary.id,
        role: "plot_boundary",
        issues: [],
        warnings: [],
        inferredMeaning: ["To jest główna granica działki"],
        relatedObjects: [siteBoundary?.id].filter(Boolean),
      });
    }
    if (siteBoundary) {
      const warnings = doesSiteContainPlot(siteBoundary, plotBoundary)
        ? []
        : ["Obszar analizy nie obejmuje całej działki — zgłoś problem"];
      results.push({
        objectId: siteBoundary.id,
        role: "site_boundary",
        issues: [],
        warnings,
        inferredMeaning: ["To jest szerszy obszar analizy"],
        relatedObjects: [plotBoundary?.id].filter(Boolean),
      });
    }

    landUseBoundaries.forEach((item) => {
      const inferred = ["Ta linia dzieli teren na strefy funkcjonalne"];
      if (item.attributes?.landUseType === "building") inferred.push("Ta część działki jest przeznaczona pod zabudowę");
      else inferred.push("Ta część działki jest poza strefą zabudowy");

      const useful = intersects(plotBoundary?.geometry || [], item.geometry || []) || contains(plotBoundary?.geometry || [], item.geometry || []);
      results.push({
        objectId: item.id,
        role: "land_use_boundary",
        issues: [],
        warnings: useful ? [] : ["Granica przeznaczenia nie przecina działki w użyteczny sposób — zgłoś ostrzeżenie"],
        inferredMeaning: inferred,
        relatedObjects: [plotBoundary?.id, siteBoundary?.id].filter(Boolean),
      });
    });

    return results;
  }
}

export class BoundaryAnalysisService {
  constructor() {
    this.geometry = new BoundaryGeometryService();
  }

  summarize({ plotBoundary, landUseBoundaries = [], siteBoundary }) {
    const plotArea = plotBoundary ? this.geometry.calculateArea(plotBoundary.geometry) : 0;
    const plotPerimeter = plotBoundary ? this.geometry.calculatePerimeter(plotBoundary.geometry) : 0;
    const split = plotBoundary ? splitPlotByLandUse(plotBoundary, landUseBoundaries) : [];
    const buildable = plotBoundary ? getBuildableSubAreas(plotBoundary, landUseBoundaries) : [];
    return {
      plotArea,
      plotPerimeter,
      relationPlotToSite: plotBoundary && siteBoundary ? doesSiteContainPlot(siteBoundary, plotBoundary) : false,
      functionalSplitCount: split.length,
      buildableArea: buildable.reduce((sum, chunk) => sum + calculateArea(chunk), 0),
    };
  }
}

class BaseBoundaryRenderer {
  drawPolygon(ctx, points, style) {
    if (!points?.length) return;
    ctx.save();
    ctx.beginPath();
    points.forEach((p, idx) => {
      if (idx === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.closePath();
    if (style.fillStyle) {
      ctx.fillStyle = style.fillStyle;
      ctx.globalAlpha = style.fillOpacity ?? 0.1;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    ctx.strokeStyle = style.strokeStyle || "#0f172a";
    ctx.lineWidth = style.strokeWidth || 1;
    if (style.dash) ctx.setLineDash(style.dash);
    ctx.stroke();
    ctx.restore();
  }

  drawVertices(ctx, points, color = "#334155") {
    points.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    });
  }

  drawLabel(ctx, points, label) {
    if (!label || !points.length) return;
    const center = points.reduce((acc, p) => ({ x: acc.x + p.x / points.length, y: acc.y + p.y / points.length }), { x: 0, y: 0 });
    ctx.fillStyle = "#0f172a";
    ctx.font = "12px Inter, sans-serif";
    ctx.fillText(label, center.x + 8, center.y - 8);
  }
}

export class PlotBoundaryRenderer extends BaseBoundaryRenderer {
  draw(ctx, object, selected = false) {
    const style = {
      strokeWidth: 2,
      strokeStyle: "#0f766e",
      fillStyle: "#0f766e",
      fillOpacity: 0.08,
    };
    this.drawPolygon(ctx, object.geometry, style);
    this.drawLabel(ctx, object.geometry, object.label);
    if (selected) this.drawVertices(ctx, object.geometry, "#0f766e");
  }
}

export class LandUseBoundaryRenderer extends BaseBoundaryRenderer {
  draw(ctx, object, selected = false) {
    const color = LAND_USE_COLORS[object.attributes?.landUseType || "other"] || LAND_USE_COLORS.other;
    if (object.geometryType === "line") {
      const pts = object.geometry || [];
      if (pts.length < 2) return;
      ctx.save();
      ctx.beginPath();
      pts.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = color;
      ctx.setLineDash([8, 4]);
      ctx.stroke();
      ctx.restore();
      if (selected) this.drawVertices(ctx, pts, color);
      this.drawLabel(ctx, pts, `${object.label} (${object.attributes?.landUseType || "other"})`);
      return;
    }
    this.drawPolygon(ctx, object.geometry, {
      strokeWidth: 1.5,
      strokeStyle: color,
      fillStyle: color,
      fillOpacity: 0.12,
      dash: [8, 4],
    });
    if (selected) this.drawVertices(ctx, object.geometry, color);
    this.drawLabel(ctx, object.geometry, `${object.label} (${object.attributes?.landUseType || "other"})`);
  }
}

export class SiteBoundaryRenderer extends BaseBoundaryRenderer {
  draw(ctx, object, selected = false) {
    this.drawPolygon(ctx, object.geometry, {
      strokeWidth: 1,
      strokeStyle: "#64748b",
      fillStyle: "#64748b",
      fillOpacity: 0.03,
      dash: [2, 5],
    });
    this.drawLabel(ctx, object.geometry, object.label);
    if (selected) this.drawVertices(ctx, object.geometry, "#64748b");
  }
}

export class BoundaryToolbar {
  constructor({ onAction }) {
    this.onAction = onAction;
  }

  render() {
    const root = document.createElement("div");
    root.className = "flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white/90 p-2 text-xs";
    root.innerHTML = `
      <button data-boundary-action="create_plot" class="rounded-lg border border-emerald-300 px-2 py-1 hover:bg-emerald-50">Granica działki</button>
      <button data-boundary-action="create_site" class="rounded-lg border border-slate-300 px-2 py-1 hover:bg-slate-50">Obszar analizy</button>
      <button data-boundary-action="create_land_use_line" class="rounded-lg border border-amber-300 px-2 py-1 hover:bg-amber-50">Linia przeznaczenia</button>
      <button data-boundary-action="create_land_use_polygon" class="rounded-lg border border-blue-300 px-2 py-1 hover:bg-blue-50">Strefa funkcjonalna</button>
      <button data-boundary-action="finish" class="rounded-lg border border-gray-300 px-2 py-1 hover:bg-gray-50">Zakończ rysowanie</button>
      <button data-boundary-action="generate_site_from_plot" class="rounded-lg border border-violet-300 px-2 py-1 hover:bg-violet-50">Site z bufora działki</button>
    `;
    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-boundary-action]");
      if (button) this.onAction?.(button.dataset.boundaryAction);
    });
    return root;
  }
}

export class BoundaryPropertiesPanel {
  constructor({ onAssignLandUse }) {
    this.onAssignLandUse = onAssignLandUse;
    this.node = document.createElement("div");
    this.node.className = "rounded-xl border border-gray-200 bg-white/90 p-3 text-xs text-gray-700";
  }

  update({ selected, validation, analysis, reasoning }) {
    const options = Object.keys(LAND_USE_COLORS).map((key) => `<option value="${key}">${key}</option>`).join("");
    this.node.innerHTML = `
      <div class="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Właściwości granic</div>
      <div><b>Obiekt:</b> ${selected?.label || "brak"}</div>
      <div><b>Typ:</b> ${selected?.type || "—"}</div>
      <div><b>Pole działki:</b> ${analysis.plotArea.toFixed(2)} m²</div>
      <div><b>Obwód działki:</b> ${analysis.plotPerimeter.toFixed(2)} m</div>
      <div><b>Buildable area:</b> ${analysis.buildableArea.toFixed(2)} m²</div>
      <div><b>Podziały funkcjonalne:</b> ${analysis.functionalSplitCount}</div>
      <div class="mt-2 rounded-md bg-gray-50 p-2 text-[11px]"><b>Walidacja:</b> ${validation.valid ? "OK" : validation.issues.join("; ") || "błędy"}</div>
      <div class="mt-2 rounded-md bg-amber-50 p-2 text-[11px]"><b>Ostrzeżenia:</b> ${(validation.warnings || []).concat(reasoning.flatMap((r) => r.warnings || [])).join("; ") || "brak"}</div>
      <label class="mt-2 block text-[11px] font-semibold">Typ funkcji (dla land_use_boundary)</label>
      <select data-boundary-land-use class="mt-1 w-full rounded-md border border-gray-300 bg-white px-2 py-1 text-xs">
        ${options}
      </select>
    `;
    const select = this.node.querySelector("[data-boundary-land-use]");
    if (select) {
      select.value = selected?.attributes?.landUseType || "other";
      select.addEventListener("change", (event) => this.onAssignLandUse?.(event.target.value));
    }
  }

  render() {
    return this.node;
  }
}

class BaseBoundaryTool {
  constructor(editor, { type, geometryType }) {
    this.editor = editor;
    this.type = type;
    this.geometryType = geometryType;
    this.points = [];
  }

  onClick(point) {
    this.points.push(point);
    this.editor.requestRender();
  }

  onDoubleClick() {
    this.commit();
  }

  commit() {
    if ((this.geometryType === "polygon" && this.points.length < 3) || (this.geometryType === "line" && this.points.length < 2)) return;
    const object = createBoundaryObject(this.type, {
      geometryType: this.geometryType,
      geometry: [...this.points],
      attributes: this.type === "land_use_boundary" ? { landUseType: "other" } : {},
    });
    this.editor.create(object);
    this.points = [];
  }
}

export class PlotBoundaryTool extends BaseBoundaryTool {
  constructor(editor) {
    super(editor, { type: "plot_boundary", geometryType: "polygon" });
  }
}

export class LandUseBoundaryTool extends BaseBoundaryTool {
  constructor(editor, geometryType = "line") {
    super(editor, { type: "land_use_boundary", geometryType });
  }
}

export class SiteBoundaryTool extends BaseBoundaryTool {
  constructor(editor) {
    super(editor, { type: "site_boundary", geometryType: "polygon" });
  }
}

export function findObjectCentroid(object) {
  if (!object?.geometry?.length) return { x: 0, y: 0 };
  const total = object.geometry.length;
  return object.geometry.reduce((acc, p) => ({ x: acc.x + p.x / total, y: acc.y + p.y / total }), { x: 0, y: 0 });
}
