"""Builds docs/USER_GUIDE.md and docs/HomeLedger_Guide.pdf from homeledger/static/guide/guide.json and its screenshots.
Run:  python tools/make_guide.py        (the PDF needs Playwright + Chromium; skipped if not installed)"""
import html, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G = ROOT / "homeledger" / "static" / "guide"
data = json.loads((G / "guide.json").read_text(encoding="utf-8"))

md = [f"# {data['title']}", "", data["intro"], "", "## Contents", ""]
for s in data["sections"]:
    if s["title"][0].isdigit():
        md.append(f"- [{s['title']}](#{s['id']})")
md += ["- [Shortcut map](#shortcut-map)", "- [Questions and answers](#questions-and-answers)", ""]
for s in data["sections"]:
    md += [f'<a id="{s["id"]}"></a>', "", ("## " if s["title"][0].isdigit() else "### ") + s["title"], ""]
    for t in s["text"]:
        md += [t, ""]
    if s.get("tips"):
        md += ["> **Good to know:** " + " ".join(s["tips"]), ""]
    if s.get("image"):
        md += [f"![{s['title']}](../homeledger/static/guide/{s['image']}.png)", ""]
md += ["## Shortcut map", "", "Keys with a plus sign are pressed together: Ctrl+A means hold Ctrl and press A.", ""]
for grp in data["shortcuts"]:
    md += [f"### {grp['group']}", "", "| Key | What it does |", "|---|---|"] + [f"| `{k}` | {d} |" for k, d in grp["rows"]] + [""]
md += ["## Questions and answers", ""]
for q, a in data["faq"]:
    md += [f"**{q}**  ", a, ""]
md += ["---", "", "GST, TDS and payroll figures are a starting point. Please have an accountant check them before filing anything."]
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "USER_GUIDE.md").write_text("\n".join(md), encoding="utf-8")
print("wrote docs/USER_GUIDE.md")

# ---- printable PDF (images embedded) ----
e = html.escape
parts = [f"<h1>{e(data['title'])}</h1><p>{e(data['intro'])}</p>"]
for s in data["sections"]:
    parts.append(f"<section><h2>{e(s['title'])}</h2>" + "".join(f"<p>{e(t)}</p>" for t in s["text"]))
    if s.get("tips"):
        parts.append(f"<div class=tip><b>Good to know:</b> {e(' '.join(s['tips']))}</div>")
    if s.get("image"):
        parts.append(f"<img src='{(G / (s['image'] + '.png')).as_uri()}'>")
    parts.append("</section>")
parts.append("<section class=pb><h2>Shortcut map</h2>")
for grp in data["shortcuts"]:
    parts.append(f"<h3>{e(grp['group'])}</h3><table>" + "".join(f"<tr><td><kbd>{e(k)}</kbd></td><td>{e(d)}</td></tr>" for k, d in grp["rows"]) + "</table>")
parts.append("</section><section><h2>Questions and answers</h2>" + "".join(f"<p><b>{e(q)}</b><br>{e(a)}</p>" for q, a in data["faq"]) + "</section>")
page = ("<!doctype html><meta charset=utf-8><style>@page{size:A4;margin:14mm}body{font:12.5px/1.5 Arial,sans-serif;color:#111}h1{color:#0b4f94}h2{color:#0b4f94;margin:0 0 6px}"
        "section{margin:0 0 14px;break-inside:avoid-page}img{width:100%;border:1px solid #ccc;border-radius:6px;margin-top:6px}.tip{background:#eef4fb;padding:6px 10px;border-radius:6px}"
        "table{border-collapse:collapse;width:100%}td{border:1px solid #ccc;padding:3px 8px}kbd{font-weight:700}.pb{break-before:page}</style>" + "".join(parts))
try:
    from playwright.sync_api import sync_playwright
    tmp = ROOT / "docs" / "_guide.html"
    tmp.write_text(page, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(tmp.as_uri()); pg.wait_for_timeout(500)
        pg.pdf(path=str(ROOT / "docs" / "HomeLedger_Guide.pdf"), format="A4", print_background=True); b.close()
    tmp.unlink()
    print("wrote docs/HomeLedger_Guide.pdf")
except Exception as ex:
    print("PDF skipped:", ex)
