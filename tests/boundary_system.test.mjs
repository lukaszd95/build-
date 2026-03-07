import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function loadBoundaryModule() {
  const source = await readFile(new URL("../static/js/boundary/boundarySystem.js", import.meta.url), "utf8");
  const dataUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
  return import(dataUrl);
}

test("boundaryObjectDefinitions expose Group A boundaries", async () => {
  const mod = await loadBoundaryModule();
  assert.ok(mod.boundaryObjectDefinitions.plot_boundary);
  assert.ok(mod.boundaryObjectDefinitions.land_use_boundary);
  assert.ok(mod.boundaryObjectDefinitions.site_boundary);
});

test("validation and normalization keep polygon consistent", async () => {
  const mod = await loadBoundaryModule();
  const polygon = mod.createBoundaryObject("plot_boundary", {
    geometry: [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
      { x: 0, y: 0 },
    ],
  });
  const normalized = mod.normalizeBoundaryGeometry(polygon);
  assert.equal(normalized.geometry.length, 4);
  const validation = mod.validateBoundaryTopology(normalized);
  assert.equal(validation.valid, true);
});

test("boundary analysis returns plot metrics and buildable area", async () => {
  const mod = await loadBoundaryModule();
  const plot = mod.createBoundaryObject("plot_boundary", {
    geometry: [
      { x: 0, y: 0 },
      { x: 20, y: 0 },
      { x: 20, y: 20 },
      { x: 0, y: 20 },
    ],
  });
  const landUse = mod.createBoundaryObject("land_use_boundary", {
    geometryType: "polygon",
    geometry: [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 20 },
      { x: 0, y: 20 },
    ],
    attributes: { landUseType: "building" },
  });
  const site = mod.createBoundaryObject("site_boundary", {
    geometry: [
      { x: -10, y: -10 },
      { x: 30, y: -10 },
      { x: 30, y: 30 },
      { x: -10, y: 30 },
    ],
  });

  const service = new mod.BoundaryAnalysisService();
  const summary = service.summarize({
    plotBoundary: plot,
    landUseBoundaries: [landUse],
    siteBoundary: site,
  });

  assert.equal(summary.plotArea, 400);
  assert.equal(summary.relationPlotToSite, true);
  assert.ok(summary.buildableArea > 0);
});

test("plot boundary validation enforces project assignment and closed polygon", async () => {
  const mod = await loadBoundaryModule();
  const invalid = mod.validatePlotBoundary({
    type: "Polygon",
    coordinates: [[[0, 0], [10, 0], [0, 10]]],
  }, "");
  assert.equal(invalid.valid, false);
  assert.ok(invalid.errors.some((msg) => msg.includes("zamknięta")));
  assert.ok(invalid.errors.some((msg) => msg.includes("przypisana do projektu")));
});

test("plot boundary service keeps boundaries isolated by project", async () => {
  const mod = await loadBoundaryModule();
  const memory = new Map();
  const storage = {
    getItem(key) { return memory.has(key) ? memory.get(key) : null; },
    setItem(key, value) { memory.set(key, value); },
  };
  const service = new mod.PlotBoundaryService({ storage });

  await service.savePlotBoundary({
    id: "b-1",
    projectId: "project-a",
    type: "plot_boundary",
    name: "Granica A",
    geometryType: "polygon",
    geometry: { type: "Polygon", coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] },
    attributes: {},
    isVisible: true,
    isLocked: false,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });

  await service.savePlotBoundary({
    id: "b-2",
    projectId: "project-b",
    type: "plot_boundary",
    name: "Granica B",
    geometryType: "polygon",
    geometry: { type: "Polygon", coordinates: [[[0, 0], [20, 0], [20, 10], [0, 10], [0, 0]]] },
    attributes: {},
    isVisible: true,
    isLocked: false,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });

  const projectA = await service.loadProjectPlotBoundaries("project-a");
  const projectB = await service.loadProjectPlotBoundaries("project-b");

  assert.equal(projectA.length, 1);
  assert.equal(projectB.length, 1);
  assert.equal(projectA[0].id, "b-1");
  assert.equal(projectB[0].id, "b-2");
});
