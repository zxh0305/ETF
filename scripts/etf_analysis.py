#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF分析层 v1.0 - 趋势分析与板块轮动
=====================================
分析正式低估池的排名变化、百分位变化、板块轮动信号
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

BASE_DIR = Path(__file__).parent.parent.resolve()
LATEST_FILE = BASE_DIR / "output" / "low_valuation_candidates_latest.json"
PREV_FILE = BASE_DIR / "output" / "low_valuation_candidates_prev.json"
ARCHIVE_DIR = BASE_DIR / "archive"
OUTPUT_FILE = BASE_DIR / "output" / "etf_analysis_latest.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etf_analysis_v1")


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_pool(data: Optional[Dict], pool_name: str = "formal_pool") -> List[Dict]:
    """兼容新旧格式：优先取 formal_pool，否则取 candidates"""
    if data is None:
        return []
    if pool_name in data:
        return data[pool_name]
    return data.get("candidates", [])


def find_prev_archive(current_date: str) -> Optional[Path]:
    """找最近的历史归档（跳过今天）"""
    if not ARCHIVE_DIR.exists():
        return None
    date_dirs = sorted(
        [d for d in ARCHIVE_DIR.iterdir() if d.is_dir() and d.name.startswith("202")],
        reverse=True
    )
    for d in date_dirs:
        if d.name < current_date and (d / "candidates.json").exists():
            return d / "candidates.json"
    return None


