import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";

async function loadUiApi() {
  const source = await readFile(new URL("../static/js/atModule.js", import.meta.url), "utf8");
  const context = {
    window: {},
    document: {
      getElementById() { return null; },
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return {
    industry: context.window.__AT_INDUSTRY_UI__,
    project: context.window.__AT_PROJECT_IDENTITY_UI__,
  };
}

test("renders badge class for known industry", async () => {
  const { industry: ui } = await loadUiApi();
  assert.match(ui.getIndustryBadgeClass("Architektura"), /violet/);
});

test("renders unknown state badge", async () => {
  const { industry: ui } = await loadUiApi();
  assert.match(ui.getIndustryBadgeClass("Nieznana"), /zinc/);
  assert.equal(ui.getIndustryLabel({ detectedIndustry: "Nieznana", processingStatus: "INDUSTRY_CLASSIFIED" }), "Nieznana");
});

test("renders loading and error states", async () => {
  const { industry: ui } = await loadUiApi();
  assert.equal(ui.getIndustryLabel({ processingStatus: "CLASSIFYING_INDUSTRY" }), "W trakcie rozpoznawania");
  assert.equal(ui.getIndustryLabel({ processingStatus: "INDUSTRY_CLASSIFICATION_FAILED" }), "Błąd klasyfikacji");
});

test("details view includes confidence and multiple industries", async () => {
  const { industry: ui } = await loadUiApi();
  const text = ui.buildIndustryDetailsText({
    detectedIndustry: "Wiele branż",
    processingStatus: "INDUSTRY_CLASSIFIED",
    detectedIndustries: ["Elektryka", "Wod-kan"],
    industryConfidence: 0.73,
    industryClassificationReason: "Wykryto silne sygnały dla kilku branż.",
    industrySignals: [{ phrase: "obwody" }, { phrase: "kanalizacja" }],
  });
  assert.match(text, /Wiele branż/);
  assert.match(text, /Elektryka, Wod-kan/);
  assert.match(text, /73%/);
});

test("renders content type badge and mixed details", async () => {
  const { industry: ui } = await loadUiApi();
  assert.match(ui.getContentTypeBadgeClass("Rzut"), /blue/);
  const details = ui.buildContentTypeDetailsText({
    detectedContentType: "Rzut",
    detectedContentTypes: ["Rzut", "Przekrój"],
    contentTypeConfidence: 0.61,
    contentTypeReason: "Dokument zawiera wiele istotnych typów stron (dokument mieszany).",
    contentTypePagesSummary: { "Rzut": 2, "Przekrój": 1 },
    pageContentResults: [{ pageNumber: 1, detectedContentType: "Rzut", confidence: 0.74, isUserOverridden: false, topPositiveSignals: [{ contentType: "Rzut", phrase: "rzut parteru" }], topConflictSignals: [{ contentType: "Przekrój", phrase: "silne_sygnały_pionowe_osłabiają_rzut" }] }],
    isMixedContent: true,
  });
  assert.match(details, /Rzut/);
  assert.match(details, /mieszany/i);
  assert.match(details, /61%/);
});

test("renders unknown content type state", async () => {
  const { industry: ui } = await loadUiApi();
  assert.equal(ui.normalizeContentType(""), "Inna / Nieznana");
  assert.match(ui.getContentTypeBadgeClass("Inna / Nieznana"), /zinc/);
});

test("integration with backend-like payload can be displayed", async () => {
  const { industry: ui } = await loadUiApi();
  const payload = {
    detectedIndustry: "PZT",
    processingStatus: "INDUSTRY_CLASSIFIED",
    detectedIndustries: ["PZT"],
    industryConfidence: 0.88,
    industryClassificationReason: "Najsilniejsze dopasowania wskazują na branżę PZT.",
    industrySignals: [{ phrase: "projekt zagospodarowania terenu" }],
  };
  assert.equal(ui.getIndustryLabel(payload), "PZT");
  assert.match(ui.buildIndustryDetailsText(payload), /PZT/);
});


test("content type details include diagnostics and origin", async () => {
  const { industry: ui } = await loadUiApi();
  const details = ui.buildContentTypeDetailsText({
    detectedContentType: "Rzut",
    contentTypeConfidence: 0.67,
    pageContentResults: [{ pageNumber: 2, detectedContentType: "Przekrój", confidence: 0.51, isUserOverridden: true, topPositiveSignals: [{ contentType: "Przekrój", phrase: "przekroj a-a" }], topConflictSignals: [] }],
  });
  assert.match(details, /Diagnostyka/);
  assert.match(details, /user/);
});

test("project identity summary renders title, location and confidence", async () => {
  const { project: ui } = await loadUiApi();
  const summary = ui.buildProjectIdentitySummary({
    projectTitleDetected: "Budowa budynku mieszkalnego jednorodzinnego",
    investmentAddressDetected: "ul. Lipowa 12, Kraków",
    projectIdentityConfidence: 0.82,
  });
  assert.match(summary, /Budowa budynku/);
  assert.match(summary, /Lipowa 12/);
  assert.match(summary, /82%/);
});

test("project identity explainability shows rejected office address", async () => {
  const { project: ui } = await loadUiApi();
  const details = ui.buildRejectedOfficeInfo({
    projectIdentitySignals: {
      rejectedOfficeAddressSignals: [{ value: "ul. Kwiatowa 5, Kraków" }],
    },
  });
  assert.match(details, /Kwiatowa 5/);
});

test("project identity diagnostics show candidates and partial plots", async () => {
  const { project: ui } = await loadUiApi();
  const details = ui.buildProjectIdentityDiagnostics({
    projectIdentitySignals: {
      plotNumberCandidates: [{ value: "12/4, 12/5", confidence: 0.78 }],
      projectTitleCandidates: [{ value: "Budowa budynku..." }],
      investmentAddressCandidates: [{ value: "Kraków, dz. 12/4" }],
      documentProjectIdentityCandidates: [{ composedFromMultipleSources: true }],
      rejectedProjectTitleCandidates: [{ value: "Projekt budowlany" }],
      rejectedInvestmentAddressCandidates: [],
      rejectedPlotNumberCandidates: [{ value: "działki ???" }],
    },
  });
  assert.match(details, /Plot candidates/);
  assert.match(details, /multiple sources: tak/);
  assert.match(details, /Rejected title\/address\/plot: 1\/0\/1/);
});

test("line extraction stats aggregate horizontal vertical diagonal", async () => {
  const { project: ui } = await loadUiApi();
  const stats = ui.buildLineExtractionStats({
    extractionSource: "vector",
    extractionConfidence: 0.78,
    lines: [
      { angle: 0, length: 100 },
      { angle: 90, length: 80 },
      { angle: 44, length: 60 },
    ],
  });
  assert.equal(stats.lineCount, 3);
  assert.equal(stats.horizontal, 1);
  assert.equal(stats.vertical, 1);
  assert.equal(stats.diagonal, 1);
  assert.equal(stats.source, "vector");
});
