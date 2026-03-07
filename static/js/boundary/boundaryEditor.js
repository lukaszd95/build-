import {
  PlotBoundaryRenderer,
  LandUseBoundaryRenderer,
  SiteBoundaryRenderer,
  PlotBoundaryTool,
  LandUseBoundaryTool,
  SiteBoundaryTool,
  BoundaryValidationService,
  BoundaryReasoningService,
  BoundaryAnalysisService,
  ProjectContextService,
  PlotBoundaryService,
  PlotBoundaryValidationService,
  PlotBoundaryGeometryService,
  createBoundaryObject,
  bufferGeometry,
  normalizeBoundaryGeometry,
  validateBoundaryTopology,
} from "./boundarySystem.js";

export function createBoundaryEditor({ container, onStateChange }) {
  if (!container) return null;
  return new BoundaryEditor(container, onStateChange);
}

class BoundaryEditor {
  constructor(container, onStateChange) {
    this.container = container;
    this.onStateChange = onStateChange;
    this.objects = [];
    this.selectedId = null;
    this.activeTool = null;
    this.drag = null;
    this.validation = new BoundaryValidationService();
    this.reasoning = new BoundaryReasoningService();
    this.analysis = new BoundaryAnalysisService();
    this.projectContextService = new ProjectContextService();
    this.plotBoundaryGeometryService = new PlotBoundaryGeometryService();
    this.plotBoundaryValidationService = new PlotBoundaryValidationService(this.plotBoundaryGeometryService);
    this.plotBoundaryService = new PlotBoundaryService({
      geometryService: this.plotBoundaryGeometryService,
      validationService: this.plotBoundaryValidationService,
    });
    this.renderers = {
      plot_boundary: new PlotBoundaryRenderer(),
      land_use_boundary: new LandUseBoundaryRenderer(),
      site_boundary: new SiteBoundaryRenderer(),
    };
    this.buildUI();
    this.requestRender();
  }

  buildUI() {
    this.container.innerHTML = "";
    this.wrapper = document.createElement("div");
    this.wrapper.className = "h-full";

    this.canvasWrap = document.createElement("div");
    this.canvasWrap.className = "relative h-full overflow-hidden rounded-xl border border-gray-200 bg-white";
    this.canvas = document.createElement("canvas");
    this.canvas.className = "absolute inset-0 h-full w-full";
    this.canvasWrap.appendChild(this.canvas);
    this.drawingHint = document.createElement("div");
    this.drawingHint.className = "pointer-events-none absolute left-3 top-3 rounded-lg bg-white/95 px-2 py-1 text-[11px] font-medium text-gray-700 shadow";
    this.canvasWrap.appendChild(this.drawingHint);

    this.wrapper.append(this.canvasWrap);
    this.container.appendChild(this.wrapper);

    this.resize();
    window.addEventListener("resize", () => this.resize());
    this.canvas.addEventListener("click", (event) => this.onCanvasClick(event));
    this.canvas.addEventListener("dblclick", () => this.finishTool());
    this.canvas.addEventListener("mousedown", (event) => this.startDrag(event));
    this.canvas.addEventListener("mousemove", (event) => this.moveDrag(event));
    window.addEventListener("mouseup", () => this.stopDrag());
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(100, Math.floor(rect.width));
    this.canvas.height = Math.max(100, Math.floor(rect.height));
    this.requestRender();
  }

  requestRender() {
    const ctx = this.canvas.getContext("2d");
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.drawGrid(ctx);
    this.objects.forEach((object) => {
      if (!object.isVisible) return;
      const selected = object.id === this.selectedId;
      this.renderers[object.type]?.draw(ctx, object, selected);
    });

    if (this.activeTool?.points?.length) {
      ctx.save();
      ctx.strokeStyle = "#111827";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      this.activeTool.points.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.stroke();
      ctx.restore();
    }

    this.updateDrawingHint();

    const selected = this.objects.find((o) => o.id === this.selectedId) || null;
    const normalized = selected ? normalizeBoundaryGeometry(selected) : null;
    const topoValidation = normalized ? validateBoundaryTopology(normalized) : { valid: true, issues: [], warnings: [] };
    const grouped = this.groupedBoundaries();
    const relationValidation = this.validation.validateRelations(grouped);
    const analysis = this.analysis.summarize(grouped);
    const reasoning = this.reasoning.evaluate(grouped);
    this.onStateChange?.({ grouped, analysis, reasoning, selected });
  }

