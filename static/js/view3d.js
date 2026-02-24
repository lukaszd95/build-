// Pseudo-3D (offline) — izometryczny renderer bez Three.js.
// Dodano: obrót myszką (LPM przeciągnij), zoom kółkiem, HUD wymiarów + skalówka.

let canvas, ctx, containerEl;
let lastModel = null;

let yaw = 0.9;        // obrót wokół osi Z (rad)
let pitch = 0.85;     // pochylenie (rad)
let zoom = 1.0;

let isRotating = false;
let dragStart = { x: 0, y: 0, yaw: 0, pitch: 0 };

function ensureCanvas() {
  if (!containerEl) return;
  if (canvas) return;

  canvas = document.createElement("canvas");
  canvas.id = "isoCanvas";
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.display = "block";
  canvas.style.borderRadius = "12px";
  canvas.style.cursor = "grab";
  containerEl.innerHTML = "";
  containerEl.appendChild(canvas);

  ctx = canvas.getContext("2d");

  canvas.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    isRotating = true;
    canvas.style.cursor = "grabbing";
    dragStart = { x: e.clientX, y: e.clientY, yaw, pitch };
  });

  window.addEventListener("mousemove", (e) => {
    if (!isRotating) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    yaw = dragStart.yaw + dx * 0.006;
    pitch = dragStart.pitch + dy * 0.006;
    pitch = Math.max(0.2, Math.min(1.35, pitch)); // clamp
    if (lastModel) draw(lastModel);
  });

  window.addEventListener("mouseup", () => {
    if (!isRotating) return;
    isRotating = false;
    canvas.style.cursor = "grab";
  });

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = 1.12;
    if (e.deltaY < 0) zoom = Math.min(zoom * factor, 6);
    else zoom = Math.max(zoom / factor, 0.25);
    if (lastModel) draw(lastModel);
  }, { passive: false });
}

function resize() {
  if (!containerEl || !canvas) return;
  const r = containerEl.getBoundingClientRect();
  canvas.width = Math.max(10, Math.floor(r.width));
  canvas.height = Math.max(10, Math.floor(r.height));
  if (lastModel) draw(lastModel);
}

function rotZ(x, y, a) {
  const ca = Math.cos(a), sa = Math.sin(a);
  return { x: x * ca - y * sa, y: x * sa + y * ca };
}

function rotX(y, z, a) {
  const ca = Math.cos(a), sa = Math.sin(a);
  return { y: y * ca - z * sa, z: y * sa + z * ca };
}

function project(p, z, s, origin) {
  // yaw (Z), potem pitch (X)
  const rz = rotZ(p.x, p.y, yaw);
  let x = rz.x, y = rz.y, zz = z;
  const rx = rotX(y, zz, pitch);
  y = rx.y; zz = rx.z;

  // prosty ortho z "wysokością"
  return { x: origin.x + x * s, y: origin.y + (y * s) - (zz * s) };
}

function polygonBoundsXY(poly) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of poly) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  }
  return { minX, maxX, minY, maxY, w: maxX - minX, h: maxY - minY };
}

function boundsProj(poly, z, s, origin) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of poly) {
    const q = project(p, z, s, origin);
    minX = Math.min(minX, q.x); maxX = Math.max(maxX, q.x);
    minY = Math.min(minY, q.y); maxY = Math.max(maxY, q.y);
  }
  return { minX, maxX, minY, maxY, w: maxX - minX, h: maxY - minY };
}

