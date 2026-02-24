export function drawCadMap(ctx, cadMap, worldToCanvas, scale, canvas, scaleMultiplier = 1) {
  if (!cadMap?.layers?.length) return;

  cadMap.layers.forEach(layer => {
    if (!layer.visible) return;
    const opacity = typeof layer.opacity === "number" ? layer.opacity : 0.7;

    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, opacity));

    layer.entities?.forEach(entity => {
      if (
        entity?.bbox &&
        canvas &&
        !isBboxVisible(entity.bbox, worldToCanvas, scale, canvas, scaleMultiplier)
      ) {
        return;
      }
      switch (entity.t) {
        case "line":
        case "polyline":
        case "arc":
          drawPolyline(ctx, entity, worldToCanvas, scale, scaleMultiplier);
          break;
        case "circle":
          drawCircle(ctx, entity, worldToCanvas, scale, scaleMultiplier);
          break;
        case "text":
          drawText(ctx, entity, worldToCanvas, scale, scaleMultiplier);
          break;
        default:
          break;
      }
    });

    ctx.restore();
  });
}

function isBboxVisible(bbox, worldToCanvas, scale, canvas, scaleMultiplier) {
  if (!bbox || !canvas) return true;
  const topLeft = worldToCanvas(bbox.minX * scaleMultiplier, bbox.minY * scaleMultiplier, scale);
  const bottomRight = worldToCanvas(
    bbox.maxX * scaleMultiplier,
    bbox.maxY * scaleMultiplier,
    scale
  );
  const minX = Math.min(topLeft.x, bottomRight.x);
  const maxX = Math.max(topLeft.x, bottomRight.x);
  const minY = Math.min(topLeft.y, bottomRight.y);
  const maxY = Math.max(topLeft.y, bottomRight.y);

  return !(maxX < 0 || maxY < 0 || minX > canvas.width || minY > canvas.height);
}

function applyStrokeStyle(ctx, entity) {
  ctx.lineWidth = Number.isFinite(entity.lw) ? Math.max(1, entity.lw) : 1;
  ctx.strokeStyle = entity.color || "rgba(15,23,42,0.65)";
}

function drawPolyline(ctx, entity, worldToCanvas, scale, scaleMultiplier) {
  const pts = entity.pts || [];
  if (pts.length < 2) return;
  ctx.beginPath();
  pts.forEach((pt, index) => {
    const c = worldToCanvas(pt.x * scaleMultiplier, pt.y * scaleMultiplier, scale);
    if (index === 0) ctx.moveTo(c.x, c.y);
    else ctx.lineTo(c.x, c.y);
  });
  if (entity.closed) ctx.closePath();
  applyStrokeStyle(ctx, entity);
  ctx.stroke();
}

function drawCircle(ctx, entity, worldToCanvas, scale, scaleMultiplier) {
  const c = worldToCanvas(entity.x * scaleMultiplier, entity.y * scaleMultiplier, scale);
  const radius = entity.r * scale * scaleMultiplier;
  ctx.beginPath();
  ctx.arc(c.x, c.y, radius, 0, Math.PI * 2);
  applyStrokeStyle(ctx, entity);
  ctx.stroke();
}

function drawText(ctx, entity, worldToCanvas, scale, scaleMultiplier) {
  const c = worldToCanvas(entity.x * scaleMultiplier, entity.y * scaleMultiplier, scale);
  const fontSize = Math.max(9, (entity.h || 1) * scale * scaleMultiplier);
  ctx.save();
  ctx.translate(c.x, c.y);
  ctx.rotate(((entity.rot || 0) * Math.PI) / 180);
  ctx.fillStyle = entity.color || "rgba(15,23,42,0.8)";
  ctx.font = `${fontSize}px Arial, sans-serif`;
  ctx.fillText(entity.text || "", 0, 0);
  ctx.restore();
}
