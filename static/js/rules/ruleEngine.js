// static/js/rules/ruleEngine.js

export function initRulesState(rulebook) {
  const out = {};
  for (const r of rulebook) {
    const baseParams =
      (r && typeof r.params === "object" && r.params) ? r.params : {};
    out[r.id] = {
      enabled: r.enabledByDefault ?? true,
      params: JSON.parse(JSON.stringify(baseParams)),
      usedLastRun: false
    };
  }
  return out;
}

export function getRuleById(rulebook, id) {
  return rulebook.find(r => r.id === id);
}

/**
 * ✅ APPLY WT (parametry §12)
 * Zwraca tylko parametry WT potrzebne dalej (a nie constraints do insetu).
 *
 * main.js używa tego tak:
 *   const outWT = applyWT({ rulebookWT: wtRules, rulesStateWT: state.rulesState.wt });
 *   state.wtParams = outWT.params;
 */
export function applyWT({ rulebookWT, rulesStateWT }) {
  const explain = [];

  // twarde defaulty (żeby NIGDY nie było undefined)
  let distWithOpeningsM = 4;
  let distWithoutOpeningsM = 3;

  // reset used flags
  for (const r of rulebookWT || []) {
    const st = rulesStateWT?.[r.id];
    if (st) st.usedLastRun = false;
  }

  // WT_12
  {
    const st = rulesStateWT?.["WT_12"];
    if (st && st.enabled !== false) {
      st.usedLastRun = true;

      const dOpen = Number.isFinite(+st.params?.distWithOpeningsM) ? +st.params.distWithOpeningsM : 4;
      const dNo   = Number.isFinite(+st.params?.distWithoutOpeningsM) ? +st.params.distWithoutOpeningsM : 3;

      distWithOpeningsM = Math.max(0, dOpen);
      distWithoutOpeningsM = Math.max(0, dNo);

      explain.push({
        summary: `WT §12: parametry odsadzeń: ${distWithoutOpeningsM}m (bez okien) / ${distWithOpeningsM}m (z oknami).`
      });
    } else {
      explain.push({
        summary: `WT §12: wyłączony → używam domyślnych ${distWithoutOpeningsM}m / ${distWithOpeningsM}m tylko jako fallback (nie powinno się liczyć).`
      });
    }
  }

  return {
    params: { distWithOpeningsM, distWithoutOpeningsM },
    explain
  };
}

/**
 * MPZP/WZ: oblicza limity (maxFootprintArea itd.)
 * Uwaga: NIE "clampujemy" geometrii tutaj. To tylko liczy limity.
 */
export function applyMpzpWzLimits({
  plotArea,
  rulebookMPZP,
  rulesStateMPZP
}) {
  const explain = [];
  const debug = {
    coverageWasClamped: false,
    pbcWasClamped: false,
    coverageK: 1,
    pbcK: 1
  };

  let maxByCoverage = Infinity;
  let maxByPbc = Infinity;

  // reset used flags
  for (const rule of rulebookMPZP || []) {
    const st = rulesStateMPZP?.[rule.id];
    if (st) st.usedLastRun = false;
  }

  // coverage max
  {
    const st = rulesStateMPZP?.["MPZP_COVERAGE_MAX"];
    if (st && st.enabled !== false) {
      st.usedLastRun = true;

      let pct = Number(st.params?.coverageMaxPercent);
      if (!Number.isFinite(pct)) pct = 30;
      pct = Math.max(0, Math.min(100, pct));

      maxByCoverage = Number.isFinite(plotArea) ? plotArea * (pct / 100) : Infinity;
      explain.push({ summary: `MPZP/WZ: maks. pow. zabudowy ${pct.toFixed(0)}% → ${maxByCoverage.toFixed(2)} m²` });
    }
  }

  // PBC min
  {
    const st = rulesStateMPZP?.["MPZP_PBC_MIN"];
    if (st && st.enabled !== false) {
      st.usedLastRun = true;

      let pct = Number(st.params?.pbcMinPercent);
      if (!Number.isFinite(pct)) pct = 30;
      pct = Math.max(0, Math.min(100, pct));

      maxByPbc = Number.isFinite(plotArea) ? plotArea * (1 - pct / 100) : Infinity;
      explain.push({ summary: `MPZP/WZ: PBC min ${pct.toFixed(0)}% → max zabudowy ${maxByPbc.toFixed(2)} m²` });
    }
  }

  let maxFootprintArea = Math.min(maxByCoverage, maxByPbc);
  if (!Number.isFinite(maxFootprintArea)) maxFootprintArea = Infinity;
  if (maxFootprintArea < 0) maxFootprintArea = 0;

  return {
    limits: { maxFootprintArea },
    explain,
    debug
  };
}