def compute_analysis() -> Dict[str, Any]:
    """计算趋势分析"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"📊 ETF趋势分析 | {today_str}")

    # ── 加载今日数据 ────────────────────────────────────────────────
    today_data = load_json(LATEST_FILE)
    if not today_data:
        logger.warning("今日候选数据不存在")
        return {}
    today_formal = get_pool(today_data, "formal_pool")
    today_obs = get_pool(today_data, "observation_pool")

    # ── 加载昨日数据（优先 prev.json，否则从归档）───────────────────
    prev_data = load_json(PREV_FILE)
    prev_source = "prev.json"
    if prev_data:
        prev_meta = prev_data.get("meta", {})
        prev_time = prev_meta.get("generated_at", "")[:10]
        if prev_time == today_str:
            # prev.json 被今天覆盖，从归档找
            archive_path = find_prev_archive(today_str)
            if archive_path:
                prev_data = load_json(archive_path)
                prev_source = archive_path.parent.name
    else:
        archive_path = find_prev_archive(today_str)
        if archive_path:
            prev_data = load_json(archive_path)
            prev_source = archive_path.parent.name

    prev_formal = get_pool(prev_data, "formal_pool") if prev_data else []
    logger.info(f"  今日: {len(today_formal)}只 昨日: {len(prev_formal)}只（来源: {prev_source}）")

    # ── 构建 code -> ETF 映射 ─────────────────────────────────────
    today_map = {e.get("code"): e for e in today_formal}
    prev_map = {e.get("code"): e for e in prev_formal}

    # ── 1. 新入选 / 退出 ───────────────────────────────────────────
    today_codes = set(today_map.keys())
    prev_codes = set(prev_map.keys())
    new_codes = today_codes - prev_codes
    exit_codes = prev_codes - today_codes

    new_entries = []
    for code in sorted(new_codes):
        etf = today_map[code]
        new_entries.append({
            "code": code,
            "name": etf.get("name", ""),
            "pe_percentile": etf.get("pe_percentile"),
            "pb_percentile": etf.get("pb_percentile"),
            "pe_pb_source": etf.get("pe_pb_source", ""),
            "rank": today_formal.index(etf) + 1,
            "score": etf.get("score"),
        })

    exits = []
    for code in sorted(exit_codes):
        etf = prev_map[code]
        exits.append({
            "code": code,
            "name": etf.get("name", ""),
            "pe_percentile": etf.get("pe_percentile"),
            "prev_score": etf.get("score"),
            "pe_pb_source": etf.get("pe_pb_source", ""),
        })

    # ── 2. 排名变化 ────────────────────────────────────────────────
    rank_changes = []
    common_codes = today_codes & prev_codes
    for code in sorted(common_codes):
        today_etf = today_map[code]
        prev_etf = prev_map[code]
        today_rank = today_formal.index(today_etf) + 1
        prev_rank = prev_formal.index(prev_etf) + 1
        rank_diff = prev_rank - today_rank  # 正=上升
        pe_diff = _delta(today_etf.get("pe_percentile"), prev_etf.get("pe_percentile"))
        pb_diff = _delta(today_etf.get("pb_percentile"), prev_etf.get("pb_percentile"))
        score_diff = _delta(today_etf.get("score"), prev_etf.get("score"))
        if rank_diff != 0 or abs(pe_diff or 0) >= 1.0:
            rank_changes.append({
                "code": code,
                "name": today_etf.get("name", ""),
                "prev_rank": prev_rank,
                "curr_rank": today_rank,
                "rank_diff": rank_diff,
                "direction": "up" if rank_diff > 0 else "down",
                "pe_percentile_change": pe_diff,
                "pb_percentile_change": pb_diff,
                "score_change": score_diff,
            })

    # ── 3. 板块集中度分析 ─────────────────────────────────────────
    sector_map: Dict[str, int] = {}
    for etf in today_formal:
        source = etf.get("pe_pb_source", "")
        sector = source.split("(")[0].strip() if source else "未知"
        sector_map[sector] = sector_map.get(sector, 0) + 1

    sectors_ranked = sorted(sector_map.items(), key=lambda x: -x[1])

    # ── 4. 观察池接近低估的ETF（28% ≤ PE分位 ≤ 35%）──────────────────
    # 条件：PE分位在28-35%之间，距低估阈值（30%）不超过5个百分点
    near_threshold = []
    for etf in today_obs[:200]:  # 只看前200
        pe_pct = etf.get("pe_percentile")
        if pe_pct is not None and 27.0 <= pe_pct <= 36.0:
            gap = round(pe_pct - 30, 1)
            avg_amt = etf.get("avg_amount_20d") or 0
            amt_ok = avg_amt >= 100_000_000  # ≥1亿
            near_threshold.append({
                "code": etf.get("code"),
                "name": etf.get("name"),
                "pe_percentile": pe_pct,
                "gap_to_threshold": gap,
                "avg_amount": avg_amt,
                "avg_amount_str": _fmt_amt(avg_amt),
                "liquidity_ok": amt_ok,
                "pe_pb_source": etf.get("pe_pb_source"),
            })
        if len(near_threshold) >= 5:
            break
    near_threshold.sort(key=lambda x: x["gap_to_threshold"])

    # ── 5. 板块轮动信号（对比归档找行业趋势）──────────────────────
    rotation_signals = _compute_rotation(today_formal, prev_formal, prev_data)

    # ── 6. 文本摘要 ───────────────────────────────────────────────
    summary_parts = []
    if new_entries:
        names = "、".join([e["name"] for e in new_entries[:3]])
        suffix = "..." if len(new_entries) > 3 else ""
        summary_parts.append(f"🆕 新入选{len(new_entries)}只：{names}{suffix}")
    if exits:
        names = "、".join([e["name"] for e in exits[:3]])
        suffix = "..." if len(exits) > 3 else ""
        summary_parts.append(f"📤 移出{len(exits)}只：{names}{suffix}")
    if rank_changes:
        ups = [r for r in rank_changes if r["direction"] == "up"]
        downs = [r for r in rank_changes if r["direction"] == "down"]
        if ups:
            names = "、".join([r["name"] for r in ups[:3]])
            summary_parts.append(f"📈 排名上升：{names}")
        if downs:
            names = "、".join([r["name"] for r in downs[:3]])
            summary_parts.append(f"📉 排名下降：{names}")
    if near_threshold and not new_entries:  # 无新入选时才提示
        top = near_threshold[0]
        if top["gap_to_threshold"] <= 0:
            reason = "已低估（流动性不足）" if not top.get("liquidity_ok") else "已低估"
            summary_parts.append(
                f"🔔 观察池关注：{top['name']}（PE分位={top['pe_percentile']}%，{reason}，成交额={top['avg_amount_str']}）"
            )
        else:
            summary_parts.append(
                f"🔔 接近低估：{top['name']}（PE分位={top['pe_percentile']}%，距低估还差{top['gap_to_threshold']}%，成交额={top['avg_amount_str']}）"
            )
    if rotation_signals:
        summary_parts.append(f"🏭 板块轮动：{rotation_signals[0]['signal']}")

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "version": "v1.0",
            "today_formal_count": len(today_formal),
            "prev_formal_count": len(prev_formal),
            "prev_source": prev_source,
        },
        "new_entries": new_entries,
        "exits": exits,
        "rank_changes": rank_changes,
        "sector_concentration": [{"sector": s, "count": c} for s, c in sectors_ranked],
        "near_threshold": near_threshold,
        "rotation_signals": rotation_signals,
        "summary": " | ".join(summary_parts) if summary_parts else "今日无显著变化",
    }


def _fmt_amt(amount: float) -> str:
    """格式化成交额"""
    if amount is None:
        return "无数据"
    if amount >= 1_000_000_000:
        return f"{amount/1_000_000_000:.1f}亿"
    elif amount >= 10_000_000:
        return f"{int(amount/10_000_000)}千万"
    else:
        return f"{int(amount/10_000)}万"


def _delta(curr: Any, prev: Any) -> Optional[float]:
    if curr is None or prev is None:
        return None
    try:
        return round(float(curr) - float(prev), 1)
    except (TypeError, ValueError):
        return None


def _compute_rotation(today_formal: List[Dict], prev_formal: List[Dict],
                       prev_data: Optional[Dict]) -> List[Dict]:
    """分析板块轮动：今日池 vs 昨日池的行业变化"""
    if not prev_data:
        return []

    signals = []

    # 收集今日和昨日的行业分布
    def get_sectors(etf_list):
        sectors = {}
        for e in etf_list:
            src = e.get("pe_pb_source", "")
            sector = src.split("(")[0].strip() if src else "未知"
            sectors[sector] = sectors.get(sector, 0) + 1
        return sectors

    today_sectors = get_sectors(today_formal)
    prev_sectors = get_sectors(prev_formal)

    all_sectors = set(today_sectors.keys()) | set(prev_sectors.keys())
    sector_changes = []
    for sector in all_sectors:
        today_c = today_sectors.get(sector, 0)
        prev_c = prev_sectors.get(sector, 0)
        diff = today_c - prev_c
        if diff != 0:
            sector_changes.append((sector, diff))

    # 排序：变化最大的在前
    sector_changes.sort(key=lambda x: -abs(x[1]))

    # 生成轮动描述
    enter_sectors = [(s, d) for s, d in sector_changes if d > 0]
    exit_sectors = [(s, d) for s, d in sector_changes if d < 0]

    if enter_sectors:
        top_enter = enter_sectors[0]
        signals.append({
            "type": "sector_enter",
            "sector": top_enter[0],
            "change": top_enter[1],
            "signal": f"{top_enter[0]}占比上升+{top_enter[1]}只",
        })
    if exit_sectors:
        top_exit = exit_sectors[0]
        signals.append({
            "type": "sector_exit",
            "sector": top_exit[0],
            "change": top_exit[1],
            "signal": f"{top_exit[0]}占比下降{top_exit[1]}只",
        })

    return signals


def main():
    result = compute_analysis()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    summary = result.get("summary", "无数据")
    logger.info(f"✅ 分析完成: {OUTPUT_FILE}")
    logger.info(f"📋 摘要: {summary}")

    # 输出简洁摘要供管道日志使用
    print(summary)


if __name__ == "__main__":
    main()
