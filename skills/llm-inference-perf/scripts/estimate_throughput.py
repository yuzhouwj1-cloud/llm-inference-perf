#!/usr/bin/env python3
import argparse
import csv
import re
import sys
import math


def extract_buckets(prefix, unit, row):
    buckets = set()
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(unit)}$")
    for key, value in row.items():
        match = pattern.match(key)
        if match and value != "":
            buckets.add(int(match.group(1)))
    return sorted(buckets)


def require_bucket(target, prefix, unit, row):
    if target is None:
        return None
    if int(target) != target:
        raise ValueError(f"{prefix} target must be an integer {unit} value")
    target = int(target)
    buckets = extract_buckets(prefix, unit, row)
    if not buckets:
        raise ValueError(f"no available {prefix} buckets found in CSV")
    if target not in buckets:
        raise ValueError(
            f"{prefix} target {target}{unit} not in CSV available buckets {buckets}"
        )
    return target


def available_buckets(prefix, unit, row):
    buckets = extract_buckets(prefix, unit, row)
    if not buckets:
        raise ValueError(f"no available {prefix} buckets found in CSV")
    return buckets


def parse_csv(path):
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty")
    return rows


def get_chip_row(rows, chip):
    matches = [row for row in rows if row.get("chip") == chip]
    if not matches:
        return None, f"chip '{chip}' not found in CSV"
    if len(matches) > 1:
        return matches[0], f"chip '{chip}' has {len(matches)} rows; using the first row"
    return matches[0], None


def to_float(row, key):
    if key not in row:
        raise ValueError(f"missing required column '{key}'")
    try:
        return float(row[key])
    except ValueError as exc:
        raise ValueError(f"column '{key}' is not a number: {row[key]}") from exc


