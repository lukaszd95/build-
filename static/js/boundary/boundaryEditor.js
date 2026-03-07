import {
  BoundaryToolbar,
  BoundaryPropertiesPanel,
  PlotBoundaryRenderer,
  LandUseBoundaryRenderer,
  SiteBoundaryRenderer,
  PlotBoundaryTool,
  LandUseBoundaryTool,
  SiteBoundaryTool,
  BoundaryValidationService,
  BoundaryReasoningService,
  BoundaryAnalysisService,
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
    this.wrapper.className = "h-full space-y-2";

    this.toolbar = new BoundaryToolbar({ onAction: (action) => this.handleAction(action) }).render();
    this.canvasWrap = document.createElement("div");
    this.canvasWrap.className = "relative h-[320px] overflow-hidden rounded-xl border border-gray-200 bg-white";
    this.canvas = document.createElement("canvas");
    this.canvas.className = "absolute inset-0 h-full w-full";
    this.canvasWrap.appendChild(this.canvas);

    this.properties = new BoundaryPropertiesPanel({ onAssignLandUse: (landUseType) => this.assignLandUse(landUseType) });

    this.wrapper.append(this.toolbar, this.canvasWrap, this.properties.render());
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

    const selected = this.objects.find((o) => o.id === this.selectedId) || null;
    const normalized = selected ? normalizeBoundaryGeometry(selected) : null;
    const topoValidation = normalized ? validateBoundaryTopology(normalized) : { valid: true, issues: [], warnings: [] };
    const grouped = this.groupedBoundaries();
    const relationValidation = this.validation.validateRelations(grouped);
    const analysis = this.analysis.summarize(grouped);
    const reasoning = this.reasoning.evaluate(grouped);
    this.properties.update({
      selected,
      validation: {
        valid: topoValidation.valid && relationValidation.valid,
        issues: [...topoValidation.issues, ...relationValidation.issues],
        warnings: [...topoValidation.warnings, ...relationValidation.warnings],
      },
      analysis,
      reasoning,
    });

    this.onStateChange?.({ grouped, analysis, reasoning, selected });
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
    };
  }

  handleAction(action) {
    if (action === "create_plot") this.activeTool = new PlotBoundaryTool(this);
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
      this.objects = this.objects.filter((item) => item.type !== "plot_boundary");
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
  BoundaryToolbar,
  PlotBoundaryTool,
  LandUseBoundaryTool,
  SiteBoundaryTool,
  BoundaryPropertiesPanel,
};
