# llm-inference-perf

用于评估 LLM 推理性能的多 agent 协作 skill 项目。

## 目录

- `skills/llm-inference-perf/SKILL.md`：技能说明与使用方式
- `skills/llm-inference-perf/scripts/estimate_throughput.py`：性能估算脚本
- `skills/llm-inference-perf/references/baseline-schema.md`：CSV 字段与计算规则
- `skills/llm-inference-perf/data/baseline.csv`：示例基线数据

## 多 agent 使用方式

建议将工作拆分为多个角色并行协作：

- 数据准备 agent：维护 `baseline.csv`，补全缺失档位与成本字段
- 规则/公式 agent：维护 `baseline-schema.md` 的规则与公式
- 计算/脚本 agent：维护 `estimate_throughput.py` 的逻辑与输出格式
- 评估/报告 agent：运行脚本并产出对比结论与摘要

如果需要单人使用，按 `SKILL.md` 的流程执行即可。

## 安装到 agent

### Codex CLI

将 skill 目录复制到 `$CODEX_HOME/skills`（默认 `~/.codex/skills`）：

```bash
mkdir -p ~/.codex/skills
cp -R skills/llm-inference-perf ~/.codex/skills/
```

如果你自定义了 `CODEX_HOME`，请替换对应路径。

### Claude Code

将 skill 目录复制到 Claude Code 的技能目录中（以你的配置为准，通常为项目级 `.claude/skills/` 或全局技能目录）：

```bash
mkdir -p .claude/skills
cp -R skills/llm-inference-perf .claude/skills/
```

## 快速开始

```bash
python3 skills/llm-inference-perf/scripts/estimate_throughput.py \
  --csv skills/llm-inference-perf/data/baseline.csv \
  --chip GB200 \
  --chip H200 \
  --ttft-s 1 \
  --tpot-ms 50
```
