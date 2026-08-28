# 任务1_Agent工作流构建材料包

本目录包含购物 Agent 的代码、数据、评测脚本、运行结果和实验报告。仓库根目录的 `README.md` 提供项目总览；本文件提供更详细的运行说明。

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r "任务1_Agent工作流构建_材料包\requirements.txt"
.\.venv\Scripts\python.exe "任务1_Agent工作流构建_材料包\starter\simulate_agent.py" --limit 5
```


真实模型配置放在 `.env`，参考 `.env.example`。未配置 API 时，Agent 会使用本地 fallback 解析器。

## Web Demo

安装依赖后，在项目根目录启动 Flask 页面：

```powershell
.\.venv\Scripts\python.exe -m pip install -r "任务1_Agent工作流构建_材料包\requirements.txt"
.\.venv\Scripts\python.exe "任务1_Agent工作流构建_材料包\starter\app.py"
```

浏览器打开 `http://127.0.0.1:5000`。页面支持自然语言需求输入、推荐商品、候选排序、约束检查、Agent trace 和评测摘要。

页面中的决策模式含义：

- `Hybrid Agent`：千问解析需求，Python 本地检索、排序并验证，作为主方案。
- `Rule baseline`：本地规则解析和检索，不调用模型，用于稳定性对照。
- `LLM direct baseline`：让千问直接从商品库选择，不经过本地约束验证，用于暴露模型直推风险。


## 评测（可选）

如果只想体验网页，可以不运行本节命令。下面命令用于复现实验报告中的结果。
评测默认复用已有结果，避免重复消耗 API 配额；使用 `--rerun` 才会重新调用 Agent。

公开任务评测：

..\..\.venv\Scripts\python.exe evaluate.py --protocol recommendation
```

困难任务评测：
可靠性任务评测：

```powershell
..\..\.venv\Scripts\python.exe simulate_agent.py --tasks ..\data\tasks2.jsonl --out ..\outputs\tasks2_results.jsonl --limit 19
..\..\.venv\Scripts\python.exe evaluate.py --tasks ..\data\tasks2.jsonl --results ..\outputs\tasks2_results.jsonl --out ..\outputs\tasks2_evaluation.json --protocol behavior
```

`tasks.jsonl` 用于检查普通购物需求能否正确推荐商品。`tasks2.jsonl` 是额外设计的困难任务，包含信息不完整、约束冲突、价格边界和无解等情况，用于检查系统是否会正确推荐、拒绝或要求补充信息。


如需复现实验报告中的离线对照和消融实验：

```powershell
..\..\.venv\Scripts\python.exe experiment.py --mode rule --out ..\outputs\experiment_rule.json
..\..\.venv\Scripts\python.exe experiment.py --mode rule --ablation no_preference --out ..\outputs\experiment_no_preference.json
..\..\.venv\Scripts\python.exe experiment.py --mode rule --ablation no_verification --out ..\outputs\experiment_no_verification.json
```


`--mode hybrid` 会调用千问；`--mode direct_llm` 是不经过本地校验的对照，会消耗 API 配额。