function drawPolygon(poly, z, s, origin, stroke, fill, dash, width = 2.5) {
  if (!poly || poly.length < 3) return;
  ctx.save();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = width;
  if (dash) ctx.setLineDash(dash);
  if (fill) ctx.fillStyle = fill;

  ctx.beginPath();
  poly.forEach((p, i) => {
    const q = project(p, z, s, origin);
    if (i === 0) ctx.moveTo(q.x, q.y);
    else ctx.lineTo(q.x, q.y);
  });
  ctx.closePath();
  if (fill) ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawLabels(poly, labels, z, s, origin, color) {
  if (!poly || !labels || poly.length !== labels.length) return;
  ctx.save();
  ctx.fillStyle = color;
  ctx.font = "bold 14px Arial";
  for (let i = 0; i < poly.length; i++) {
    const q = project(poly[i], z, s, origin);
    ctx.fillText(labels[i], q.x + 5, q.y - 5);
  }
  ctx.restore();
}

function drawScaleBar(pxPerM) {
  const targetPx = 120;
  const steps = [0.5, 1, 2, 5, 10, 20, 50];
  let bestM = steps[0], bestDiff = Infinity;
  for (const m of steps) {
    const diff = Math.abs(m * pxPerM - targetPx);
    if (diff < bestDiff) { bestDiff = diff; bestM = m; }
  }
  const lenPx = Math.max(60, Math.min(220, bestM * pxPerM));

  const pad = 14;
  const x0 = canvas.width - pad - lenPx;
  const y0 = canvas.height - pad - 18;

  ctx.save();
  ctx.fillStyle = "rgba(243,244,246,0.92)";
  ctx.strokeStyle = "rgba(209,213,219,1)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(x0 - 10, y0 - 18, lenPx + 20, 34, 10);
  ctx.fill();
  ctx.stroke();

  ctx.strokeStyle = "#111827";
  ctx.lineWidth = 6;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x0 + lenPx, y0);
  ctx.stroke();

  ctx.fillStyle = "#111827";
  ctx.font = "12px Arial";
  ctx.fillText(`${bestM} m`, x0, y0 - 6);
  ctx.font = "10px Arial";
  ctx.fillStyle = "#6b7280";
  ctx.fillText(`zoom ${zoom.toFixed(2)}×`, x0, y0 + 14);
  ctx.restore();
}

function drawSizeHUD(footprint, height) {
  const b = polygonBoundsXY(footprint);
  const w = b.w, h = b.h;

  ctx.save();
  ctx.fillStyle = "rgba(243,244,246,0.92)";
  ctx.strokeStyle = "rgba(209,213,219,1)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(12, 12, 270, 78, 12);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "#111827";
  ctx.font = "12px Arial";
  ctx.fillText(`Budynek (MVP)`, 22, 32);
  ctx.font = "11px Arial";
  ctx.fillStyle = "#374151";
  ctx.fillText(`Wymiary XY (bbox): ${w.toFixed(2)} m × ${h.toFixed(2)} m`, 22, 52);
  ctx.fillText(`Wysokość: ${height.toFixed(2)} m`, 22, 68);
  ctx.fillStyle = "#6b7280";
  ctx.font = "10px Arial";
  ctx.fillText(`Obrót: przeciągnij LPM · Zoom: kółko`, 22, 84);
  ctx.restore();
}

