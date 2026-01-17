# 基线 CSV 字段与规则

## 必填字段

- `chip` (string)：用于 `--chip` 的芯片标识
- `prefill_ttft_<N>s` (float)：prefill 目标 TTFT 为 N 秒时的 tokens/s，字段名与可用档位由 CSV 列名给出
- `decode_tpot_<N>ms` (float)：decode 目标 TPOT 为 N 毫秒时的 tokens/s，字段名与可用档位由 CSV 列名给出

## 可选字段

- `model` (string)：模型名称或系列
- `notes` (string)：自由备注
- `ratio_prefill` (int)：固定配比模式下的 prefill 芯片数权重
- `ratio_decode` (int)：固定配比模式下的 decode 芯片数权重
- `seq_len_in` (int)：默认输入长度，若 CLI 未提供 `--seq-in` 则使用
- `seq_len_out` (int)：默认输出长度，若 CLI 未提供 `--seq-out` 则使用
- `TCO_per_GPU` (float)：单卡成本（用于性价比计算）

## 选择规则

1) prefill/decode 的延迟档位从 CSV 中已有列名提取，不预设固定档位。
2) 如果客户明确指定了 `ttft_s` 或 `tpot_ms`，但 CSV 中缺失对应档位，则直接反馈无法满足。
3) 如果客户未指定档位要求，则输出 CSV 中该芯片已有的全部档位结果（prefill 和 decode 均适用）。

## 吞吐计算

给定 `seq_len_in`, `seq_len_out`：

- `prefill_rps = prefill_tput / seq_len_in`
- `decode_rps = decode_tput / seq_len_out`

### 方案 A（默认）：调节 prefill/decode 芯片数量使 rps 匹配

当允许调整 prefill 与 decode 使用的芯片数量时，按 rps 匹配进行均衡。记 prefill 侧芯片数为 `n_prefill`，decode 侧为 `n_decode`，则：

- `n_prefill * prefill_rps ≈ n_decode * decode_rps`
- 选择整数配比（要求为 2 的幂）：`n_prefill = 2^a`，`n_decode = 2^b`，并尽量逼近 `decode_rps : prefill_rps`
- 单位总芯片吞吐：`end_to_end_rps = min(n_prefill * prefill_rps, n_decode * decode_rps) / (n_prefill + n_decode)`
- `end_to_end_tokens_s = end_to_end_rps * (seq_len_in + seq_len_out)`

该方案为默认输出，若客户明确指定固定配比则使用方案 B。

### 方案 B（固定配比）：取低的 rps

当 prefill 与 decode 的芯片配比固定时，优先从 CSV 的 `ratio_prefill` / `ratio_decode` 读取；若缺失则默认 1:1。设配比为 `r_prefill : r_decode`：

- `end_to_end_rps = min(r_prefill * prefill_rps, r_decode * decode_rps) / (r_prefill + r_decode)`
- `end_to_end_tokens_s = end_to_end_rps * (seq_len_in + seq_len_out)`

## 约束检查（仅告警）

- `tpot_est_ms = 1000 / decode_tput`
- `ttft_est_ms = 1000 * (seq_len_in / prefill_tput + 1 / decode_tput)`
- 当估算值超过用户目标时给出警告（仅对 TPOT 生效）。`ttft_ms` 是独立指标，不参与选档位。

## 性价比计算（可选）

当 CSV 提供 `TCO_per_GPU` 时：

- `cost_per_tokens_s = TCO_per_GPU / end_to_end_tokens_s`
- `value_ratio_vs_base = base_cost_per_tokens_s / cost_per_tokens_s`
