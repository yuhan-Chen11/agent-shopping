# 任务1_Agent工作流构建材料包
本目录包含购物 Agent 的代码、数据、评测脚本、运行结果和实验报告。

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r "任务1_Agent工作流构建_材料包\requirements.txt"
.\.venv\Scripts\python.exe "任务1_Agent工作流构建_材料包\starter\simulate_agent.py" --limit 5
```

真实模型配置放在 `.env`，参考 `.env.example`。未配置 API 时，Agent 会使用本地 fallback 解析器。不要将 `.env` 提交到 GitHub。

## Web Demo

```powershell
.\.venv\Scripts\python.exe "任务1_Agent工作流构建_材料包\starter\app.py"
```

浏览器打开 `http://127.0.0.1:5000`。

## 评测（可选）

```powershell
cd "任务1_Agent工作流构建_材料包\starter"
..\..\.venv\Scripts\python.exe simulate_agent.py --limit 50
..\..\.venv\Scripts\python.exe evaluate.py --protocol recommendation
```

可靠性任务评测：

```powershell
..\..\.venv\Scripts\python.exe simulate_agent.py --tasks ..\data\tasks2.jsonl --out ..\outputs\tasks2_results.jsonl --limit 19
..\..\.venv\Scripts\python.exe evaluate.py --tasks ..\data\tasks2.jsonl --results ..\outputs\tasks2_results.jsonl --out ..\outputs\tasks2_evaluation.json --protocol behavior
```

`tasks2.jsonl` 共 19 条，覆盖 `paraphrase`、`unseen_paraphrase`、信息不完整、约束冲突、价格边界、无解和不存在标签等情况。

## 离线对照和消融实验

```powershell
..\..\.venv\Scripts\python.exe experiment.py --mode rule --out ..\outputs\experiment_rule.json
..\..\.venv\Scripts\python.exe experiment.py --mode rule --ablation no_preference --out ..\outputs\experiment_no_preference.json
..\..\.venv\Scripts\python.exe experiment.py --mode rule --ablation no_verification --out ..\outputs\experiment_no_verification.json
```

`--mode hybrid` 会调用千问；`--mode direct_llm` 是不经过本地校验的对照，会消耗 API 配额。
```

你本地 README 我刚才已经改成更完整的版本了，优先用文件里的版本。
