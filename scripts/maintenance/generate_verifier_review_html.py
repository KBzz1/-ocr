#!/usr/bin/env python
"""生成复核器人工评价 HTML（离线自包含，数据内嵌，不进 git）。

背景：校准裁定之前由 Claude 子 agent 模拟人工（LLM judge）。本工具把 judge
换成真人：医生逐条阅读字段声称值 + 证据 + 复核器意见，人工裁定 should_flag，
HTML 内实时统计 Cohen's kappa 并可导出裁定 JSON（格式与 calibrate.load_adjudications
兼容），最终用 calibrate kappa 命令做官方统计。

展示层净化（不动 verdict 统计口径，n 仍为全部条目）：
- 同键同疑点去重：复核 LLM 偶发对同一处错读重复输出意见（如 pe_skin 一处错读
  两条、逐字相同的两条），按 原文'…' 定位键判重，保留信息最全（非截断/更长）一条。
- 截断残句标记：comment 由 verifier 以 [:40] 硬截断，截断点常落在半句
  （"应为'…'或"），检测残句结尾并加"（原文截断）"提示。

用法（worktree/仓库根）:
    conda run -n manzufei_ocr python scripts/maintenance/generate_verifier_review_html.py \
      --verdicts data/evaluation/calibration/20260801_1330_verdicts.json \
      --golden-dir data/evaluation/golden \
      --llm-adjudications data/evaluation/calibration/20260801_1330_adjudications.json \
      --out data/evaluation/calibration/20260802_verifier_manual_review.html

输出含病历 OCR 原文（患者信息），必须留在 data/，不得提交。
"""
import argparse
import json
import re
from pathlib import Path

_TRUNC_TAIL = re.compile(r"('[^']*'?)?[或、，；;]$")


def _looks_truncated(comment: str) -> bool:
    """截断判定：引号不成对（应为'…'缺闭合引号）或以'或'等残句结尾。"""
    return comment.count("'") % 2 == 1 or bool(_TRUNC_TAIL.search(comment))


def _dedup_opinions(ops: list[dict]) -> list[dict]:
    """同键内按疑点去重：优先按 comment 中的 原文'X' 定位键，退化为同 comment 判重。

    保留信息最全的一条（非截断优先，同截断状态取更长）；其余字段原样保留。
    """
    seen: dict[str, dict] = {}
    for op in ops:
        comment = op.get("comment", "")
        m = re.search(r"原文'([^']*)'", comment)
        key = m.group(1) if m else comment
        truncated = _looks_truncated(comment)
        item = {**op, "truncated": truncated}
        prev = seen.get(key)
        if prev is None:
            seen[key] = item
            continue
        prev_trunc = prev.get("truncated", False)
        if (prev_trunc and not truncated) or (
            prev_trunc == truncated and len(prev.get("comment", "")) < len(comment)
        ):
            seen[key] = item
    return list(seen.values())