function draw(model) {
  if (!ctx || !canvas) return;
  const { footprint, heightTotal, lot, lotLabels } = model;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (!lot || lot.length < 3) {
    ctx.fillStyle = "#111827";
    ctx.font = "14px Arial";
    ctx.fillText("Brak obrysu działki.", 20, 30);
    return;
  }

  // Fit scale by lot bbox in XY, then projection centering
  const bXY = polygonBoundsXY(lot);
  const usableW = canvas.width * 0.80;
  const usableH = canvas.height * 0.75;
  let s = Math.max(2, Math.min(usableW / Math.max(1e-6, bXY.w), usableH / Math.max(1e-6, bXY.h)));
  s *= zoom;

  const bProj = boundsProj(lot, 0, s, { x: 0, y: 0 });
  const origin = {
    x: canvas.width / 2 - (bProj.minX + bProj.w / 2),
    y: canvas.height / 2 - (bProj.minY + bProj.h / 2) + canvas.height * 0.10
  };

  // Ground grid
  ctx.save();
  ctx.strokeStyle = "rgba(148,163,184,0.20)";
  ctx.lineWidth = 1;
  const gridStep = 5;
  const startX = Math.floor(bXY.minX / gridStep) * gridStep;
  const startY = Math.floor(bXY.minY / gridStep) * gridStep;

  for (let x = startX; x <= bXY.maxX + gridStep; x += gridStep) {
    const a = project({ x, y: bXY.minY - gridStep }, 0, s, origin);
    const d = project({ x, y: bXY.maxY + gridStep }, 0, s, origin);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(d.x, d.y); ctx.stroke();
  }
  for (let y = startY; y <= bXY.maxY + gridStep; y += gridStep) {
    const a = project({ x: bXY.minX - gridStep, y }, 0, s, origin);
    const d = project({ x: bXY.maxX + gridStep, y }, 0, s, origin);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(d.x, d.y); ctx.stroke();
  }
  ctx.restore();

  // Lot outline + labels
  drawPolygon(lot, 0, s, origin, "#f97316", null, [10, 6], 2);
  drawLabels(lot, lotLabels, 0, s, origin, "#f97316");
  drawLotLabel(lot, 0, s, origin, "Granica działki", "#f97316");

  if (!footprint || footprint.length < 3) {
    ctx.fillStyle = "#6b7280";
    ctx.font = "12px Arial";
    ctx.fillText("Brak footprintu budynku (sprawdź parametry).", 20, 52);
    drawScaleBar(s);
    return;
  }

  const H = Math.max(1, heightTotal || 6);

  // Footprint shadow on ground
  drawPolygon(footprint, 0, s, origin, "rgba(17,24,39,0.35)", "rgba(17,24,39,0.06)", null, 2.5);

  // Walls
  ctx.save();
  ctx.lineWidth = 1.3;
  for (let i = 0; i < footprint.length; i++) {
    const a = footprint[i];
    const b = footprint[(i + 1) % footprint.length];

    const a0 = project(a, 0, s, origin);
    const b0 = project(b, 0, s, origin);
    const a1 = project(a, H, s, origin);
    const b1 = project(b, H, s, origin);

    ctx.fillStyle = "rgba(17,24,39,0.08)";
    ctx.beginPath();
    ctx.moveTo(a0.x, a0.y);
    ctx.lineTo(b0.x, b0.y);
    ctx.lineTo(b1.x, b1.y);
    ctx.lineTo(a1.x, a1.y);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "rgba(17,24,39,0.35)";
    ctx.stroke();
  }
  ctx.restore();

  // Roof
  drawPolygon(footprint, H, s, origin, "#111827", "rgba(17,24,39,0.10)", null, 3);

  // HUD + scale
  drawSizeHUD(footprint, H);
  drawScaleBar(s);
}

export async function init3D(container) {
  containerEl = container;
  ensureCanvas();
  resize();
}

export function update3DBuilding({ footprint, heightTotal, lot, lotLabels }) {
  lastModel = { footprint, heightTotal, lot, lotLabels };
  ensureCanvas();
  resize();
  draw(lastModel);
}

export function set3DVisible(is3D) {
  const el = document.getElementById("threeContainer");
  if (!el) return;
  el.style.display = is3D ? "block" : "none";
  if (is3D) {
    ensureCanvas();
    resize();
    if (lastModel) draw(lastModel);
  }
}

export function force3DResize() {
  resize();
}

window.addEventListener("resize", () => resize());

function drawLotLabel(points, z, scale, origin, label, color) {
  if (!points || points.length < 3) return;
  const centroid = points.reduce(
    (acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }),
    { x: 0, y: 0 }
  );
  centroid.x /= points.length;
  centroid.y /= points.length;
  const c = project(centroid, z, scale, origin);
  ctx.save();
  ctx.fillStyle = color || "#f97316";
  ctx.font = "bold 12px Arial";
  ctx.fillText(label, c.x + 8, c.y - 8);
  ctx.restore();
}
