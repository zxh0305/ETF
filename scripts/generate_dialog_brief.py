#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF每日简报生成器 v3.0 - 真实历史分位版
========================================
明确区分真实分位和非分位，不误导用户

输出文件: output/dialog_brief_latest.txt
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).parent.parent.resolve()
INPUT_FILE = BASE_DIR / "output" / "low_valuation_candidates_latest.json"
OUTPUT_FILE = BASE_DIR / "output" / "dialog_brief_latest.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("brief_gen_v3")


def format_amount(amount: float) -> str:
    """格式化成交额，避免科学计数法"""
    if amount is None:
        return "无数据"
    if amount >= 1_000_000_000:
        return f"{amount/1_000_000_000:.1f}亿"
    elif amount >= 10_000_000:
        return f"{int(amount/10_000_000)}千万"      # 整千万，如 2千万
    else:
        return f"{int(amount/10_000)}万"          # 整万，如 350万


def generate_brief() -> str:
    """生成简报"""
    logger.info("=" * 70)
    logger.info("生成ETF每日简报 v3.0")
    logger.info("=" * 70)
    
    # 加载数据
    if not INPUT_FILE.exists():
        logger.error(f"输入文件不存在: {INPUT_FILE}")
        return "数据未就绪"
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    stats = data.get("stats", {})
    formal_pool = data.get("formal_pool", [])
    observation_pool = data.get("observation_pool", [])
    
    # 构建简报
    lines = [
        "=" * 50,
        "  📊 ETF每日观察简报 · " + datetime.now().strftime("%Y年%m月%d日"),
        "=" * 50,
        "",
        "✅ 本次筛选基于真实历史分位数据",
        "",
        "【筛选结果】",
        f"- 正式低估池：{stats.get('formal_pool', 0)} 只",
        f"- 观察池：{stats.get('observation_pool', 0)} 只",
        f"- 数据不可用：{stats.get('unavailable', 0)} 只",
        "",
    ]
    
    # ── 变化信号（从 change_report 读取）────────────────────────────
    change_file = BASE_DIR / "output" / "change_report_latest.json"
    if change_file.exists():
        try:
            with open(change_file, 'r', encoding='utf-8') as f:
                change_data = json.load(f)
            summary = change_data.get("summary", {})
            new_entries = change_data.get("new_entries", [])
            exits = change_data.get("exits", [])
            
            new_count = summary.get("new_entries_count", 0)
            exit_count = summary.get("exits_count", 0)
            
            if new_count > 0 or exit_count > 0:
                lines.append("━" * 50)
                lines.append("📢 今日变化信号")
                lines.append("━" * 50)
                
                if new_count > 0:
                    names = "、".join([e["name"] for e in new_entries[:5]])
                    suffix = "..." if new_count > 5 else ""
                    lines.append(f"🆕 新入选（+{new_count}）：{names}{suffix}")
                
                if exit_count > 0:
                    names = "、".join([e["name"] for e in exits[:5]])
                    suffix = "..." if exit_count > 5 else ""
                    lines.append(f"📤 移出观察（-{exit_count}）：{names}{suffix}")
                
                lines.append("")
        except Exception as e:
            logger.warning(f"读取变化报告失败: {e}")
    # ────────────────────────────────────────────────────────────────
    
    # 正式低估池
    if formal_pool:
        lines.extend([
            "━" * 50,
            "✅ 正式低估候选（满足真实历史分位+流动性条件）",
            "━" * 50,
            "",
        ])
        
        for i, etf in enumerate(formal_pool[:15], 1):
            pe_pct = etf.get("pe_percentile")
            pb_pct = etf.get("pb_percentile")
            amt = etf.get("avg_amount_20d", 0)
            score = etf.get("score", 0)
            
            pe_str = f"PE分位={pe_pct:.1f}%" if pe_pct is not None else "PE分位=N/A"
            pb_str = f"PB分位={pb_pct:.1f}%" if pb_pct is not None else ""
            
            lines.append(
                f"  {i:2d}. {etf['name']}（{etf['code']}）"
            )
            lines.append(
                f"      {pe_str}  {pb_str}  成交额={format_amount(amt)}  评分={score:.0f}"
            )
            lines.append("")
    else:
        lines.extend([
            "━" * 50,
            "⚠️ 暂无满足条件的正式低估候选",
            "━" * 50,
            "",
            "原因：",
            "- 需要真实历史分位数据",
            "- PE分位或PB分位需 ≤ 30%",
            "- 成交额需 ≥ 1亿",
            "",
        ])
    
    # ── 趋势分析（从 etf_analysis_latest.json 读取）───────────────────────
    analysis_file = BASE_DIR / "output" / "etf_analysis_latest.json"
    if analysis_file.exists():
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis = json.load(f)

            # 板块集中度（仅在有数据时显示）
            sectors = analysis.get("sector_concentration", [])
            near_thresh = analysis.get("near_threshold", [])

            if sectors or near_thresh:
                lines.append("━" * 50)
                lines.append("📈 趋势分析")
                lines.append("━" * 50)
                lines.append("")

                # 板块集中度
                if sectors:
                    sector_str = "、".join([f"{s['sector']}{s['count']}只" for s in sectors[:3]])
                    lines.append(f"  🏭 低估池板块分布：{sector_str}")
                    lines.append("")

                # 接近低估ETF
                if near_thresh:
                    lines.append("  🔔 接近低估（PE分位30-36%，距低估阈值≤6%）：")
                    for e in near_thresh[:3]:
                        gap = e.get("gap_to_threshold", 0)
                        gap_str = f"距低估还差{gap}%" if gap > 0 else "已低估"
                        liq = e.get("avg_amount_str", "?")
                        lines.append(
                            f"    · {e['name']}（{e['code']}）"
                            f" PE分位={e['pe_percentile']}%，{gap_str}，成交额={liq}"
                        )
                    lines.append("")
        except Exception as e:
            logger.warning(f"读取分析数据失败: {e}")
    # ────────────────────────────────────────────────────────────────────

    # 观察池
    if observation_pool:
        lines.extend([
            "━" * 50,
            "👀 观察池（有真实分位但未满足低估条件）",
            "━" * 50,
            "",
        ])
        
        for i, etf in enumerate(observation_pool[:10], 1):
            pe_pct = etf.get("pe_percentile")
            pb_pct = etf.get("pb_percentile")
            amt = etf.get("avg_amount_20d", 0)
            reason = etf.get("reason", "")
            
            pe_str = f"PE分位={pe_pct:.1f}%" if pe_pct is not None else ""
            pb_str = f"PB分位={pb_pct:.1f}%" if pb_pct is not None else ""
            
            lines.append(
                f"  {i:2d}. {etf['name']}（{etf['code']}）"
            )
            lines.append(
                f"      {pe_str}  {pb_str}  成交额={format_amount(amt)}"
            )
            lines.append("")
    
    # 说明
    lines.extend([
        "━" * 50,
        "📌 重要说明",
        "━" * 50,
        "",
        "1. **正式低估池**：基于真实历史分位筛选，可信度高",
        "   - 必须有真实历史分位数据（来自乐咕乐股）",
        "   - PE分位 ≤ 30% 或 PB分位 ≤ 30%",
        "   - 成交额 ≥ 1亿（流动性保障）",
        "",
        "2. **观察池**：有真实分位数据，但未满足低估条件",
        "   - 可持续跟踪，等待估值修复",
        "",
        "3. **数据不可用ETF**：无真实历史分位数据",
        f"   - 共 {stats.get('unavailable', 0)} 只",
        "   - 系统不再为其生成mock分位",
        "   - 待扩充数据源后逐步覆盖",
        "",
        "—",
        f"数据来源: 乐咕乐股（20年历史）",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "⚠️ 风险提示: 仅供参考，不构成投资建议",
    ])
    
    brief = "\n".join(lines)
    
    # 保存
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(brief)
    
    logger.info(f"✅ 输出: {OUTPUT_FILE}")
    
    return brief


def main():
    brief = generate_brief()
    print("\n" + brief)


if __name__ == "__main__":
    main()
