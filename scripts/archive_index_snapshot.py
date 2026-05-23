#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指数估值历史快照归档脚本
=========================
每日采集完成后，对 etf_valuation_latest.json 按跟踪指数聚合，
生成 archive/index_valuation_history/YYYY-MM-DD.json

快照字段：date / index_code / index_name / pe_ttm / pb /
          pe_percentile / pb_percentile / source / quality_flag /
          etf_count / etf_codes
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).parent.parent.resolve()
ARCHIVE_DIR = BASE_DIR / "archive" / "index_valuation_history"
INPUT_FILE = BASE_DIR / "data" / "etf_valuation_latest.json"

LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("archive_index")


def to_float(val: Any, default=None):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if val in ("", "N/A", "-", "nan", "None"):
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
    return default


def build_index_snapshot(etf_data: List[Dict]) -> Dict[str, Any]:
    """按跟踪指数聚合ETF数据"""
    # 按 index_code 分组
    index_map: Dict[str, Dict[str, Any]] = {}

    for etf in etf_data:
        ti = etf.get("tracking_index")
        if not ti:
            continue

        code = ti.get("code", "")
        name = ti.get("name", "")
        if not code:
            continue

        if code not in index_map:
            index_map[code] = {
                "index_code": code,
                "index_name": name,
                "source": ti.get("source", ""),
                "etf_codes": [],
                "pe_ttm_list": [],
                "pb_list": [],
                "pe_percentile_list": [],
                "pb_percentile_list": [],
                "quality_flags": [],
            }

        entry = index_map[code]
        entry["etf_codes"].append(etf.get("code", ""))
        entry["quality_flags"].append(etf.get("pe_pb_source", "mock"))

        pe = to_float(etf.get("pe_ttm"))
        pb = to_float(etf.get("pb"))
        pe_pct = to_float(etf.get("pe_percentile"))
        pb_pct = to_float(etf.get("pb_percentile"))

        if pe is not None:
            entry["pe_ttm_list"].append(pe)
        if pb is not None:
            entry["pb_list"].append(pb)
        if pe_pct is not None:
            entry["pe_percentile_list"].append(pe_pct)
        if pb_pct is not None:
            entry["pb_percentile_list"].append(pb_pct)

    # 汇总为单条记录
    result = []
    for code, entry in index_map.items():
        pe_vals = entry.pop("pe_ttm_list")
        pb_vals = entry.pop("pb_list")
        pe_pct_vals = entry.pop("pe_percentile_list")
        pb_pct_vals = entry.pop("pb_percentile_list")

        # 中位数（抗极端值）
        def median(lst):
            if not lst:
                return None
            s = sorted(lst)
            n = len(s)
            if n % 2 == 1:
                return s[n // 2]
            return (s[n // 2 - 1] + s[n // 2]) / 2

        flags = entry.pop("quality_flags")
        # 质量：任一真实即为真实
        quality = "real" if "real" in flags else "mock"

        result.append({
            "index_code": entry["index_code"],
            "index_name": entry["index_name"],
            "source": entry["source"],
            "etf_count": len(entry["etf_codes"]),
            "etf_codes": entry["etf_codes"],
            "pe_ttm": round(median(pe_vals), 2) if pe_vals else None,
            "pb": round(median(pb_vals), 3) if pb_vals else None,
            "pe_percentile": round(median(pe_pct_vals), 1) if pe_pct_vals else None,
            "pb_percentile": round(median(pb_pct_vals), 1) if pb_pct_vals else None,
            "quality_flag": quality,
        })

    return result


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_FILE.exists():
        logger.error(f"输入文件不存在: {INPUT_FILE}")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    meta = raw.get("meta", {})
    etf_data = raw.get("data", [])
    collect_time = meta.get("collect_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info(f"开始归档今日指数快照: {today}")
    logger.info(f"  ETF总数: {len(etf_data)}")

    snapshot = build_index_snapshot(etf_data)

    output = {
        "meta": {
            "date": today,
            "collect_time": collect_time,
            "etf_total": len(etf_data),
            "index_count": len(snapshot),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "indices": snapshot,
    }

    out_file = ARCHIVE_DIR / f"{today}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ 快照已保存: {out_file}")
    logger.info(f"  指数数量: {len(snapshot)}")

    if snapshot:
        logger.info("  Top5:")
        for idx in snapshot[:5]:
            logger.info(
                f"    {idx['index_code']} {idx['index_name']} "
                f"PE={idx['pe_ttm']} PB={idx['pb']} "
                f"分位PE={idx['pe_percentile']}% PB={idx['pb_percentile']}% "
                f"[{idx['quality_flag']}]"
            )

    return output


if __name__ == "__main__":
    main()