def _load_verdicts(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("items") or []
    if not items:
        raise SystemExit(f"verdicts 文件无 items: {path}")
    return items


def _load_ocr_texts(golden_dir: Path) -> dict[str, str]:
    texts = {}
    for p in sorted(golden_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        case_id = data.get("case_id") or p.stem
        if data.get("ocr_text"):
            texts[case_id] = data["ocr_text"]
    return texts


def _load_llm_adjudications(path: Path | None) -> dict[tuple[str, str], bool]:
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(i["case_id"], i["field_key"]): bool(i["should_flag"])
            for i in data.get("adjudications", [])}


def _build_data(items: list[dict], ocr_texts: dict[str, str],
                llm_adj: dict[tuple[str, str], bool]) -> dict:
    """按 (case_id, field_key) 去重分组，合并同键复核器意见。"""
    ordered_keys: list[tuple[str, str]] = []
    opinions: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        key = (item.get("case_id", ""), item.get("field_key", ""))
        if key not in opinions:
            opinions[key] = []
            ordered_keys.append(key)
        opinions[key].append({
            "verdict": item.get("verdict", ""),
            "reason_code": item.get("reason_code", ""),
            "comment": item.get("comment", ""),
            "value": item.get("value", ""),
            "evidence_text": item.get("evidence_text", ""),
        })
    for key in opinions:
        opinions[key] = _dedup_opinions(opinions[key])
    cards = []
    for case_id, field_key in ordered_keys:
        ops = opinions[(case_id, field_key)]
        card = {
            "case_id": case_id,
            "field_key": field_key,
            "opinions": ops,
            "value": ops[0].get("value", ""),
            "evidence_text": ops[0].get("evidence_text", ""),
            "verdict": ops[0].get("verdict", ""),
            "reason_code": ops[0].get("reason_code", ""),
            "comments": [o.get("comment", "") for o in ops],
            "ocr_text": ocr_texts.get(case_id, ""),
            "llm_should_flag": llm_adj.get((case_id, field_key)),
        }
        cards.append(card)
    return {
        "cards": cards,
        # 原始 verdicts 全部条目（统计口径与 calibrate.compute_kappa 一致：n=全部条目）
        "verdict_items": [
            {"case_id": i.get("case_id", ""), "field_key": i.get("field_key", ""),
             "verdict": i.get("verdict", "")}
            for i in items
        ],
        "llm_should_flag_entries": [
            {"case_id": c, "field_key": f, "should_flag": b}
            for (c, f), b in sorted(llm_adj.items())
        ],
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>复核器人工评价 — {stamp}</title>
<style>
  :root {{
    --navy: #1e3a6b; --accentbg: #eef1f7; --ink: #1a1a1a; --muted: #6b6b6b;
    --pass: #1a7f37; --passbg: #e6f4ea; --sus: #b45309; --susbg: #fef3c7;
    --fail: #b3261e; --failbg: #fdecea; --border: #d9dee8;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #f5f6f8; color: var(--ink);
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 15px; line-height: 1.7; }}
  .topbar {{ position: sticky; top: 0; z-index: 10; background: var(--navy); color: #fff;
    padding: 14px 28px; display: flex; align-items: center; gap: 20px; }}
  .topbar h1 {{ font-size: 17px; margin: 0; font-weight: 600; }}
  .topbar .progress {{ flex: 1; }}
  .topbar .bar {{ height: 8px; background: rgba(255,255,255,.25); border-radius: 4px; overflow: hidden; }}
  .topbar .bar > div {{ height: 100%; background: #4ade80; width: 0; transition: width .2s; }}
  .topbar .count {{ font-size: 13px; opacity: .9; white-space: nowrap; }}
  .topbar .actions {{ display: flex; gap: 8px; }}
  .topbar button {{ background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.4);
    color: #fff; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
  .topbar button:hover {{ background: rgba(255,255,255,.28); }}
  .wrap {{ max-width: 860px; margin: 24px auto 80px; padding: 0 20px; }}
  .guide {{ background: var(--accentbg); border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 16px; font-size: 13px; color: var(--muted); margin-bottom: 16px; }}
  .card {{ background: #fff; border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 24px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }}
  .card.done {{ border-left: 5px solid #4ade80; }}
  .card.undone {{ border-left: 5px solid var(--border); }}
  .card .head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
  .card .head .case {{ font-size: 13px; color: var(--muted); }}
  .card .head .fk {{ font-weight: 700; font-size: 16px; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .badge.pass {{ background: var(--passbg); color: var(--pass); }}
  .badge.suspicious {{ background: var(--susbg); color: var(--sus); }}
  .badge.fail {{ background: var(--failbg); color: var(--fail); }}
  .badge.unrated {{ background: #eee; color: var(--muted); }}
  .sec {{ margin: 10px 0; }}
  .sec .lbl {{ font-size: 12px; color: var(--muted); margin-bottom: 2px; }}
  .value {{ background: #fafafa; border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 12px; font-family: Menlo, Consolas, monospace; font-size: 13px; word-break: break-all; }}
  .evidence {{ background: var(--accentbg); border-radius: 6px; padding: 8px 12px;
    font-size: 13px; word-break: break-all; }}
  .comment {{ font-size: 13px; color: var(--sus); }}
  details.ocr {{ margin-top: 6px; }}
  details.ocr summary {{ font-size: 12px; color: var(--muted); cursor: pointer; }}
  details.ocr pre {{ background: #fafafa; border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; font-size: 12px; white-space: pre-wrap; word-break: break-all;
    max-height: 260px; overflow-y: auto; }}
  .opts {{ display: flex; gap: 12px; margin-top: 14px; }}
  .opts button {{ flex: 1; padding: 12px 0; border-radius: 8px; font-size: 15px; font-weight: 600;
    cursor: pointer; border: 2px solid var(--border); background: #fff; }}
  .opts .flag {{ color: var(--fail); }}
  .opts .flag.sel {{ background: var(--failbg); border-color: var(--fail); }}
  .opts .clear {{ color: var(--muted); }}
  .opts .clear.sel {{ background: var(--passbg); border-color: var(--pass); }}
  .opts button:hover {{ border-color: var(--navy); }}
  .stats {{ background: #fff; border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 24px; margin-top: 20px; }}
  .stats h2 {{ font-size: 15px; margin: 0 0 10px; }}
  .stats .kbig {{ font-size: 28px; font-weight: 700; color: var(--navy); }}
  .stats .kmeta {{ font-size: 13px; color: var(--muted); }}
  .stats table {{ border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
  .stats td, .stats th {{ border: 1px solid var(--border); padding: 5px 12px; text-align: center; }}
  .stats .warn {{ color: var(--sus); font-size: 13px; }}
  .nav {{ position: fixed; bottom: 20px; right: 24px; display: flex; gap: 8px; }}
  .nav button {{ padding: 10px 16px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--navy); color: #fff; cursor: pointer; font-size: 14px; }}
  .nav button:disabled {{ opacity: .4; cursor: default; }}
  .nav .jump {{ display: flex; gap: 4px; align-items: center; }}
  .nav input {{ width: 56px; padding: 6px; border-radius: 6px; border: 1px solid var(--border); }}
  .llm-note {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .trunc {{ font-size: 11px; color: var(--sus); font-style: italic; }}
</style>
</head>
<body>
<div class="topbar">
  <h1>复核器人工评价</h1>
  <div class="progress"><div class="bar"><div id="barFill"></div></div></div>
  <div class="count"><span id="doneCount">0</span>/<span id="totalCount">0</span> 已评</div>
  <div class="actions">
    <button onclick="exportAdj()">导出裁定 JSON</button>
    <button onclick="importAdj()">导入裁定</button>
    <button onclick="resetAll()">重置</button>
  </div>
</div>
<div class="wrap">
  <div class="guide">
    判定标准：根据「字段声称值」与「证据/原文」，判断该字段<b>是否应被标记可疑、需要医生复核</b>。
    对复核器标记 suspicious/fail 的字段：值真有需要复核的问题 → 选「应标可疑」；是误报 → 选「无需复核」。
    对标记 pass 的字段：值确实没问题 → 「无需复核」；若发现漏报 → 「应标可疑」。快捷键 1=应标，2=无需，←/→ 翻页。
  </div>
  <div id="cards"></div>
  <div class="stats" id="stats"></div>
</div>
<div class="nav">
  <button onclick="go(-1)" id="prevBtn">← 上一题</button>
  <div class="jump"><input id="jumpInput" type="number" min="1" onkeydown="if(event.key==='Enter')jumpTo()"><span>/<span id="totalNav"></span></span></div>
  <button onclick="go(1)" id="nextBtn">下一题 →</button>
</div>
<input type="file" id="adjFile" accept=".json" style="display:none" onchange="onImportFile(event)">
<script>
const DATA = {data_json};
const STORE_KEY = "{store_key}";
const LEGACY_KEY = "{store_key}-" + "{stamp}";
let idx = 0;

// ---- 状态 ----
function loadState() {{
  // 新固定 key 为空时，从旧时间戳 key 迁移已评进度（覆盖重生成时进度不丢）
  try {{
    const cur = JSON.parse(localStorage.getItem(STORE_KEY) || "{{}}");
    if (Object.keys(cur).length) return cur;
    const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || "{{}}");
    if (Object.keys(legacy).length) {{
      localStorage.setItem(STORE_KEY, JSON.stringify(legacy));
      return legacy;
    }}
    return {{}};
  }}
  catch (e) {{ return {{}}; }}
}}
let state = loadState();
function saveState() {{
  localStorage.setItem(STORE_KEY, JSON.stringify(state));
  renderAll();
}}

// ---- 渲染 ----
function cardKey(c) {{ return c.case_id + "::" + c.field_key; }}
function verdictBadge(verdict) {{
  if (verdict === "pass") return '<span class="badge pass">pass 通过</span>';
  if (verdict === "suspicious") return '<span class="badge suspicious">suspicious 可疑</span>';
  if (verdict === "fail") return '<span class="badge fail">fail 失败</span>';
  return '<span class="badge unrated">?</span>';
}}
function renderCard(c, i) {{
  const k = cardKey(c);
  const rated = (k in state);
  const sel = state[k];
  const llm = (c.llm_should_flag === undefined) ? "" :
    '<div class="llm-note">LLM 裁定：' + (c.llm_should_flag ? "应标可疑" : "无需复核") + '</div>';
  const comments = (c.opinions || []).filter(o => o && o.comment).map(o =>
    '<div class="comment">复核器意见：' + escapeHtml(o.comment) +
    (o.truncated ? ' <span class="trunc">（原文截断）</span>' : '') + '</div>').join("");
  return '<div class="card ' + (rated ? "done" : "undone") + '" id="card-' + i + '">' +
    '<div class="head"><span class="fk">' + escapeHtml(c.field_key) + '</span>' +
    '<span class="case">' + escapeHtml(c.case_id) + '（第 ' + (i + 1) + ' / ' + DATA.cards.length + ' 题）</span></div>' +
    verdictBadge(c.verdict) + (c.reason_code ? ' <span class="llm-note">' + escapeHtml(c.reason_code) + '</span>' : '') + llm +
    '<div class="sec"><div class="lbl">字段声称值</div><div class="value">' + escapeHtml(c.value || "（空）") + '</div></div>' +
    '<div class="sec"><div class="lbl">证据（eXXX 编号引用）</div><div class="evidence">' + escapeHtml(c.evidence_text || "（无证据）") + '</div></div>' +
    comments +
    (c.ocr_text ? '<details class="ocr"><summary>查看完整 OCR 原文（' + escapeHtml(c.case_id) + '）</summary><pre>' +
      escapeHtml(c.ocr_text) + '</pre></details>' : '') +
    '<div class="opts">' +
      '<button class="flag' + (rated && sel ? " sel" : "") + '" onclick="rate(' + i + ', true)">1 · 应标可疑（需要复核）</button>' +
      '<button class="clear' + (rated && !sel ? " sel" : "") + '" onclick="rate(' + i + ', false)">2 · 无需复核</button>' +
    '</div></div>';
}}
function escapeHtml(s) {{
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}}
function renderAll() {{
  const cardsEl = document.getElementById("cards");
  cardsEl.innerHTML = DATA.cards.map(renderCard).join("");
  const done = DATA.cards.filter(c => cardKey(c) in state).length;
  document.getElementById("doneCount").textContent = done;
  document.getElementById("totalCount").textContent = DATA.cards.length;
  document.getElementById("barFill").style.width = (done / DATA.cards.length * 100) + "%";
  document.getElementById("totalNav").textContent = DATA.cards.length;
  document.getElementById("prevBtn").disabled = (idx <= 0);
  document.getElementById("nextBtn").disabled = (idx >= DATA.cards.length - 1);
  document.getElementById("jumpInput").value = idx + 1;
  renderStats();
  const active = document.getElementById("card-" + idx);
  if (active) active.scrollIntoView({{ behavior: "smooth", block: "start" }});
}}
function rate(i, flag) {{
  state[cardKey(DATA.cards[i])] = flag;
  saveState();
}}
function go(delta) {{
  idx = Math.max(0, Math.min(DATA.cards.length - 1, idx + delta));
  renderAll();
}}
function jumpTo() {{
  const v = parseInt(document.getElementById("jumpInput").value, 10);
  if (v >= 1 && v <= DATA.cards.length) {{ idx = v - 1; renderAll(); }}
}}

// ---- 统计（口径与 calibrate.compute_kappa 一致：suspicious/fail=应标侧，n=全部 verdict 条目）----
function cohenKappa(table) {{
  const n = table[0][0] + table[0][1] + table[1][0] + table[1][1];
  if (n === 0) return 0;
  const p0 = (table[0][0] + table[1][1]) / n;
  const r0 = table[0][0] + table[0][1], r1 = table[1][0] + table[1][1];
  const c0 = table[0][0] + table[1][0], c1 = table[0][1] + table[1][1];
  const pe = (r0 * c0 + r1 * c1) / (n * n);
  if (pe >= 1) return 0;
  return (p0 - pe) / (1 - pe);
}}
function renderStats() {{
  const table = [[0, 0], [0, 0]];  // 行=复核器 pass/susp|fail，列=人工 不应标/应标
  let n = 0, llmAgree = 0, llmDisagree = 0;
  const diff = [];
  for (const it of DATA.verdict_items) {{
    const k = it.case_id + "::" + it.field_key;
    if (!(k in state)) continue;
    n++;
    const verifierFlagged = (it.verdict === "suspicious" || it.verdict === "fail");
    const shouldFlag = state[k];
    table[verifierFlagged ? 1 : 0][shouldFlag ? 1 : 0]++;
    const card = DATA.cards.find(c => cardKey(c) === k);
    if (card && card.llm_should_flag !== undefined) {{
      if (card.llm_should_flag === shouldFlag) llmAgree++;
      else {{ llmDisagree++; diff.push(card.case_id + " / " + card.field_key +
        "：LLM=" + (card.llm_should_flag ? "应标" : "不标") + "，人工=" + (shouldFlag ? "应标" : "不标")); }}
    }}
  }}
  const kappa = cohenKappa(table);
  const done = DATA.cards.filter(c => cardKey(c) in state).length;
  const allDone = (done === DATA.cards.length);
  let html = "<h2>统计（已评 " + done + "/" + DATA.cards.length + "）</h2>";
  html += '<div class="kbig">kappa = ' + kappa.toFixed(4) + '</div>';
  html += '<div class="kmeta">n = ' + n + ' 条 verdict 条目（含重复键，与 calibrate CLI 口径一致）　' +
    '一致性表：复核器(pass / suspicious|fail) × 人工(不应标 / 应标)</div>';
  html += "<table><tr><th>复核器\\人工</th><th>不应标</th><th>应标</th></tr>" +
    "<tr><td>pass</td><td>" + table[0][0] + "</td><td>" + table[0][1] + "</td></tr>" +
    "<tr><td>suspicious/fail</td><td>" + table[1][0] + "</td><td>" + table[1][1] + "</td></tr></table>";
  if (allDone) {{
    html += (kappa >= 0.7)
      ? '<div class="kbig" style="color:#1a7f37">✓ kappa ≥ 0.7，复核器可上岗</div>'
      : '<div class="warn">kappa &lt; 0.7，复核器未达上岗线（spec 5.2）</div>';
  }} else {{
    html += '<div class="kmeta">尚未评完：当前 kappa 为已评部分的中间值</div>';
  }}
  if (DATA.llm_should_flag_entries.length > 0) {{
    html += '<div class="kmeta">与 LLM 裁定对比：一致 ' + llmAgree + '，分歧 ' + llmDisagree + '</div>';
    if (diff.length) html += '<ul style="font-size:13px;color:var(--muted)">' +
      diff.slice(0, 20).map(d => "<li>" + escapeHtml(d) + "</li>").join("") + "</ul>";
  }}
  document.getElementById("stats").innerHTML = html;
}}

// ---- 导入 / 导出 ----
function exportAdj() {{
  const items = DATA.cards.filter(c => cardKey(c) in state).map(c => ({{
    case_id: c.case_id, field_key: c.field_key, should_flag: state[cardKey(c)],
  }}));
  const blob = new Blob([JSON.stringify({{ adjudications: items }}, null, 2)], {{ type: "application/json" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "{stamp}_human_adjudications.json";
  a.click();
  URL.revokeObjectURL(a.href);
}}
function importAdj() {{ document.getElementById("adjFile").click(); }}
function onImportFile(ev) {{
  const f = ev.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = function () {{
    try {{
      const data = JSON.parse(reader.result);
      const items = data.adjudications || [];
      for (const it of items) state[it.case_id + "::" + it.field_key] = !!it.should_flag;
      saveState();
      alert("已导入 " + items.length + " 条裁定");
    }} catch (e) {{ alert("导入失败：" + e.message); }}
  }};
  reader.readAsText(f);
  ev.target.value = "";
}}
function resetAll() {{
  if (!confirm("确认清空全部人工裁定？此操作不可撤销。")) return;
  state = {{}};
  saveState();
}}

// ---- 键盘 ----
document.addEventListener("keydown", function (e) {{
  if (e.target.tagName === "INPUT") return;
  if (e.key === "1") rate(idx, true);
  else if (e.key === "2") rate(idx, false);
  else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === "ArrowRight") go(1);
}});

renderAll();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="生成复核器人工评价 HTML（离线自包含，含病历原文，输出不进 git）")
    parser.add_argument("--verdicts", required=True, help="calibrate export 输出的 verdicts JSON")
    parser.add_argument("--golden-dir", default="data/evaluation/golden")
    parser.add_argument("--llm-adjudications", default=None, help="可选：LLM 裁定 JSON，用于人工 vs LLM 对比")
    parser.add_argument("--out", required=True, help="输出 HTML 路径（建议 data/evaluation/calibration/）")
    parser.add_argument("--store-key", default="verifier-manual-review",
                        help="浏览器进度存储键；不同评测集用不同 key 避免进度互相覆盖")
    args = parser.parse_args()

    items = _load_verdicts(Path(args.verdicts))
    ocr_texts = _load_ocr_texts(Path(args.golden_dir))
    llm_adj = _load_llm_adjudications(Path(args.llm_adjudications) if args.llm_adjudications else None)
    data = _build_data(items, ocr_texts, llm_adj)
    stamp = Path(args.out).stem
    html = HTML_TEMPLATE.format(
        data_json=json.dumps(data, ensure_ascii=False),
        stamp=stamp,
        store_key=args.store_key,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"已生成人工评价页: {out}")
    print(f"  字段数（去重）: {len(data['cards'])}　verdict 条目: {len(data['verdict_items'])}　含 OCR 原文: {len(ocr_texts)} 例")


if __name__ == "__main__":
    main()
