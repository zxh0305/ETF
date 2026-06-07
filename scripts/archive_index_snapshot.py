#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指数估值历史快照归档脚本 v2.0
==============================
每日采集完成后，对 etf_valuation_latest.json 按行业/指数聚合，
生成 archive/index_valuation_history/YYYY-MM-DD.json

v2.0 变更：
  - 不再依赖 tracking_index 字段（该字段始终为None）
  - 改用 pe_pb_source 字段推导ETF所属行业/指数
  - 新增 etf_snapshot 维度（每个ETF的估值快照）
  - 从ETF名称关键词匹配宽基指数

快照字段：
  indices: 按 index_code/index_name 聚合
  etf_snapshot: 每个ETF的估值数据
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
ARCHIVE_DIR = BASE_DIR / "archive" / "index_valuation_history"
INPUT_FILE = BASE_DIR / "data" / "etf_valuation_latest.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("archive_index_v2")


# ============================================================================
# ETF → 宽基指数名称匹配
# ============================================================================
BROAD_INDEX_KEYWORDS = {
    "沪深300": ["沪深300", "HS300", "300ETF"],
    "中证500": ["中证500", "500ETF"],
    "上证50": ["上证50", "50ETF"],
    "中证1000": ["中证1000", "1000ETF"],
    "中证800": ["中证800", "800ETF"],
    "上证180": ["上证180", "180ETF"],
    "中证100": ["中证100"],
    "上证红利": ["上证红利"],
    "科创50": ["科创50", "科创板50"],
    "创业板": ["创业板"],
    "深证100": ["深证100"],
    "深证红利": ["深证红利"],
    "中证红利": ["中证红利", "红利低波", "红利低波100"],
    "恒生科技": ["恒生科技"],
    "恒生医疗": ["恒生医疗"],
    "纳斯达克": ["纳斯达克", "纳指"],
    "标普500": ["标普500"],
    "日经225": ["日经"],
}


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


def extract_index_from_name(etf_name: str) -> Optional[str]:
    """从ETF名称匹配宽基指数"""
    for idx_name, keywords in BROAD_INDEX_KEYWORDS.items():
        for kw in keywords:
            if kw in etf_name:
                return idx_name
    return None


def extract_industry_from_source(pe_pb_source: str) -> Optional[str]:
    """从pe_pb_source提取行业名"""
    if not pe_pb_source or pe_pb_source == "unavailable":
        return None

    # "申万-计算机(334股)" → "计算机"
    if "申万-" in pe_pb_source:
        part = pe_pb_source.split("申万-")[1]
        return part.split("(")[0].strip()

    # "穿透-电子,石油石化,通信" → "电子"（取第一个行业）
    if "穿透-" in pe_pb_source:
        part = pe_pb_source.split("穿透-")[1]
        first_ind = part.split(",")[0].strip()
        return first_ind

    # "中证指数官方(6年1550条)-沪深300" → "沪深300"
    if "中证指数官方" in pe_pb_source and "-" in pe_pb_source:
        return pe_pb_source.rsplit("-", 1)[-1].strip()

    # "降级(估算PE+申万分位)" → None
    # "CNINFO" → None
    return None


def classify_etf(etf: Dict) -> str:
    """
    分类ETF到指数/行业组
    
    返回格式: "宽基:沪深300" / "行业:计算机" / "其他"
    """
    name = etf.get("name", "")
    source = etf.get("pe_pb_source", "")

    # 1. 先从名称匹配宽基指数
    idx_name = extract_index_from_name(name)
    if idx_name:
        return f"宽基:{idx_name}"

    # 2. 从pe_pb_source提取行业
    ind_name = extract_industry_from_source(source)
    if ind_name:
        return f"行业:{ind_name}"

    # 3. 无法分类
    return "其他:未分类"


