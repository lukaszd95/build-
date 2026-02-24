// static/js/designEngine/shapeGenerator.js
import { variableInsetLotPolygon, polygonAreaAbs } from "../geometry/variableInset.js";

/**
 * Cel:
 * - wygenerować kilka wariantów footprintu wewnątrz envelope (obszar dopuszczalny po WT),
 * - twardy warunek: wariant musi być inside(envelope),
 * - twardy warunek: jeśli maxFootprintArea jest skończone -> area <= maxFootprintArea,
 * - zawsze zwrócić przynajmniej 1 wariant, jeśli envelope istnieje.
 *
 * Najważniejsza poprawka:
 * - Poprawny binary search w insetEnvelopeToMaxArea:
 *   rosnący inset => malejące pole.
 *   Szukamy największego pola <= maxArea, czyli minimalnego insetu który spełnia limit.
 */

function centroid(poly) {
  let A = 0, Cx = 0, Cy = 0;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i];
    const q = poly[(i + 1) % poly.length];
    const cross = p.x * q.y - q.x * p.y;
    A += cross;
    Cx += (p.x + q.x) * cross;
    Cy += (p.y + q.y) * cross;
  }
  A *= 0.5;
  if (Math.abs(A) < 1e-9) {
    const s = poly.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 });
    return { x: s.x / poly.length, y: s.y / poly.length };
  }
  return { x: Cx / (6 * A), y: Cy / (6 * A) };
}

function bounds(poly) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of poly) {
    minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y);
  }
  return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };
}

function rotatePoint(p, c, ang) {
  const s = Math.sin(ang), co = Math.cos(ang);
  const dx = p.x - c.x, dy = p.y - c.y;
  return { x: c.x + dx * co - dy * s, y: c.y + dx * s + dy * co };
}

function rotatePoly(poly, ang) {
  const c = centroid(poly);
  return poly.map(p => rotatePoint(p, c, ang));
}

