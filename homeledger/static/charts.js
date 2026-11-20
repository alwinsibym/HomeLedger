/* Small dependency-free SVG charts (work fully offline). Marks are thin, gridlines faint, hover shows the exact figure. */
"use strict";
const NS = "http://www.w3.org/2000/svg";
function sv(tag, attrs, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs || {}) { if (attrs[k] != null) e.setAttribute(k, attrs[k]); }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
function niceScale(min, max, n = 4) {
  if (max <= min) max = min + 100 * 100;
  const span = max - min, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(x => x * mag).find(s => s >= raw);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(v);
  return { lo, hi, ticks };
}
const CVAR = i => `var(--s${i})`;

/** wraps a chart with title, legend, and a "table" toggle */
function chartCard({ title, sub, legend, draw, table, cls }) {
  const card = h("div", { class: "card " + (cls || "") });
  const tb = h("button", { class: "tbtn noprint", type: "button", "aria-pressed": "false" }, "Show as table");
  const body = h("div", { class: "chart" });
  let asTable = false;
  const paint = () => { body.replaceChildren(asTable && table ? table() : draw()); tb.textContent = asTable ? "Show as chart" : "Show as table"; tb.setAttribute("aria-pressed", asTable); };
  tb.onclick = () => { asTable = !asTable; paint(); };
  card.append(table ? tb : "", h("h3", {}, title), sub ? h("p", { class: "cs" }, sub) : "");
  if (legend && legend.length > 1) card.append(h("div", { class: "legend" }, legend.map(l => h("span", {}, h("span", { class: "sw", style: "background:" + l.color }), l.name))));
  card.append(body); paint();
  return card;
}

/** grouped (side-by-side) or stacked vertical bars. data: [{label, vals:[...], tip?: [..]}], series: [{name,color}] */
function barChart({ data, series, stacked, height = 230, onbar, width = 640 }) {
  const W = width, H = height, L = 46, R = 8, T = 10, B = 26, iw = W - L - R, ih = H - T - B;
  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Bar chart" });
  const tot = d => stacked ? d.vals.reduce((a, b) => a + Math.max(b, 0), 0) : Math.max(0, ...d.vals);
  const mx = Math.max(0, ...data.map(tot)), mn = stacked ? 0 : Math.min(0, ...data.flatMap(d => d.vals));
  const sc = niceScale(mn, mx || 10000, 4), y = v => T + ih - (v - sc.lo) / (sc.hi - sc.lo) * ih;
  const ax = sv("g", { class: "ax" });
  sc.ticks.forEach(t => { ax.append(sv("line", { class: "gl", x1: L, x2: W - R, y1: y(t), y2: y(t) }), sv("text", { x: L - 6, y: y(t) + 4, "text-anchor": "end" }, short(t))); });
  svg.append(ax);
  const gw = iw / data.length, ns = stacked ? 1 : series.length;
  const bw = Math.min(stacked ? 26 : 16, (gw * 0.78) / ns);
  data.forEach((d, i) => {
    const cx = L + gw * i + gw / 2;
    ax.append(sv("text", { x: cx, y: H - 8, "text-anchor": "middle" }, d.label));
    let acc = 0;
    d.vals.forEach((v, j) => {
      if (!v) return;
      const x = stacked ? cx - bw / 2 : cx - (bw * ns) / 2 + bw * j;
      let y0 = y(Math.max(v, 0)), y1 = y(Math.min(v, 0));
      if (stacked) { y0 = y(acc + v); y1 = y(acc); acc += v; }
      const hh = Math.max(1.5, y1 - y0);
      const bar = sv("rect", { class: "mk", x: x + (stacked ? 0 : 1), y: y0, width: bw - (stacked ? 0 : 2), height: hh, rx: 3, fill: CVAR(series[j].c || j + 1), stroke: stacked ? "var(--surface-gap)" : null, "stroke-width": stacked ? 2 : null });
      const tip = `<b>${esc(d.long || d.label)}</b>${esc(series[j].name)}: ${rs(v)}` + (stacked ? `<br>Total: ${rs(tot(d))}` : "");
      bar.addEventListener("mousemove", e => showTip(e, tip)); bar.addEventListener("mouseleave", hideTip);
      if (onbar) { bar.style.cursor = "pointer"; bar.addEventListener("click", () => onbar(d, j)); }
      svg.append(bar);
    });
    // invisible wider hit area so thin bars are easy to hover
    const hit = sv("rect", { x: cx - gw / 2, y: T, width: gw, height: ih, fill: "transparent" });
    hit.addEventListener("mousemove", e => showTip(e, `<b>${esc(d.long || d.label)}</b>` + d.vals.map((v, j) => `${esc(series[j].name)}: ${rs(v)}`).join("<br>")));
    hit.addEventListener("mouseleave", hideTip);
    if (onbar) { hit.style.cursor = "pointer"; hit.addEventListener("click", () => onbar(d)); }
    svg.insertBefore(hit, svg.children[1]);
  });
  return svg;
}

