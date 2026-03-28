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
  return context.window.__AT_INDUSTRY_UI__;
}

test("renders badge class for known industry", async () => {
  const ui = await loadUiApi();
  assert.match(ui.getIndustryBadgeClass("Architektura"), /violet/);
});

test("renders unknown state badge", async () => {
  const ui = await loadUiApi();
  assert.match(ui.getIndustryBadgeClass("Nieznana"), /zinc/);
  assert.equal(ui.getIndustryLabel({ detectedIndustry: "Nieznana", processingStatus: "INDUSTRY_CLASSIFIED" }), "Nieznana");
});

test("renders loading and error states", async () => {
  const ui = await loadUiApi();
  assert.equal(ui.getIndustryLabel({ processingStatus: "CLASSIFYING_INDUSTRY" }), "W trakcie rozpoznawania");
  assert.equal(ui.getIndustryLabel({ processingStatus: "INDUSTRY_CLASSIFICATION_FAILED" }), "Błąd klasyfikacji");
});

test("details view includes confidence and multiple industries", async () => {
  const ui = await loadUiApi();
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

test("integration with backend-like payload can be displayed", async () => {
  const ui = await loadUiApi();
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