function pointInPolygon(pt, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    const intersect =
      ((yi > pt.y) !== (yj > pt.y)) &&
      (pt.x < (xj - xi) * (pt.y - yi) / ((yj - yi) || 1e-12) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function polygonInside(poly, envelope) {
  return poly.every(pt => pointInPolygon(pt, envelope));
}

function makeRectCentered(cx, cy, w, h) {
  const hw = w / 2, hh = h / 2;
  return [
    { x: cx - hw, y: cy - hh },
    { x: cx + hw, y: cy - hh },
    { x: cx + hw, y: cy + hh },
    { x: cx - hw, y: cy + hh }
  ];
}

/**
 * ✅ BEZPIECZNE docięcie envelope do maxArea:
 * - robimy stały inset (taki sam na wszystkich krawędziach)
 * - dobieramy go binarnie tak, by area(inset) <= maxArea i było jak największe.
 *
 * Monotoniczność:
 * - większy inset => mniejsze pole (albo polygon znika)
 * Szukamy minimalnego insetu, który daje pole <= maxArea.
 */
function insetEnvelopeToMaxArea(envelope, maxArea, opts = {}) {
  const envArea = polygonAreaAbs(envelope);
  if (!Number.isFinite(maxArea) || maxArea <= 0) return null;
  if (envArea <= maxArea + 1e-6) return envelope;

  const resolution = opts.resolution ?? 0.25;
  const simplifyEps = opts.simplifyEps ?? 0.35;

  const b = bounds(envelope);

  // Startowa górna granica — potem ewentualnie podbijemy jeśli wciąż za duże pole
  let hi = Math.max(0, Math.min(b.w, b.h) * 0.49);
  let lo = 0;

  // Upewnij się, że przy hi pole faktycznie spada poniżej maxArea (albo polygon znika).
  // Jeśli nadal jest > maxArea, to znaczy że potrzeba jeszcze większego insetu,
  // ale fizycznie i tak zbliżamy się do zaniku wielokąta, więc zwiększamy hi ostrożnie.
  for (let guard = 0; guard < 6; guard++) {
    const testSetb = new Array(envelope.length).fill(hi);
    let testPoly = null;
    try {
      testPoly = variableInsetLotPolygon(envelope, testSetb, { resolution, simplifyEps });
      if (!testPoly || testPoly.length < 3) testPoly = null;
    } catch {
      testPoly = null;
    }
    if (!testPoly) break; // zanikło -> hi jest wystarczająco duże
    const a = polygonAreaAbs(testPoly);
    if (a <= maxArea + 1e-6) break; // hi daje już <= maxArea
    hi = hi * 1.25; // spróbuj większego (rzadko potrzebne)
  }

  let best = null;

  for (let iter = 0; iter < 32; iter++) {
    const mid = (lo + hi) / 2;
    const setb = new Array(envelope.length).fill(mid);

    let poly = null;
    try {
      poly = variableInsetLotPolygon(envelope, setb, { resolution, simplifyEps });
      if (!poly || poly.length < 3) poly = null;
    } catch {
      poly = null;
    }

    if (!poly) {
      // inset za duży -> cofnij hi
      hi = mid;
      continue;
    }

    const a = polygonAreaAbs(poly);

    if (a > maxArea + 1e-6) {
      // inset za mały -> zwiększ lo
      lo = mid;
    } else {
      // ✅ spełnia limit -> zapamiętaj i próbuj mniejszego insetu, żeby pole było większe
      best = poly;
      hi = mid;
    }
  }

  return best;
}

function normalizeMaxArea(maxFootprintArea) {
  if (!Number.isFinite(maxFootprintArea)) return Infinity;
  if (maxFootprintArea <= 0) return 0;
  return maxFootprintArea;
}

/**
 * public API
 */
export function generateBuildingVariants({
  envelope,
  plotPolygon,
  limits,
  wtParams,
  edgeOpeningsMode,
  objective
}) {
  const explain = [];
  if (!envelope || envelope.length < 3) {
    return { variants: [], best: null, explain: [{ summary: "Brak envelope (WT) — generator nie ma gdzie projektować." }] };
  }

  const envArea = polygonAreaAbs(envelope);
  const maxA = normalizeMaxArea(limits?.maxFootprintArea);

  const effectiveMaxA = Math.min(maxA, envArea);

  explain.push({ summary: `Generator: envelope area=${envArea.toFixed(2)} m², maxArea=${Number.isFinite(maxA) ? maxA.toFixed(2) : "∞"} m², effectiveMax=${effectiveMaxA.toFixed(2)} m²` });

  const variants = [];

  // (1) Wariant gwarantowany: envelope
  if (envArea <= effectiveMaxA + 1e-6) {
    variants.push({
      name: "Maksymalny (envelope)",
      poly: envelope,
      area: envArea,
      meta: {}
    });
  }

  // (2) Wariant gwarantowany: envelope docięty do maxArea bezpiecznym insetem
  if (effectiveMaxA < envArea - 1e-6) {
    const cut = insetEnvelopeToMaxArea(envelope, effectiveMaxA, { resolution: 0.25, simplifyEps: 0.35 });
    if (cut && cut.length >= 3) {
      const a = polygonAreaAbs(cut);
      variants.push({
        name: "Maksymalny (docięty do MPZP/WZ)",
        poly: cut,
        area: a,
        meta: {}
      });
      explain.push({ summary: `Generator: docięto envelope do maxArea insetem → area=${a.toFixed(2)} m²` });
    } else {
      explain.push({ summary: `Generator: nie udało się dociąć envelope do maxArea (inset wygasił wielokąt).` });
    }
  }

  // (3) „Bardziej prostokątny”: envelope -> lekki inset
  {
    const b = bounds(envelope);
    const inset = new Array(envelope.length).fill(Math.min(b.w, b.h) * 0.06);
    let poly = null;
    try {
      poly = variableInsetLotPolygon(envelope, inset, { resolution: 0.25, simplifyEps: 0.35 });
      if (!poly || poly.length < 3) poly = null;
    } catch {
      poly = null;
    }

    if (poly) {
      let a = polygonAreaAbs(poly);
      let final = poly;

      if (a > effectiveMaxA + 1e-6) {
        const cut = insetEnvelopeToMaxArea(poly, effectiveMaxA, { resolution: 0.25, simplifyEps: 0.35 });
        if (cut) {
          final = cut;
          a = polygonAreaAbs(cut);
        } else {
          final = null;
        }
      }

      if (final && polygonInside(final, envelope)) {
        variants.push({ name: "Bardziej prostokątny", poly: final, area: a, meta: {} });
      }
    }
  }

  // (4) „Bardziej równoległy do granic”: kilka prób przez różne insettingi (MVP)
  {
    const angles = [0, Math.PI / 12, -Math.PI / 12, Math.PI / 6, -Math.PI / 6];
    for (const ang of angles) {
      const envR = rotatePoly(envelope, ang);
      const b = bounds(envR);

      const extra = Math.min(b.w, b.h) * 0.08;
      const setb = new Array(envelope.length).fill(extra);

      let poly = null;
      try {
        poly = variableInsetLotPolygon(envelope, setb, { resolution: 0.25, simplifyEps: 0.35 });
        if (!poly || poly.length < 3) poly = null;
      } catch {
        poly = null;
      }

      if (!poly) continue;

      let a = polygonAreaAbs(poly);
      let final = poly;

      if (a > effectiveMaxA + 1e-6) {
        const cut = insetEnvelopeToMaxArea(poly, effectiveMaxA, { resolution: 0.25, simplifyEps: 0.35 });
        if (cut) {
          final = cut;
          a = polygonAreaAbs(cut);
        } else {
          final = null;
        }
      }

      if (final && polygonInside(final, envelope)) {
        variants.push({ name: "Bardziej równoległy do granic", poly: final, area: a, meta: {} });
        break;
      }
    }
  }

  const safe = variants.filter(v => v.poly && v.poly.length >= 3 && polygonInside(v.poly, envelope));
  const ok = safe.filter(v => v.area <= effectiveMaxA + 1e-6);

  explain.push({ summary: `Generator: wygenerowano ${variants.length} wariantów, po inside=${safe.length}, po maxArea=${ok.length}` });

  let best = null;

  if (ok.length > 0) {
    best = ok.slice().sort((a, b) => b.area - a.area)[0];
  } else if (safe.length > 0) {
    best = safe.slice().sort((a, b) => b.area - a.area)[0];
    explain.push({ summary: `Generator: brak wariantu spełniającego maxArea, pokazuję największy inside(envelope) poglądowo.` });
  } else {
    explain.push({ summary: `Generator: brak jakiegokolwiek wariantu inside(envelope).` });
  }

  return {
    variants: ok,
    best,
    explain
  };
}
