export function polygonAreaAbs(poly){
  let a=0;
  for(let i=0;i<poly.length;i++){
    const p=poly[i], q=poly[(i+1)%poly.length];
    a += p.x*q.y - q.x*p.y;
  }
  return Math.abs(a)/2;
}
function signedArea(poly){
  let a=0;
  for(let i=0;i<poly.length;i++){
    const p=poly[i], q=poly[(i+1)%poly.length];
    a += p.x*q.y - q.x*p.y;
  }
  return a/2;
}
function normalize(v){ const l=Math.hypot(v.x,v.y)||1; return {x:v.x/l,y:v.y/l}; }
function sub(a,b){ return {x:a.x-b.x,y:a.y-b.y}; }
function add(a,b){ return {x:a.x+b.x,y:a.y+b.y}; }
function mul(a,s){ return {x:a.x*s,y:a.y*s}; }
function inwardNormal(d,ccw){ return ccw ? {x:-d.y,y:d.x}:{x:d.y,y:-d.x}; }

export function variableInsetLotPolygon(poly, setbacks){
  const n=poly?.length||0;
  if(n<3) return null;
  const ccw = signedArea(poly) >= 0;

  const dirs=new Array(n);
  const norms=new Array(n);
  for(let i=0;i<n;i++){
    const a=poly[i], b=poly[(i+1)%n];
    const d=normalize(sub(b,a));
    dirs[i]=d;
    norms[i]=normalize(inwardNormal(d,ccw));
  }

  const out=[];
  for(let i=0;i<n;i++){
    const prev=(i-1+n)%n;
    const v=poly[i];
    const n1=norms[prev], n2=norms[i];
    const s1=(setbacks?.[prev] ?? 3);
    const s2=(setbacks?.[i] ?? 3);

    const p1=add(v, mul(n1,s1));
    const d1=dirs[prev];
    const p2=add(v, mul(n2,s2));
    const d2=dirs[i];

    const det = d1.x*d2.y - d1.y*d2.x;
    if(Math.abs(det) < 1e-9){
      // parallel edges -> move along averaged normal
      const avg=normalize(add(mul(n1,s1), mul(n2,s2)));
      out.push(add(v, avg));
      continue;
    }
    const rhs=sub(p2,p1);
    const t=(rhs.x*d2.y - rhs.y*d2.x)/det;
    out.push(add(p1, mul(d1,t)));
  }

  if(polygonAreaAbs(out) < 1e-6) return null;

  // Keep inside: if needed, shrink around centroid until all points inside
  const inside=(pt,pg)=>{
    let c=false;
    for(let i=0,j=pg.length-1;i<pg.length;j=i++){
      const a=pg[i], b=pg[j];
      if(((a.y>pt.y)!=(b.y>pt.y)) && (pt.x < (b.x-a.x)*(pt.y-a.y)/(b.y-a.y+1e-12)+a.x)) c=!c;
    }
    return c;
  };
  const c = out.reduce((acc,p)=>({x:acc.x+p.x,y:acc.y+p.y}),{x:0,y:0});
  c.x/=out.length; c.y/=out.length;

  let k=1.0;
  for(let iter=0; iter<25; iter++){
    let ok=true;
    for(const p of out){ if(!inside(p,poly)){ ok=false; break; } }
    if(ok) break;
    k *= 0.92;
    for(let i=0;i<out.length;i++){
      out[i] = {x: c.x + (out[i].x-c.x)*k, y: c.y + (out[i].y-c.y)*k};
    }
  }
  if(polygonAreaAbs(out) < 1e-6) return null;
  return out;
}
