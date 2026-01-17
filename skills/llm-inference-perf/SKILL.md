---
name: llm-inference-perf
description: Evaluate LLM inference performance from baseline CSV data and compute performance such as per-card end-to-end throughput under latency constraints (ttft, tpot) and sequence lengths(option); use to compare serveral chips or to answer questions about throughput under specific latency targets.
---

# LLM Inference Perf

## Overview

通过从 CSV 基线数据中选择 prefill/decode 吞吐，结合 ttft/tpot 约束并平衡 prefill 与 decode 容量，估算每卡 LLM 推理吞吐。

## Workflow

### 1) Gather inputs

收集用户需求：

- `ttft_ms` (time to first token)
- `tpot_ms` (time per output token)
- `ttft_s` (prefill 目标 TTFT 档位，若客户有明确要求)
- `seq_len_in`, `seq_len_out`（若未提供且 CSV 含默认值，可直接读取）
- target chip(s) to evaluate or compare（若未指定则使用 CSV 内全部芯片）

### 2) Load baseline data

基线数据位于 `SKILL.md` 同级的 `data/` 目录。使用 `references/baseline-schema.md` 中的字段与规则。

### 3) Compute and compare

使用 `scripts/estimate_throughput.py` 进行基线计算。prefill/decode 延迟档位从 CSV 列名读取：若客户明确指定但 CSV 中不存在对应档位，需反馈无法满足并等待新增仿真数据；若未指定，则输出该芯片在 CSV 中已有的全部档位结果。
端到端吞吐默认采用可调配芯片数量的均衡方案，并输出 2 的幂芯片配比；若客户指定固定配比，则按固定配比计算。

```bash
python3 scripts/estimate_throughput.py \
  --csv data/baseline.csv \
  --chip chip-a \
  --chip chip-b \
  --ttft-s 1 \
  --tpot-ms 50 \
  --seq-in 2048 \
  --seq-out 512
```

如果提供多个芯片，输出相对第一个芯片的倍率。
若客户指定的芯片或档位在 CSV 中不存在，提示缺少数据并继续输出其他芯片结果。

### 示例输出（含缺失数据提示）

```
warning: chip 'chip-x' not found in CSV
warning: chip 'chip-b' skipped: decode target 5ms not in CSV available buckets [10, 20, 50, 80]

chip: chip-a
  prefill: 1s, tput=20000.00 tok/s
  decode:  20ms, tput=8000.00 tok/s
  rps: prefill=9.7656, decode=15.6250, e2e=9.7656
  e2e_tokens_s: 25000.00
  mode: balanced (prefill:decode chips 16:8)
  estimates_ms: ttft=102.48, tpot=0.12
```

如需固定配比，增加参数例如 `--ratio-prefill 1 --ratio-decode 1`。

### 未来扩展（占位）

- [ ] 新增仿真功能：当 CSV 缺失档位时生成估算值
- [ ] 支持按模型/批大小/并发度筛选基线
- [ ] 输出表格或 CSV 报告

## Output expectations

返回：

- 每个芯片选中的 prefill/decode 档位
- 端到端每卡吞吐（req/s 与 tokens/s）
- 对比时的芯片倍率
- 当客户指定档位但 CSV 缺失时的反馈
- 采用的吞吐计算方案（均衡或固定配比）
- 若提供 `TCO_per_GPU`，输出性价比对比
