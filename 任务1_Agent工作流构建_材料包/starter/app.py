from __future__ import annotations

import json
import io
from pathlib import Path

from flask import Flask, render_template_string, request, send_file, session

from agent_interface import Agent
from model_client import ModelClient


PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_DIR / "data"
TASKS_PATH = DATA_DIR / "tasks.jsonl"

app = Flask(__name__)
app.secret_key = "shopping-agent-local-demo"
agent = Agent(DATA_DIR)
model_client = ModelClient()
products_by_id = {product["product_id"]: product for product in agent.products}
last_batch_results: list[dict] = []
last_batch_evaluation: dict = {}

with TASKS_PATH.open("r", encoding="utf-8") as file:
  tasks = [json.loads(line) for line in file if line.strip()]

EXAMPLES = [
    "Find a shirt about Barn from Konopelski-Inc with price under $17.",
    "Buy an affordable mug related to Person; prefer Rice-Inc if available.",
    "I need a Nature themed mug that costs less than $17.",
]


def run_with_mode(instruction: str, mode: str) -> dict:
    if mode == "rule":
        rule_agent = Agent(DATA_DIR)
        rule_agent.model_client.api_key = None
        return rule_agent.run(instruction)
    if mode == "direct_llm":
        started = __import__("time").perf_counter()
        try:
            product_id = model_client.recommend_product(instruction, agent.products)
            error = None
        except Exception as exc:
            product_id = None
            error = f"LLM direct baseline failed: {type(exc).__name__}"
        return {
            "instruction": instruction,
            "purchased_product_id": product_id,
            "trace": [{"step": "direct_llm", "status": "selected" if product_id else "rejected", "method": "llm"}],
            "summary": error or "Selected directly by the LLM baseline without local constraint verification.",
            "parsed_request": None,
            "candidates": [],
            "verification": {},
            "latency_ms": round((__import__("time").perf_counter() - started) * 1000, 2),
        }
    return agent.run(instruction)

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cartographer | Shopping Agent</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root { --ink:#17212b; --muted:#687681; --line:#d8ded8; --lime:#d8ed65; --coral:#e95f4b; --panel:#fffefa; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); font-family:'Space Grotesk',sans-serif; background:radial-gradient(circle at 90% 0%,#e2edbd 0,transparent 30rem),linear-gradient(135deg,#f4f3ed,#e9eee7); }
    .shell { max-width:1240px; margin:auto; padding:34px 24px 70px; }
    .eyebrow { color:#5d7416; font:500 12px 'DM Mono',monospace; letter-spacing:.12em; text-transform:uppercase; }
    h1 { font-size:clamp(2.5rem,6vw,5rem); line-height:.98; margin:12px 0 18px; letter-spacing:-.04em; }
    h2,h3 { margin-top:0; letter-spacing:0; } h2 { font-size:1.25rem; }
    .lede { max-width:700px; color:var(--muted); font-size:1.06rem; line-height:1.55; }
    .workspace { display:grid; grid-template-columns:minmax(0,1.4fr) minmax(280px,.8fr); gap:20px; align-items:start; margin-top:34px; }
    .panel { background:rgba(255,254,250,.8); border:1px solid var(--line); border-radius:8px; padding:22px; box-shadow:0 16px 40px rgba(23,33,43,.06); }
    label { display:block; color:var(--muted); font-size:.82rem; font-weight:600; margin:0 0 8px; }
    select, textarea { width:100%; border:1px solid #bdc8bd; border-radius:5px; background:#fff; color:var(--ink); font:inherit; padding:12px; }
    textarea { resize:vertical; min-height:110px; line-height:1.45; }
    .field { margin-bottom:16px; }
    button { width:100%; border:0; border-radius:5px; padding:13px 16px; background:var(--ink); color:#fff; font:600 15px 'Space Grotesk',sans-serif; cursor:pointer; }
    button:hover { background:#344552; } .hint { color:var(--muted); font-size:.82rem; line-height:1.4; margin-top:12px; }
    .result { margin-top:20px; } .product-id { color:#5d7416; font:500 12px 'DM Mono',monospace; letter-spacing:.08em; }
    .product-name { font-size:clamp(1.7rem,3vw,2.45rem); font-weight:700; margin:8px 0; } .price { color:var(--coral); font:500 1.5rem 'DM Mono',monospace; }
    .muted { color:var(--muted); } .tags { margin-top:16px; } .tag { display:inline-block; background:#edf2d7; border:1px solid #d7e2a7; border-radius:999px; padding:5px 9px; margin:3px 4px 3px 0; font-size:.78rem; }
    .checks { display:grid; gap:8px; } .check { display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid #e4e8e2; padding:8px 0; font-size:.9rem; } .pass { color:#4f7414; } .fail { color:var(--coral); }
    .metric { background:#f0f3eb; border-radius:5px; padding:12px; margin-top:12px; } .metric strong { display:block; font:500 1.35rem 'DM Mono',monospace; }
    .below { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:20px; } .candidate { padding:9px 0; border-bottom:1px solid #e4e8e2; } .candidate:last-child { border-bottom:0; }
    pre { white-space:pre-wrap; overflow:auto; background:#202b34; color:#edf2d7; border-radius:5px; padding:14px; font:12px/1.5 'DM Mono',monospace; }
    .error { border-left:4px solid var(--coral); } .snapshot { margin-top:28px; } .stats { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; } .stat { border-top:2px solid var(--lime); padding-top:10px; } .stat span { display:block; color:var(--muted); font-size:.78rem; } .stat strong { font:500 1.2rem 'DM Mono',monospace; }
    .batch { margin-top:20px; } .batch-table { width:100%; border-collapse:collapse; font-size:.88rem; } .batch-table th,.batch-table td { text-align:left; border-bottom:1px solid #e1e6df; padding:10px 8px; vertical-align:top; } .batch-table th { color:var(--muted); font-size:.76rem; text-transform:uppercase; } .download { display:inline-block; margin-top:14px; color:#5d7416; font-weight:600; text-decoration:none; }
    @media (max-width:800px) { .workspace,.below { grid-template-columns:1fr; } .stats { grid-template-columns:repeat(2,1fr); } .shell { padding:24px 16px 50px; } }
  </style>
</head>
<body>
<main class="shell">
  <div class="eyebrow">Offline catalogue / live model reasoning</div>
  <h1>Find the right thing.</h1>
  <p class="lede">Describe a shopping need in plain language. The agent uses the model to understand intent, then searches and verifies against the local catalogue.</p>
  <p class="hint">Current model: <strong>{{ active_model }}</strong>{% if not llm_enabled %} · fallback parser active{% endif %}</p>
  <section class="workspace">
    <form class="panel" method="post">
      <h2>Single request</h2>
      <div class="field"><label for="instruction">CUSTOM REQUEST</label><textarea id="instruction" name="instruction" placeholder="Type your own request, e.g. Find a mug about Person under $20...">{{ instruction }}</textarea></div>
    <div class="field"><label for="task">LOAD EXAMPLE TASK (OPTIONAL)</label><select id="task" name="task_id" onchange="document.getElementById('instruction').value=this.options[this.selectedIndex].dataset.instruction || ''"><option value="">Do not load an example</option>{% for task in tasks %}<option value="{{ task.task_id }}" data-instruction="{{ task.instruction }}">{{ task.task_id }} · {{ task.instruction }}</option>{% endfor %}</select></div>
    <div class="field"><label for="mode">DECISION MODE</label><select id="mode" name="mode"><option value="hybrid" {% if mode == 'hybrid' %}selected{% endif %}>Hybrid Agent · LLM parse + local verify</option><option value="rule" {% if mode == 'rule' %}selected{% endif %}>Rule baseline · local only</option><option value="direct_llm" {% if mode == 'direct_llm' %}selected{% endif %}>LLM direct baseline · no local verify</option></select></div>
    <button type="submit">Run single request</button>
      <p class="hint">Type a custom shopping request, or load one bundled task as an example. Incomplete requests can be continued in the next turn.</p>
    </form>
    <form class="panel" method="post" enctype="multipart/form-data" action="/batch">
      <h2>Batch import</h2>
      <p class="muted">Upload a JSONL file with one object per line, containing <code>task_id</code> and <code>instruction</code>.</p>
      <div class="field"><label for="tasks_file">TASK FILE</label><input id="tasks_file" name="tasks_file" type="file" accept=".jsonl,.json" required></div>
    <div class="field"><label for="batch_mode">BATCH DECISION MODE</label><select id="batch_mode" name="batch_mode"><option value="hybrid">Hybrid Agent · LLM parse + local verify</option><option value="rule">Rule baseline · local only</option><option value="direct_llm">LLM direct baseline · no local verify</option></select></div>
    <button type="submit">Run all uploaded tasks</button>
      <p class="hint">Each task may call the configured model API.</p>
    </form>
    {% if clarification %}<div class="panel result"><div class="eyebrow">Clarification needed</div><p>{{ clarification }}</p><p class="muted">Add the missing information in the request box and submit again.</p></div>{% endif %}
    {% if result %}
    <div class="panel result">
      {% if product %}<div class="eyebrow">Recommendation / verified</div><div class="product-id">{{ product.product_id }} · SELECTED PRODUCT</div><div class="product-name">{{ product.name }}</div><div class="price">${{ '%.2f'|format(product.price) }}</div><p class="muted">{{ product.manufacturer }} · {{ product.item_type }}</p><div class="tags">{% for tag in product.tags %}<span class="tag">{{ tag }}</span>{% endfor %}</div><hr><p><strong>Why this product</strong><br>{{ result.summary }}</p>{% else %}<div class="error"><strong>No recommendation</strong><p>{{ result.summary }}</p></div>{% endif %}
      <h3>Decision checks</h3><div class="checks">{% for name, passed in result.verification.items() %}<div class="check"><span>{{ name.replace('_',' ').title() }}</span><strong class="{{ 'pass' if passed else 'fail' }}">{{ 'PASS' if passed else 'WARN' }}</strong></div>{% endfor %}</div><div class="metric"><span class="muted">Decision latency</span><strong>{{ '%.0f'|format(result.latency_ms or 0) }} ms</strong></div>
    </div>
    {% endif %}
  </section>
  {% if result %}<section class="below"><div class="panel"><h2>Parsed request</h2><pre>{{ result.parsed_request|tojson(indent=2) }}</pre></div><div class="panel"><h2>Candidate ranking</h2>{% for candidate_id in result.candidates %}{% set candidate = products[candidate_id] %}<div class="candidate"><strong>{{ '%02d'|format(loop.index) }}</strong> {{ candidate_id }} · {{ candidate.name }} · ${{ '%.2f'|format(candidate.price) }}</div>{% else %}<p class="muted">No candidates survived the hard constraints.</p>{% endfor %}</div></section><section class="panel" style="margin-top:20px"><h2>Agent trace</h2><pre>{{ result.trace|tojson(indent=2) }}</pre></section>{% endif %}
    {% if batch_results %}<section class="panel batch"><h2>Batch results · {{ batch_results|length }} tasks</h2><div class="stats">{% for label, value in batch_evaluation.items() %}<div class="stat"><span>{{ label.replace('_',' ').title() }}</span><strong>{{ value }}</strong></div>{% endfor %}</div><a class="download" href="/batch/download">Download JSONL results</a><table class="batch-table"><thead><tr><th>Task</th><th>Request</th><th>Recommendation</th><th>Latency</th></tr></thead><tbody>{% for row in batch_results %}<tr><td>{{ row.task_id }}</td><td>{{ row.instruction }}</td><td>{% if row.purchased_product_id %}<strong>{{ row.purchased_product_id }}</strong>{% else %}<span class="fail">No result</span>{% endif %}<br><span class="muted">{{ row.summary }}</span></td><td>{{ '%.0f'|format(row.latency_ms or 0) }} ms</td></tr>{% endfor %}</tbody></table></section>{% endif %}
    <section class="snapshot"><div class="eyebrow">Current run metrics</div>{% if batch_results %}<p class="muted">Metrics below are calculated from the task file uploaded in this run.</p>{% elif result %}<div class="stats"><div class="stat"><span>Tasks in current run</span><strong>1</strong></div><div class="stat"><span>Selected</span><strong>{{ 1 if result.purchased_product_id else 0 }}</strong></div><div class="stat"><span>Latency</span><strong>{{ '%.0f'|format(result.latency_ms or 0) }} ms</strong></div></div>{% else %}<p class="muted">Run a single request or upload a JSONL task file to calculate current metrics.</p>{% endif %}</section>
</main>
</body></html>
"""


def summarize_batch(rows: list[dict]) -> dict:
    latencies = [row.get("latency_ms") for row in rows if row.get("latency_ms") is not None]
    selected = [row for row in rows if row.get("purchased_product_id")]
    checks = [row.get("verification", {}) for row in selected if row.get("verification")]
    summary = {
        "task_count": len(rows),
        "selected_count": len(selected),
        "no_result_count": len(rows) - len(selected),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "hard_check_pass_rate": round(sum(all(check.values()) for check in checks) / len(checks), 4) if checks else None,
    }
    expected_rows = [row for row in rows if row.get("expected")]
    if expected_rows:
        correct = 0
        for row in expected_rows:
            expected = row["expected"]
            actual = "recommend" if row.get("purchased_product_id") else "clarify" if row.get("parsed_request") is None else "reject"
            correct += int(actual == expected)
        summary["behavior_accuracy"] = round(correct / len(expected_rows), 4)
    return summary


@app.route("/", methods=["GET", "POST"])
def index():
    instruction = request.form.get("instruction", "")
    task_id = request.form.get("task_id", "")
    if task_id and task_id != "":
        selected_task = next((task for task in tasks if task["task_id"] == task_id), None)
        if selected_task and not instruction.strip():
            instruction = selected_task["instruction"]
    result = None
    clarification = None
    if request.method == "POST" and instruction.strip():
        current_instruction = instruction.strip()
        previous_instruction = session.get("pending_instruction")
        if previous_instruction:
            current_instruction = f"{previous_instruction} Additional user information: {current_instruction}"
        result = run_with_mode(current_instruction, request.form.get("mode", "hybrid"))
        if result.get("parsed_request") is None:
            clarification = "I need a little more detail. Please specify the product type (shirt or mug) and the theme or tag you want."
            session["pending_instruction"] = current_instruction
        else:
            session.pop("pending_instruction", None)
    return render_template_string(
        PAGE,
        examples=EXAMPLES,
        tasks=tasks,
        instruction=instruction,
        result=result,
        product=products_by_id.get(result.get("purchased_product_id")) if result else None,
        products=products_by_id,
        evaluation={},
        batch_results=[],
        clarification=clarification,
        mode=request.form.get("mode", "hybrid"),
        batch_evaluation={},
        active_model=agent.model_client.model,
        llm_enabled=agent.model_client.enabled,
    )


@app.post("/batch")
def batch():
    global last_batch_results, last_batch_evaluation
    uploaded = request.files.get("tasks_file")
    if uploaded is None or not uploaded.filename:
        return "Missing tasks_file", 400
    try:
        rows = [json.loads(line) for line in uploaded.read().decode("utf-8-sig").splitlines() if line.strip()]
        if not rows or any(not row.get("task_id") or not row.get("instruction") for row in rows):
            raise ValueError("each row needs task_id and instruction")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return f"Invalid JSONL task file: {exc}", 400
    mode = request.form.get("batch_mode", "hybrid")
    last_batch_results = []
    for row in rows:
        result = run_with_mode(str(row["instruction"]), mode)
        last_batch_results.append({"task_id": row["task_id"], "expected": row.get("expected"), "scenario": row.get("scenario"), **result})
    last_batch_evaluation = summarize_batch(last_batch_results)
    return render_template_string(
        PAGE,
        examples=EXAMPLES,
        tasks=tasks,
        instruction="",
        result=None,
        product=None,
        products=products_by_id,
        evaluation={},
        batch_results=last_batch_results,
        clarification=None,
        mode="hybrid",
        batch_evaluation=last_batch_evaluation,
        active_model=agent.model_client.model,
        llm_enabled=agent.model_client.enabled,
    )


@app.get("/batch/download")
def download_batch():
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in last_batch_results)
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype="application/jsonl",
        as_attachment=True,
        download_name="batch_results.jsonl",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