  updateDrawingHint() {
    if (!this.drawingHint) return;
    const activeProject = this.projectContextService.getActiveProject();
    if (!activeProject.isActive) {
      this.drawingHint.textContent = "Najpierw wybierz lub utwórz projekt.";
      return;
    }
    if (this.activeTool?.type === "plot_boundary") {
      const count = this.activeTool.points.length;
      if (count === 0) {
        this.drawingHint.textContent = "Kliknij, aby dodać punkt granicy działki.";
      } else {
        const lastSegment = count >= 2
          ? Math.hypot(
              this.activeTool.points[count - 1].x - this.activeTool.points[count - 2].x,
              this.activeTool.points[count - 1].y - this.activeTool.points[count - 2].y
            ).toFixed(2)
          : "0.00";
        this.drawingHint.textContent = `Klikaj kolejne punkty. Punkty: ${count}, odcinek: ${lastSegment} m.`;
      }
      return;
    }
    if (this.selectedId) {
      this.drawingHint.textContent = "Granica działki została utworzona. Uzupełnij dane i zapisz.";
      return;
    }
    this.drawingHint.textContent = "Wybierz warstwę i kliknij „Dodaj granicę działki” aby rysować.";
  }

  drawGrid(ctx) {
    ctx.save();
    ctx.strokeStyle = "rgba(148,163,184,0.2)";
    ctx.lineWidth = 1;
    for (let x = 0; x < this.canvas.width; x += 24) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, this.canvas.height);
      ctx.stroke();
    }
    for (let y = 0; y < this.canvas.height; y += 24) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.canvas.width, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  groupedBoundaries() {
    return {
      plotBoundary: this.objects.find((o) => o.type === "plot_boundary") || null,
      siteBoundary: this.objects.find((o) => o.type === "site_boundary") || null,
      landUseBoundaries: this.objects.filter((o) => o.type === "land_use_boundary"),
      plotBoundaries: this.objects.filter((o) => o.type === "plot_boundary"),
    };
  }

  handleAction(action) {
    if (action === "create_plot") {
      const activeProject = this.projectContextService.getActiveProject();
      if (!activeProject.isActive) {
        this.emitError("Najpierw wybierz lub utwórz projekt.");
        this.requestRender();
        return;
      }
      this.activeTool = new PlotBoundaryTool(this);
    }
    if (action === "create_site") this.activeTool = new SiteBoundaryTool(this);
    if (action === "create_land_use_line") this.activeTool = new LandUseBoundaryTool(this, "line");
    if (action === "create_land_use_polygon") this.activeTool = new LandUseBoundaryTool(this, "polygon");
    if (action === "finish") this.finishTool();
    if (action === "generate_site_from_plot") this.generateSiteBoundaryFromPlot();
  }

  finishTool() {
    this.activeTool?.commit?.();
    this.activeTool = null;
    this.requestRender();
  }

  emitError(message) {
    window.dispatchEvent(new CustomEvent("topbar:notify", {
      detail: { variant: "error", message },
    }));
  }

  snap(point) {
    const step = 12;
    return { x: Math.round(point.x / step) * step, y: Math.round(point.y / step) * step };
  }

  onCanvasClick(event) {
    const point = this.toCanvasPoint(event);
    if (this.activeTool) {
      this.activeTool.onClick(this.snap(point));
      return;
    }
    this.selectByPoint(point);
  }

  toCanvasPoint(event) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  create(object) {
    const normalized = normalizeBoundaryGeometry(object);
    if (normalized.type === "plot_boundary") {
      const active = this.projectContextService.getActiveProject();
      const geometry = this.plotBoundaryGeometryService.toGeoJsonPolygon(normalized.geometry);
      const area = this.plotBoundaryGeometryService.calculateBoundaryArea(normalized.geometry);
      const perimeter = this.plotBoundaryGeometryService.calculateBoundaryPerimeter(normalized.geometry);
      const plotBoundary = {
        id: normalized.id,
        projectId: active.projectId,
        type: "plot_boundary",
        name: normalized.label || "Granica działki",
        geometryType: "polygon",
        geometry,
        attributes: {
          ...(normalized.attributes || {}),
          area,
          perimeter,
        },
        isVisible: normalized.isVisible !== false,
        isLocked: !!normalized.isLocked,
        createdAt: normalized.createdAt || new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      const validation = this.plotBoundaryValidationService.validatePlotBoundary(plotBoundary.geometry, plotBoundary.projectId);
      if (!validation.valid) {
        this.emitError(validation.errors[0] || "Nie udało się zapisać granicy działki.");
        return;
      }
      this.plotBoundaryService.savePlotBoundary(plotBoundary).catch((error) => {
        this.emitError(error?.message || "Nie udało się zapisać granicy działki.");
      });
      normalized.attributes = {
        ...(normalized.attributes || {}),
        projectId: plotBoundary.projectId,
        area,
        perimeter,
      };
    }
    if (normalized.type === "site_boundary") {
      this.objects = this.objects.filter((item) => item.type !== "site_boundary");
    }
    this.objects.push(normalized);
    this.selectedId = normalized.id;
    this.requestRender();
  }

  edit(id, patch) {
    this.objects = this.objects.map((object) => (object.id === id ? { ...object, ...patch, updatedAt: new Date().toISOString() } : object));
    this.requestRender();
  }

  getPlotBoundaryItems() {
    return this.objects
      .filter((item) => item.type === "plot_boundary")
      .map((item, idx) => ({
        id: item.id,
        name: item.label || `Granica działki ${idx + 1}`,
        isVisible: item.isVisible !== false,
        isLocked: !!item.isLocked,
        area: Number(item.attributes?.area || 0),
        perimeter: Number(item.attributes?.perimeter || 0),
        isActive: item.id === this.selectedId,
      }));
  }

  selectBoundary(id) {
    this.selectedId = id || null;
    this.requestRender();
  }

  toggleBoundaryVisibility(id) {
    const target = this.objects.find((item) => item.id === id);
    if (!target) return;
    this.edit(id, { isVisible: target.isVisible === false });
  }

  toggleBoundaryLock(id) {
    const target = this.objects.find((item) => item.id === id);
    if (!target) return;
    this.edit(id, { isLocked: !target.isLocked });
  }

  async loadProjectBoundaries(projectContext) {
    this.projectContextService.setActiveProject(projectContext || {});
    const active = this.projectContextService.getActiveProject();
    this.activeTool = null;
    this.selectedId = null;
    this.drag = null;

    const nonPlotObjects = this.objects.filter((item) => item.type !== "plot_boundary");
    if (!active.isActive) {
      this.objects = nonPlotObjects;
      this.requestRender();
      return;
    }

    const saved = await this.plotBoundaryService.loadProjectPlotBoundaries(active.projectId);
    const plotObjects = saved.map((boundary) => createBoundaryObject("plot_boundary", {
      id: boundary.id,
      label: boundary.name || "Granica działki",
      geometryType: "polygon",
      geometry: this.plotBoundaryGeometryService.fromGeoJson(boundary.geometry),
      attributes: {
        ...(boundary.attributes || {}),
        projectId: boundary.projectId,
      },
      isVisible: boundary.isVisible !== false,
      isLocked: !!boundary.isLocked,
      createdAt: boundary.createdAt,
      updatedAt: boundary.updatedAt,
    }));
    this.objects = [...nonPlotObjects, ...plotObjects];
    this.requestRender();
  }

  async deleteBoundary(boundaryId) {
    const active = this.projectContextService.getActiveProject();
    if (!active.isActive) {
      this.emitError("Najpierw wybierz lub utwórz projekt.");
      return;
    }
    await this.plotBoundaryService.deletePlotBoundary(boundaryId, active.projectId);
    this.objects = this.objects.filter((item) => item.id !== boundaryId);
    if (this.selectedId === boundaryId) this.selectedId = null;
    this.requestRender();
  }

  moveVertex(objectId, index, point) {
    this.objects = this.objects.map((obj) => {
      if (obj.id !== objectId) return obj;
      const geometry = [...obj.geometry];
      geometry[index] = this.snap(point);
      return normalizeBoundaryGeometry({ ...obj, geometry });
    });
    this.requestRender();
  }

  insertVertex(objectId, index, point) {
    this.objects = this.objects.map((obj) => {
      if (obj.id !== objectId) return obj;
      const geometry = [...obj.geometry];
      geometry.splice(index, 0, this.snap(point));
      return normalizeBoundaryGeometry({ ...obj, geometry });
    });
    this.requestRender();
  }

  deleteVertex(objectId, index) {
    this.objects = this.objects.map((obj) => {
      if (obj.id !== objectId) return obj;
      const geometry = obj.geometry.filter((_, idx) => idx !== index);
      return normalizeBoundaryGeometry({ ...obj, geometry });
    });
    this.requestRender();
  }

  translate(objectId, dx, dy) {
    this.objects = this.objects.map((obj) => {
      if (obj.id !== objectId) return obj;
      const geometry = obj.geometry.map((point) => ({ x: point.x + dx, y: point.y + dy }));
      return normalizeBoundaryGeometry({ ...obj, geometry });
    });
    this.requestRender();
  }

  assignLandUse(landUseType) {
    const selected = this.objects.find((item) => item.id === this.selectedId);
    if (!selected || selected.type !== "land_use_boundary") return;
    this.edit(selected.id, {
      attributes: { ...selected.attributes, landUseType },
    });
  }

  generateSiteBoundaryFromPlot() {
    const plot = this.objects.find((item) => item.type === "plot_boundary");
    if (!plot) return;
    const generated = createBoundaryObject("site_boundary", {
      label: "Obszar analizy (buffer)",
      geometry: bufferGeometry(plot.geometry, 30),
      geometryType: "polygon",
      attributes: { purpose: "planning_scope", bufferFromPlot: 30 },
      createdBy: "system",
    });
    this.create(generated);
  }

  selectByPoint(point) {
    const hit = [...this.objects].reverse().find((object) => this.hitTest(object, point));
    this.selectedId = hit?.id || null;
    this.requestRender();
  }

  hitTest(object, point) {
    if (!object?.geometry?.length) return false;
    return object.geometry.some((vertex) => Math.hypot(vertex.x - point.x, vertex.y - point.y) <= 8);
  }

  startDrag(event) {
    const point = this.toCanvasPoint(event);
    const selected = this.objects.find((item) => item.id === this.selectedId);
    if (!selected) return;
    const vertexIdx = selected.geometry.findIndex((vertex) => Math.hypot(vertex.x - point.x, vertex.y - point.y) < 7);
    if (vertexIdx >= 0) {
      this.drag = { objectId: selected.id, vertexIdx };
      return;
    }
    if (this.hitTest(selected, point)) {
      this.drag = { objectId: selected.id, translate: true, origin: point };
    }
  }

  moveDrag(event) {
    if (!this.drag) return;
    const point = this.toCanvasPoint(event);
    if (Number.isInteger(this.drag.vertexIdx)) {
      this.moveVertex(this.drag.objectId, this.drag.vertexIdx, point);
      return;
    }
    if (this.drag.translate) {
      const dx = point.x - this.drag.origin.x;
      const dy = point.y - this.drag.origin.y;
      this.translate(this.drag.objectId, dx, dy);
      this.drag.origin = point;
    }
  }

  stopDrag() {
    this.drag = null;
  }
}

export {
  PlotBoundaryTool,
  LandUseBoundaryTool,
  SiteBoundaryTool,
};