def compute_combo(
    row,
    chip,
    prefill_bucket,
    decode_bucket,
    ttft_target_ms,
    tpot_ms,
    seq_in,
    seq_out,
    ratio_prefill,
    ratio_decode,
):
    warnings = []

    prefill_tput = to_float(row, f"prefill_ttft_{prefill_bucket}s")
    decode_tput = to_float(row, f"decode_tpot_{decode_bucket}ms")

    prefill_rps = prefill_tput / seq_in
    decode_rps = decode_tput / seq_out
    if ratio_prefill is not None and ratio_decode is not None:
        total_ratio = ratio_prefill + ratio_decode
        prefill_share = ratio_prefill / total_ratio
        decode_share = ratio_decode / total_ratio
        e2e_rps = min(prefill_share * prefill_rps, decode_share * decode_rps)
        mode = "fixed_ratio"
        balance_ratio_prefill = None
        balance_ratio_decode = None
    else:
        if prefill_rps == 0 or decode_rps == 0:
            e2e_rps = 0.0
            balance_ratio_prefill = 0
            balance_ratio_decode = 0
        else:
            target_ratio = decode_rps / prefill_rps
            max_pow = 10
            best = (0, 0, float("inf"))
            for a in range(max_pow + 1):
                for b in range(max_pow + 1):
                    ratio = (2 ** a) / (2 ** b)
                    error = abs(math.log2(ratio) - math.log2(target_ratio))
                    if error < best[2]:
                        best = (a, b, error)
            balance_ratio_prefill = 2 ** best[0]
            balance_ratio_decode = 2 ** best[1]
            total_ratio = balance_ratio_prefill + balance_ratio_decode
            prefill_share = balance_ratio_prefill / total_ratio
            decode_share = balance_ratio_decode / total_ratio
            e2e_rps = min(prefill_share * prefill_rps, decode_share * decode_rps)
        mode = "balanced"
    e2e_tokens_s = e2e_rps * (seq_in + seq_out)

    tpot_est_ms = 1000.0 / decode_tput
    ttft_est_ms = 1000.0 * (seq_in / prefill_tput + 1.0 / decode_tput)

    tco_per_gpu = None
    cost_per_rps = None
    cost_per_tokens_s = None
    if row.get("TCO_per_GPU"):
        try:
            tco_per_gpu = float(row["TCO_per_GPU"])
            if e2e_rps > 0:
                cost_per_rps = tco_per_gpu / e2e_rps
            if e2e_tokens_s > 0:
                cost_per_tokens_s = tco_per_gpu / e2e_tokens_s
        except ValueError:
            warnings.append("TCO_per_GPU is not a number; cost metrics skipped")

    if tpot_ms is not None and tpot_est_ms > tpot_ms:
        warnings.append(
            f"tpot_est_ms={tpot_est_ms:.2f} exceeds target {tpot_ms}ms"
        )
    return {
        "chip": chip,
        "prefill_bucket": prefill_bucket,
        "decode_bucket": decode_bucket,
        "prefill_tput": prefill_tput,
        "decode_tput": decode_tput,
        "prefill_rps": prefill_rps,
        "decode_rps": decode_rps,
        "e2e_rps": e2e_rps,
        "e2e_tokens_s": e2e_tokens_s,
        "mode": mode,
        "balance_ratio_prefill": balance_ratio_prefill,
        "balance_ratio_decode": balance_ratio_decode,
        "ratio_prefill": ratio_prefill,
        "ratio_decode": ratio_decode,
        "tco_per_gpu": tco_per_gpu,
        "cost_per_rps": cost_per_rps,
        "cost_per_tokens_s": cost_per_tokens_s,
        "tpot_est_ms": tpot_est_ms,
        "ttft_est_ms": ttft_est_ms,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Estimate per-card LLM throughput from baseline CSV"
    )
    parser.add_argument("--csv", default="data/baseline.csv")
    parser.add_argument("--chip", action="append")
    parser.add_argument("--ttft-s", type=float)
    parser.add_argument("--tpot-ms", type=float)
    parser.add_argument("--ratio-prefill", type=int)
    parser.add_argument("--ratio-decode", type=int)
    parser.add_argument("--seq-in", type=int)
    parser.add_argument("--seq-out", type=int)
    args = parser.parse_args()

    if (args.ratio_prefill is None) != (args.ratio_decode is None):
        raise ValueError("ratio-prefill and ratio-decode must be provided together")
    if args.ratio_prefill is not None and (args.ratio_prefill <= 0 or args.ratio_decode <= 0):
        raise ValueError("ratio-prefill and ratio-decode must be positive integers")

    rows = parse_csv(args.csv)
    ttft_target_ms = args.ttft_s * 1000.0 if args.ttft_s is not None else None

    chips = args.chip if args.chip else sorted({row.get("chip") for row in rows if row.get("chip")})
    results = []
    for chip in chips:
        row, warn = get_chip_row(rows, chip)
        if row is None:
            print(f"warning: {warn}")
            continue
        ratio_prefill = args.ratio_prefill
        ratio_decode = args.ratio_decode
        if ratio_prefill is None and row.get("ratio_prefill") and row.get("ratio_decode"):
            try:
                ratio_prefill = int(row["ratio_prefill"])
                ratio_decode = int(row["ratio_decode"])
            except ValueError:
                print(
                    f"warning: chip '{chip}' has non-integer ratio fields; ignoring"
                )

        seq_in = args.seq_in
        seq_out = args.seq_out
        if seq_in is None and row.get("seq_len_in"):
            try:
                seq_in = int(row["seq_len_in"])
            except ValueError:
                print(
                    f"warning: chip '{chip}' has non-integer seq_len_in; value ignored"
                )
        if seq_out is None and row.get("seq_len_out"):
            try:
                seq_out = int(row["seq_len_out"])
            except ValueError:
                print(
                    f"warning: chip '{chip}' has non-integer seq_len_out; value ignored"
                )
        if seq_in is None or seq_out is None:
            print(
                f"warning: chip '{chip}' skipped: seq_len_in/seq_len_out not provided and not found in CSV"
            )
            continue
        try:
            prefill_bucket = require_bucket(args.ttft_s, "prefill_ttft_", "s", row)
            decode_bucket = require_bucket(args.tpot_ms, "decode_tpot_", "ms", row)
        except ValueError as exc:
            print(f"warning: chip '{chip}' skipped: {exc}")
            continue

        prefill_buckets = (
            [prefill_bucket]
            if prefill_bucket is not None
            else available_buckets("prefill_ttft_", "s", row)
        )
        decode_buckets = (
            [decode_bucket]
            if decode_bucket is not None
            else available_buckets("decode_tpot_", "ms", row)
        )

        chip_results = []
        for prefill in prefill_buckets:
            for decode in decode_buckets:
                combo = compute_combo(
                    row,
                    chip,
                    prefill,
                    decode,
                    ttft_target_ms,
                    args.tpot_ms,
                    seq_in,
                    seq_out,
                    ratio_prefill,
                    ratio_decode,
                )
                if warn:
                    combo["warnings"].append(warn)
                chip_results.append(combo)
        if chip_results:
            results.append(chip_results)

    if not results:
        raise ValueError("no chips available for output after filtering")

    base = results[0]
    base_lookup = {
        (entry["prefill_bucket"], entry["decode_bucket"]): entry
        for entry in base
    }
    for chip_results in results:
        for result in chip_results:
            print(f"chip: {result['chip']}")
            print(
                f"  prefill: {result['prefill_bucket']}s, tput={result['prefill_tput']:.2f} tok/s"
            )
            print(
                f"  decode:  {result['decode_bucket']}ms, tput={result['decode_tput']:.2f} tok/s"
            )
            print(
                f"  rps: prefill={result['prefill_rps']:.4f}, decode={result['decode_rps']:.4f}, e2e={result['e2e_rps']:.4f}"
            )
            print(f"  e2e_tokens_s: {result['e2e_tokens_s']:.2f}")
            if result["mode"] == "balanced":
                print(
                    "  mode: balanced (prefill:decode chips "
                    f"{result['balance_ratio_prefill']}:{result['balance_ratio_decode']})"
                )
            else:
                print(
                    "  mode: fixed_ratio "
                    f"({result['ratio_prefill']}:{result['ratio_decode']})"
                )
            if result["tco_per_gpu"] is not None:
                print(f"  tco_per_gpu: {result['tco_per_gpu']:.2f}")
                print(
                    "  cost_per_tokens_s: "
                    f"{result['cost_per_tokens_s']:.4f}"
                )
            print(
                f"  estimates_ms: ttft={result['ttft_est_ms']:.2f}, tpot={result['tpot_est_ms']:.2f}"
            )
            base_entry = base_lookup.get(
                (result["prefill_bucket"], result["decode_bucket"])
            )
            if base_entry and base_entry is not result:
                ratio = (
                    result["e2e_rps"] / base_entry["e2e_rps"]
                    if base_entry["e2e_rps"]
                    else 0.0
                )
                print(f"  ratio_vs_{base_entry['chip']}: {ratio:.3f}x")
                if (
                    result["cost_per_tokens_s"] is not None
                    and base_entry["cost_per_tokens_s"] is not None
                    and base_entry["cost_per_tokens_s"] > 0
                ):
                    cost_ratio = (
                        base_entry["cost_per_tokens_s"] / result["cost_per_tokens_s"]
                    )
                    print(f"  value_ratio_vs_{base_entry['chip']}: {cost_ratio:.3f}x")
            if result["warnings"]:
                print("  warnings:")
                for warn in result["warnings"]:
                    print(f"    - {warn}")
            print("")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