/** line chart. points: [{label, vals:[...]}] */
function lineChart({ data, series, height = 220, width = 640 }) {
  const W = width, H = height, L = 46, R = 14, T = 10, B = 26, iw = W - L - R, ih = H - T - B;
  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Line chart" });
  const all = data.flatMap(d => d.vals.filter(v => v != null));
  const lo0 = Math.min(...all), hi0 = Math.max(...all), span0 = hi0 - lo0;
  // lines may zoom in (the exact figure is in the tooltip); a flat line from zero hides what is happening
  const base = lo0 >= 0 ? Math.max(0, lo0 - Math.max(span0, hi0 * 0.05) * 0.6) : lo0;
  const sc = niceScale(Math.min(base, 0 > lo0 ? lo0 : base), Math.max(hi0, 0 < hi0 ? hi0 : 0), 4), y = v => T + ih - (v - sc.lo) / (sc.hi - sc.lo) * ih;
  const x = i => L + (data.length === 1 ? iw / 2 : iw * i / (data.length - 1));
  const ax = sv("g", { class: "ax" });
  sc.ticks.forEach(t => ax.append(sv("line", { class: "gl", x1: L, x2: W - R, y1: y(t), y2: y(t) }), sv("text", { x: L - 6, y: y(t) + 4, "text-anchor": "end" }, short(t))));
  const every = Math.ceil(data.length / 12);
  data.forEach((d, i) => { if (i % every === 0 || i === data.length - 1) ax.append(sv("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, d.label)); });
  svg.append(ax);
  series.forEach((s, j) => {
    const pts = data.map((d, i) => d.vals[j] == null ? null : [x(i), y(d.vals[j])]).filter(Boolean);
    svg.append(sv("polyline", { fill: "none", stroke: CVAR(s.c || j + 1), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round", points: pts.map(p => p.join(",")).join(" ") }));
    if (data.length <= 24) pts.forEach(p => svg.append(sv("circle", { cx: p[0], cy: p[1], r: 3.5, fill: CVAR(s.c || j + 1), stroke: "var(--surface-gap)", "stroke-width": 2 })));
  });
  const cross = sv("line", { y1: T, y2: T + ih, stroke: "var(--ink-3)", "stroke-width": 1, "stroke-dasharray": "3 3", style: "display:none" });
  svg.append(cross);
  const hit = sv("rect", { x: L, y: T, width: iw, height: ih, fill: "transparent" });
  hit.addEventListener("mousemove", e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(data.length - 1, Math.round((px - L) / (iw / Math.max(1, data.length - 1)))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
    showTip(e, `<b>${esc(data[i].long || data[i].label)}</b>` + series.map((s, j) => data[i].vals[j] == null ? "" : `${esc(s.name)}: ${rs(data[i].vals[j])}`).join("<br>"));
  });
  hit.addEventListener("mouseleave", () => { cross.style.display = "none"; hideTip(); });
  svg.append(hit);
  return svg;
}

/** horizontal bars as HTML rows. items: [{label, value, color?, onclick?, sub?}] */
function hbars(items, { color = 1, max } = {}) {
  const wrap = h("div", {});
  if (!items.length) return h("div", { class: "empty" }, "Nothing to show for this period.");
  const mx = max || Math.max(...items.map(i => i.value), 1);
  for (const it of items) {
    const row = h("div", { class: "hbar", title: it.label + ": " + rs(it.value), onclick: it.onclick },
      h("div", { class: "nm" }, it.label),
      h("div", { class: "tr" }, h("div", { class: "fl", style: `width:${Math.max(0.5, it.value / mx * 100)}%;background:${it.color || CVAR(color)}` })),
      h("div", { class: "v" }, rs(it.value, 0)));
    row.addEventListener("mousemove", e => showTip(e, `<b>${esc(it.label)}</b>${rs(it.value)}${it.sub ? "<br>" + esc(it.sub) : ""}`));
    row.addEventListener("mouseleave", hideTip);
    wrap.append(row);
  }
  return wrap;
}

function simpleTable(head, rows) {
  const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, head.map((x, i) => h("th", { class: i ? "r" : "" }, x)))));
  const tb = h("tbody", {});
  rows.forEach(r => tb.append(h("tr", {}, r.map((c, i) => h("td", { class: i ? "r" : "" }, c)))));
  t.append(tb);
  return h("div", { class: "scroll" }, t);
}