def build_index_snapshot(etf_data: List[Dict]) -> List[Dict]:
    """按指数/行业分组聚合ETF数据"""
    group_map: Dict[str, Dict[str, Any]] = {}

    for etf in etf_data:
        group_key = classify_etf(etf)
        
        if group_key not in group_map:
            group_type, group_name = group_key.split(":", 1)
            group_map[group_key] = {
                "index_code": group_key,
                "index_name": group_name,
                "index_type": group_type,
                "etf_codes": [],
                "pe_ttm_list": [],
                "pb_list": [],
                "pe_percentile_list": [],
                "pb_percentile_list": [],
                "quality_flags": [],
            }

        entry = group_map[group_key]
        entry["etf_codes"].append(etf.get("code", ""))
        entry["quality_flags"].append(etf.get("pe_pb_source", "unknown"))

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

    # 汇总
    result = []
    for key, entry in group_map.items():
        pe_vals = entry.pop("pe_ttm_list")
        pb_vals = entry.pop("pb_list")
        pe_pct_vals = entry.pop("pe_percentile_list")
        pb_pct_vals = entry.pop("pb_percentile_list")

        def median(lst):
            if not lst:
                return None
            s = sorted(lst)
            n = len(s)
            if n % 2 == 1:
                return s[n // 2]
            return (s[n // 2 - 1] + s[n // 2]) / 2

        flags = entry.pop("quality_flags")
        quality = "real" if any("中证指数官方" in str(f) or "乐咕" in str(f) for f in flags) else "estimated"

        result.append({
            "index_code": entry["index_code"],
            "index_name": entry["index_name"],
            "index_type": entry["index_type"],
            "etf_count": len(entry["etf_codes"]),
            "etf_codes": entry["etf_codes"],
            "pe_ttm": round(median(pe_vals), 2) if pe_vals else None,
            "pb": round(median(pb_vals), 3) if pb_vals else None,
            "pe_percentile": round(median(pe_pct_vals), 1) if pe_pct_vals else None,
            "pb_percentile": round(median(pb_pct_vals), 1) if pb_pct_vals else None,
            "quality_flag": quality,
        })

    # 按类型和数量排序
    result.sort(key=lambda x: (0 if x["index_type"] == "宽基" else 1 if x["index_type"] == "行业" else 2, -x["etf_count"]))

    return result


def build_etf_snapshot(etf_data: List[Dict]) -> List[Dict]:
    """构建每个ETF的估值快照"""
    snapshot = []
    for etf in etf_data:
        snapshot.append({
            "code": etf.get("code", ""),
            "name": etf.get("name", ""),
            "price": to_float(etf.get("price")),
            "change_pct": to_float(etf.get("change_pct")),
            "pe_ttm": to_float(etf.get("pe_ttm")),
            "pb": to_float(etf.get("pb")),
            "pe_percentile": to_float(etf.get("pe_percentile")),
            "pb_percentile": to_float(etf.get("pb_percentile")),
            "pe_pb_source": etf.get("pe_pb_source", ""),
            "percentile_real_flag": etf.get("percentile_real_flag"),
            "valuation_signal": etf.get("valuation_signal", ""),
            "avg_amount_20d": to_float(etf.get("avg_amount_20d")),
            "group": classify_etf(etf),
        })
    return snapshot


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

    logger.info(f"开始归档今日指数快照 v2.0: {today}")
    logger.info(f"  ETF总数: {len(etf_data)}")

    # 分类统计
    type_counts = {"宽基": 0, "行业": 0, "其他": 0}
    for etf in etf_data:
        g = classify_etf(etf)
        gtype = g.split(":")[0]
        type_counts[gtype] = type_counts.get(gtype, 0) + 1
    logger.info(f"  分类: 宽基={type_counts.get('宽基',0)} 行业={type_counts.get('行业',0)} 其他={type_counts.get('其他',0)}")

    # 生成快照
    index_snapshot = build_index_snapshot(etf_data)
    etf_snapshot = build_etf_snapshot(etf_data)

    output = {
        "meta": {
            "date": today,
            "collect_time": collect_time,
            "etf_total": len(etf_data),
            "index_count": len(index_snapshot),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "v2.0",
        },
        "indices": index_snapshot,
        "etf_snapshot": etf_snapshot,
    }

    out_file = ARCHIVE_DIR / f"{today}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 快照已保存: {out_file}")
    logger.info(f"  指数/行业分组: {len(index_snapshot)}个")

    # 统计分组类型
    broad_groups = [i for i in index_snapshot if i["index_type"] == "宽基"]
    industry_groups = [i for i in index_snapshot if i["index_type"] == "行业"]
    other_groups = [i for i in index_snapshot if i["index_type"] == "其他"]

    logger.info(f"  宽基指数: {len(broad_groups)}个")
    logger.info(f"  行业分组: {len(industry_groups)}个")
    logger.info(f"  其他: {len(other_groups)}个")

    # 宽基指数详情
    if broad_groups:
        logger.info("  宽基指数:")
        for idx in broad_groups:
            logger.info(
                f"    {idx['index_name']:10s} ETF数={idx['etf_count']:3d} "
                f"PE={idx['pe_ttm']} PB={idx['pb']} "
                f"分位PE={idx['pe_percentile']}% PB={idx['pb_percentile']}% "
                f"[{idx['quality_flag']}]"
            )

    # 行业分组详情（低估TOP5）
    if industry_groups:
        low_val = [i for i in industry_groups if i.get("pe_percentile") and i["pe_percentile"] <= 30]
        if low_val:
            logger.info(f"  低估行业({len(low_val)}个):")
            for idx in sorted(low_val, key=lambda x: x.get("pe_percentile", 999)):
                logger.info(
                    f"    ✅{idx['index_name']:10s} ETF数={idx['etf_count']:3d} "
                    f"PE分位={idx['pe_percentile']}% PB分位={idx['pb_percentile']}%"
                )

    return output


if __name__ == "__main__":
    main()
