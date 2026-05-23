#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent3: ETF微信日报生成器
=======================
读取screener筛选结果 + 对比报告，生成PPT要求格式的微信日报。

输入文件:
  - output/low_valuation_candidates_latest.json（screener输出）
  - output/change_report_latest.json（对比报告，可选）
  - data/sw_industry_valuation_latest.json（市场温度计，可选）

输出文件:
  - output/daily_report_latest.txt（微信日报，纯文本）
  - output/daily_report_latest.md（详细Markdown版）

日报格式（PPT要求）:
  【ETF低估智能体 | 每日09:20播报】
  📅 日期
  📊 市场温度
  🎯 正式池数量 + 关注池数量
  📋 重点关注清单
  🔄 变化提醒
  💡 操作建议
  ⚠️ 风险提示
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# 配置区
# ============================================================================

BASE_DIR = Path(__file__).parent.parent.resolve()
LATEST_JSON = BASE_DIR / "output" / "low_valuation_candidates_latest.json"
CHANGE_JSON = BASE_DIR / "output" / "change_report_latest.json"
SW_JSON = BASE_DIR / "data" / "sw_industry_valuation_latest.json"

DAILY_TXT = BASE_DIR / "output" / "daily_report_latest.txt"
DAILY_MD = BASE_DIR / "output" / "daily_report_latest.md"

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    logger = logging.getLogger("daily_report")
    logger.setLevel(LOG_LEVEL)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(LOG_LEVEL)
        h.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(h)
    return logger


logger = setup_logging()


def load_json(path: Path, default=None):
    """安全加载JSON"""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def to_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


# ============================================================================
# 市场温度计
# ============================================================================

def get_market_temperature() -> dict:
    """从申万行业数据计算市场温度"""
    sw = load_json(SW_JSON, {})
    industries = sw.get("industries", {})
    meta = sw.get("meta", {})

    if not industries:
        return {"icon": "❓", "label": "数据不可用", "avg_pe": None}

    pe_values = [v["pe_ttm"] for v in industries.values() if v.get("pe_ttm")]
    avg_pe = round(sum(pe_values) / len(pe_values), 1) if pe_values else None

    if avg_pe is None:
        return {"icon": "❓", "label": "数据不可用", "avg_pe": None}

    if avg_pe < 15:
        icon, label = "🥶", "极寒（严重低估）"
    elif avg_pe < 20:
        icon, label = "❄️", "偏冷（低估）"
    elif avg_pe < 30:
        icon, label = "🌱", "温和（正常偏低）"
    elif avg_pe < 40:
        icon, label = "☀️", "适中（正常）"
    elif avg_pe < 50:
        icon, label = "🔥", "偏热（偏高）"
    else:
        icon, label = "🔴", "过热（高估）"

    # 最低和最高行业
    sorted_pe = sorted(industries.items(), key=lambda x: x[1].get("pe_ttm", 999) or 999)
    cheap = [(v["name"], v["pe_ttm"]) for _, v in sorted_pe[:3]]
    hot = [(v["name"], v["pe_ttm"]) for _, v in sorted_pe[-3:]]

    return {
        "icon": icon,
        "label": label,
        "avg_pe": avg_pe,
        "industry_count": len(industries),
        "update_date": meta.get("generated_at", "")[:10],
        "cheapest": cheap,
        "hottest": hot,
    }


# ============================================================================
# 投资建议生成器
# ============================================================================

def generate_etf_advice(etf: dict) -> str:
    """为单个ETF生成一句话投资建议"""
    pe_pct = to_float(etf.get("pe_percentile"), 999)
    pb_pct = to_float(etf.get("pb_percentile"), 999)
    amt = to_float(etf.get("avg_amount_20d"), 0) or 0
    score = to_float(etf.get("score"), 0) or 0
    source = etf.get("pe_pb_source", "")
    change_pct = to_float(etf.get("change_pct"), 0) or 0
    pool = etf.get("pool", "")
    
    # === 新增：数据质量判断 ===
    percentile_real = etf.get("percentile_real_flag", False)
    data_quality = etf.get("data_quality_flag", "unavailable")
    is_legulegu = "乐咕" in source or "legu" in source.lower() or percentile_real
    
    if percentile_real and is_legulegu:
        quality_icon = "✅"
        quality_note = "（真实历史分位-乐咕）"
        quality_tag = "[真实-乐咕]"  # 紧凑标注
    elif percentile_real:
        quality_icon = "✅"
        quality_note = "（真实历史分位）"
        quality_tag = "[真实]"
    elif "估算" in source or data_quality == "partial":
        quality_icon = "⚠️"
        quality_note = "（估算数据）"
        # 区分估算类型
        if "申万" in source:
            quality_tag = "[估算-申万]"
        elif "穿透" in source:
            quality_tag = "[估算-穿透]"
        else:
            quality_tag = "[估算]"
    else:
        quality_icon = "❓"
        quality_note = "（数据不可用）"
        quality_tag = "[未知]"

    # 判断低估程度
    if pe_pct <= 10 and pb_pct <= 15:
        level = "极度低估"
    elif pe_pct <= 20 and pb_pct <= 25:
        level = "显著低估"
    elif pe_pct <= 30:
        level = "低估"
    else:
        level = "偏低"

    # 流动性评估
    amt_yi = amt / 1e8
    if pool == "formal_pool":
        liq_note = ""
    elif amt_yi >= 0.3:
        liq_note = "（流动性尚可）"
    elif amt_yi >= 0.1:
        liq_note = "（流动性一般，小仓位操作）"
    else:
        liq_note = "（流动性偏低，谨慎操作）"

    # 数据质量（保留原有逻辑，但使用新的quality_note）
    if source and "估算" in source or "?" in source:
        data_note = quality_note  # 使用上面判断的quality_note
    else:
        data_note = quality_note  # 使用上面判断的quality_note

    # 涨跌方向
    if change_pct < -2:
        trend = "，近期回调中"
    elif change_pct > 2:
        trend = "，近期上涨"
    else:
        trend = ""

    # 组合建议（根据数据真实性区分）
    # 关键：估算数据不构成投资建议，只作参考
    if not percentile_real:
        # 估算数据：不给出买入建议
        if pe_pct <= 30 or pb_pct <= 30:
            action = f"{quality_tag} ⚠️ 数据估算，仅供参考（PE%={pe_pct}, PB%={pb_pct}）{trend}"
        else:
            action = f"{quality_tag} 数据估算，暂不操作"
    else:
        # 真实数据：可以给出投资建议
        if pe_pct <= 15 and pb_pct <= 15:
            action = f"{quality_tag} {level}，值得关注{liq_note}{trend}"
        elif pe_pct <= 20:
            action = f"{quality_tag} {level}，可小仓位试探{liq_note}{trend}"
        elif pb_pct <= 20:
            action = f"{quality_tag} PB{level}，可关注{liq_note}{trend}"
        elif pool == "watch_list":
            action = f"{quality_tag} {level}，持续观察{liq_note}{trend}"
        else:
            action = f"{quality_tag} {level}，暂不操作"

    return action


def generate_overall_advice(formal_count: int, watch_count: int, market_temp: dict) -> str:
    """生成整体操作建议"""
    temp = market_temp.get("icon", "")

    if formal_count > 0:
        lines = [
            f"✅ 今日有{formal_count}只ETF满足全部PPT标准，可重点关注。",
            "   建议分批建仓，单只仓位不超过总资金的20%。",
        ]
    else:
        if watch_count > 0:
            lines = [
                f"⚠️ 今日正式低估池为空，市场暂无满足全部条件的标的。",
                f"   关注池有{watch_count}只ETF满足低估条件但流动性不足。",
                "   可小仓位试探关注池中流动性较好的标的（如日均≥500万），",
                "   或耐心等待市场回调后出现正式低估机会。",
            ]
        else:
            lines = [
                "🔴 今日无低估ETF信号，市场整体估值偏高。",
                "   建议保持空仓或低仓位观望，等待更好时机。",
            ]

    # 市场温度补充
    avg_pe = market_temp.get("avg_pe")
    if avg_pe:
        if avg_pe >= 40:
            lines.append("   📌 市场偏热，追高风险较大，以防御为主。")
        elif avg_pe >= 30:
            lines.append("   📌 市场适中，精选低估行业ETF，控制仓位。")
        else:
            lines.append("   📌 市场偏低估，可适度增加ETF配置比例。")

    return "\n".join(lines)


# ============================================================================
# 日报生成器
# ============================================================================

class DailyReportGenerator:
    def __init__(self):
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.today_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate(self) -> dict:
        """生成日报"""
        # 1. 加载数据
        screener = load_json(LATEST_JSON, {})
        change = load_json(CHANGE_JSON, {})
        market_temp = get_market_temperature()

        formal = screener.get("formal_pool", [])
        watch = screener.get("watch_list", [])
        stats = screener.get("stats", {})

        # 2. 生成变化提醒
        changes = self._build_changes(change)

        # 3. 生成ETF建议
        all_candidates = []
        for e in formal:
            e["pool"] = "formal_pool"
            e["advice"] = generate_etf_advice(e)
            all_candidates.append(e)
        for e in watch:
            e["pool"] = "watch_list"
            e["advice"] = generate_etf_advice(e)
            all_candidates.append(e)

        # 4. 生成整体建议
        overall = generate_overall_advice(len(formal), len(watch), market_temp)

        # 5. 生成文本
        wechat_text = self._build_wechat(formal, watch, changes, market_temp, overall, all_candidates)
        md_text = self._build_markdown(formal, watch, changes, market_temp, overall, all_candidates, screener)

        # 6. 保存
        with open(DAILY_TXT, "w", encoding="utf-8") as f:
            f.write(wechat_text)
        logger.info(f"✅ 微信日报: {DAILY_TXT}")

        with open(DAILY_MD, "w", encoding="utf-8") as f:
            f.write(md_text)
        logger.info(f"✅ Markdown日报: {DAILY_MD}")

        return {
            "wechat": wechat_text,
            "markdown": md_text,
            "meta": {
                "generate_time": self.today_full,
                "formal_count": len(formal),
                "watch_count": len(watch),
                "market_temp": f"{market_temp.get('icon', '')} {market_temp.get('label', '')}",
            },
        }

    def _build_changes(self, change: dict) -> list:
        """构建变化提醒列表"""
        if not change or change.get("meta", {}).get("is_first_run"):
            return [{"type": "info", "text": "首次运行，无昨日数据对比"}]

        result = []
        summary = change.get("summary", {})

        # 新入
        for e in change.get("new_entries", [])[:5]:
            result.append({
                "type": "new",
                "code": e.get("code", ""),
                "name": e.get("name", ""),
                "text": f"+ {e.get('code', '')} {e.get('name', '')} 新入低估池",
            })

        # 退出
        for e in change.get("exits", [])[:5]:
            result.append({
                "type": "exit",
                "code": e.get("code", ""),
                "name": e.get("name", ""),
                "text": f"- {e.get('code', '')} {e.get('name', '')} 退出低估池",
            })

        if not result:
            if summary.get("today_count", 0) > 0:
                result.append({"type": "stable", "text": "低估池标的无变化，维持昨日判断"})
            else:
                result.append({"type": "empty", "text": "今日无变化"})

        return result

    def _build_wechat(self, formal, watch, changes, market_temp, overall, candidates) -> str:
        """生成微信纯文本日报（精简版：只推送3-5只最值得关注的ETF）"""
        lines = []

        # 标题
        lines.append("【ETF低估智能体 | 每日播报】")
        lines.append(f"📅 {self.today}")
        lines.append("")

        # 市场温度
        temp_icon = market_temp.get("icon", "❓")
        temp_label = market_temp.get("label", "未知")
        temp_pe = market_temp.get("avg_pe", "?")
        lines.append(f"📊 市场温度：{temp_icon} {temp_label}")
        if temp_pe:
            lines.append(f"   申万行业PE均值：{temp_pe}")
        lines.append("")

        # ========== 核心逻辑：优先真实数据 ==========
        
        # 排序规则：真实数据优先 > 估值吸引力 > 流动性好
        def sort_key(e):
            pe_pct = to_float(e.get("pe_percentile"), 999)
            pb_pct = to_float(e.get("pb_percentile"), 999)
            amt = to_float(e.get("avg_amount_20d"), 0) or 0
            real_flag = e.get("percentile_real_flag", False)
            
            # 优先级：真实数据(0) > 估算数据(1)，sorted()升序，真实数据排前面
            real_score = 0 if real_flag else 1
            # 估值吸引力：PE% + PB% 越低越好
            value_score = pe_pct + pb_pct
            # 流动性：日均成交额（亿元），越高越好（取负数让sorted()降序）
            liquidity_score = -amt / 1e8
            
            return (real_score, value_score, liquidity_score)
        
        sorted_formal = sorted(formal, key=sort_key)
        
        # 分离真实数据和估算数据
        real_picks = [e for e in sorted_formal if e.get('percentile_real_flag', False)]
        estimate_picks = [e for e in sorted_formal if not e.get('percentile_real_flag', False)]
        
        # 选取策略：优先真实数据，不足5只时用估算数据补充
        top_picks = real_picks[:5]  # 先取真实数据
        if len(top_picks) < 5:
            top_picks += estimate_picks[:5 - len(top_picks)]  # 用估算数据补充到5只
        
        # 选取TOP 5（如果正式池有）
        if sorted_formal:
            top_picks = sorted_formal[:5]
            lines.append(f"🎯 今日重点关注（TOP {len(top_picks)}）")
            lines.append(f"   （优先真实历史分位数据，兼顾估值吸引力+流动性）")
            lines.append("")
            
            for i, e in enumerate(top_picks, 1):
                code = e.get('code', '')
                name = e.get('name', '')
                pe_pct = to_float(e.get('pe_percentile'), 0) or 0
                pb_pct = to_float(e.get('pb_percentile'), 0) or 0
                peg = e.get('peg')
                amt = to_float(e.get('avg_amount_20d'), 0) or 0
                amt_yi = amt / 1e8
                
                # 数据质量标识
                percentile_real = e.get("percentile_real_flag", False)
                source = e.get("pe_pb_source", "")
                
                if percentile_real and ("乐咕" in source or "legu" in source.lower()):
                    quality_tag = "✅[真实-乐咕]"
                elif percentile_real:
                    quality_tag = "✅[真实]"
                elif "估算" in source:
                    quality_tag = "⚠️[估算]"
                else:
                    quality_tag = "❓[未知]"
                
                # 投资建议
                advice = generate_etf_advice(e)
                
                lines.append(f"{i}. {quality_tag} {code} {name}")
                lines.append(f"   📊 PE{pe_pct:.0f}% PB{pb_pct:.0f}%" + (f" PEG{peg:.2f}" if peg else "") + f" | 💰日均{amt_yi:.1f}亿")
                lines.append(f"   💡 {advice}")
                lines.append("")
        else:
            # 正式池为空，从关注池选TOP 3
            sorted_watch = sorted(watch, key=sort_key)
            top_picks = sorted_watch[:3]
            
            lines.append(f"⚠️ 今日正式低估池为空，以下从关注池精选TOP {len(top_picks)}")
            lines.append("")
            
            for i, e in enumerate(top_picks, 1):
                code = e.get('code', '')
                name = e.get('name', '')
                pe_pct = to_float(e.get('pe_percentile'), 0) or 0
                pb_pct = to_float(e.get('pb_percentile'), 0) or 0
                amt = to_float(e.get('avg_amount_20d'), 0) or 0
                amt_yi = amt / 1e8
                
                quality_tag = "⚠️[估算]" if "估算" in e.get("pe_pb_source", "") else "✅[真实]"
                advice = generate_etf_advice(e)
                
                lines.append(f"{i}. {quality_tag} {code} {name}")
                lines.append(f"   📊 PE{pe_pct:.0f}% PB{pb_pct:.0f}% | 💰日均{amt_yi:.1f}亿")
                lines.append(f"   💡 {advice}")
                lines.append("")
        
        # 2. 市场概况（简要）
        formal_count = len(formal)
        watch_count = len(watch)
        lines.append("---")
        lines.append(f"📈 市场概况：正式池{formal_count}只 | 关注池{watch_count}只")
        lines.append("")

        # 3. 变化提醒（只显示最重要的3条）
        if changes:
            lines.append("🔄 重要变化：")
            for c in changes[:3]:
                lines.append(f"   {c['text']}")
            lines.append("")

        # 4. 操作建议（精简）
        lines.append("💡 操作建议：")
        if formal_count > 0:
            lines.append(f"   今日有{formal_count}只ETF满足全部标准，可重点关注上方TOP {len(top_picks)}推荐")
        else:
            lines.append("   正式池为空，建议观望或小仓位试探关注池标的")
        lines.append("   建议分批建仓，单只仓位≤20%")
        lines.append("")

        # 5. 风险提示（精简）
        lines.append("⚠️ 风险提示：")
        lines.append("   • 以上建议基于量化数据，不构成投资建议")
        lines.append("   • 投资有风险，需自行判断并控制仓位")
        lines.append("   • 数据来源：AkShare + 乐咕乐股 | 仅供参考")

        return "\n".join(lines)

    def _build_markdown(self, formal, watch, changes, market_temp, overall, candidates, screener) -> str:
        """生成详细Markdown版日报"""
        lines = [
            "# ETF低估智能体 · 每日日报",
            "",
            f"> 生成时间：{self.today_full} | 数据来源：AkShare",
            "",
        ]

        # 市场温度
        temp_icon = market_temp.get("icon", "❓")
        temp_label = market_temp.get("label", "未知")
        temp_pe = market_temp.get("avg_pe", "?")
        lines.extend([
            "## 📊 市场温度",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 市场温度 | {temp_icon} {temp_label} |",
            f"| 申万行业PE均值 | {temp_pe} |",
            f"| 申万行业数 | {market_temp.get('industry_count', '?')} |",
            f"| 数据更新 | {market_temp.get('update_date', '?')} |",
            "",
        ])

        # 最低/最高行业
        cheapest = market_temp.get("cheapest", [])
        hottest = market_temp.get("hottest", [])
        if cheapest or hottest:
            lines.append("**估值最低行业**：")
            for name, pe in cheapest:
                lines.append(f"- {name}：PE={pe:.1f}")
            lines.append("")
            lines.append("**估值最高行业**：")
            for name, pe in reversed(hottest):
                lines.append(f"- {name}：PE={pe:.1f}")
            lines.append("")

        # 正式低估池
        formal_count = len(formal)
        watch_count = len(watch)
        stats = screener.get("stats", {})

        lines.extend([
            "## 🎯 筛选结果",
            "",
            f"| 池别 | 数量 | 说明 |",
            f"|------|------|------|",
            f"| 正式低估池 | **{formal_count}只** | PE/PB%≤30 + PEG<1 + 日均≥1亿 |",
            f"| 关注池 | **{watch_count}只** | 低估+流动性≥300万 |",
            f"| 观察池 | {stats.get('observation_pool', '?')}只 | 有数据但不低估 |",
            f"| 数据不可用 | {stats.get('unavailable', '?')}只 | 无估值数据 |",
            "",
        ])

        if formal_count > 0:
            lines.extend([
                "### 🏆 正式低估池",
                "",
                "| 代码 | 名称 | 数据质量 | PE分位 | PB分位 | PEG | 20日均(亿) | 投资建议 |",
                "|------|------|----------|--------|--------|-----|-----------|----------|",
            ])
            for e in formal[:20]:
                pe = to_float(e.get("pe_percentile"), 0) or 0
                pb = to_float(e.get("pb_percentile"), 0) or 0
                peg = e.get("peg")
                amt = to_float(e.get("avg_amount_20d"), 0) or 0
                advice = e.get("advice", "")
                peg_str = f"{peg:.2f}" if peg else "-"
                
                # 新增：数据质量图标
                percentile_real = e.get("percentile_real_flag", False)
                data_quality = e.get("data_quality_flag", "unavailable")
                source = e.get("pe_pb_source", "")
                
                if percentile_real:
                    quality_icon = "✅ 真实"
                elif "估算" in source or data_quality == "partial":
                    quality_icon = "⚠️ 估算"
                else:
                    quality_icon = "❓ 未知"
                
                lines.append(f"| {e['code']} | {e['name']} | {quality_icon} | {pe:.1f}% | {pb:.1f}% | {peg_str} | {amt/1e8:.2f} | {advice} |")
            lines.append("")
        else:
            lines.extend([
                "### 🏆 正式低估池",
                "",
                "> ❌ 当前市场无ETF同时满足全部PPT标准条件。",
                "> 市场整体估值偏高，低估ETF流动性不足。",
                "",
            ])

        # 关注池
        if watch_count > 0:
            lines.extend([
                "### 👀 关注池（低估值+流动性尚可）",
                "",
                "| 代码 | 名称 | 数据质量 | PE分位 | PB分位 | 20日均(亿) | 来源 | 投资建议 |",
                "|------|------|----------|--------|--------|-----------|------|----------|",
            ])
            for e in watch[:20]:
                pe = to_float(e.get("pe_percentile"), 0) or 0
                pb = to_float(e.get("pb_percentile"), 0) or 0
                amt = to_float(e.get("avg_amount_20d"), 0) or 0
                src = e.get("pe_pb_source", "")
                advice = e.get("advice", "")
                
                # 新增：数据质量图标
                percentile_real = e.get("percentile_real_flag", False)
                data_quality = e.get("data_quality_flag", "unavailable")
                
                if percentile_real:
                    quality_icon = "✅ 真实"
                elif "估算" in src or data_quality == "partial":
                    quality_icon = "⚠️ 估算"
                else:
                    quality_icon = "❓ 未知"
                
                lines.append(f"| {e['code']} | {e['name']} | {quality_icon} | {pe:.1f}% | {pb:.1f}% | {amt/1e8:.2f} | {src} | {advice} |")
            lines.append("")

        # 变化提醒
        if changes:
            lines.extend(["## 🔄 变化提醒", ""])
            for c in changes:
                icon = {"new": "🆕", "exit": "📤", "stable": "➡️", "info": "ℹ️", "empty": "📭"}.get(c["type"], "•")
                lines.append(f"- {icon} {c['text']}")
            lines.append("")

        # 操作建议
        lines.extend([
            "## 💡 操作建议",
            "",
        ])
        for line in overall.split("\n"):
            lines.append(f"> {line}")
        lines.append("")

        # 数据质量说明（新增）
        lines.extend([
            "## 📊 数据质量说明",
            "",
            "| 图标 | 含义 | 数据来源 | 可信度 |",
            "|------|------|----------|--------|",
            "| ✅ 真实 | 真实历史分位 | 乐咕乐股(第三方) 20年历史 | ⭐⭐⭐⭐ |",
            "| ⚠️ 估算 | 估算分位 | 申万行业加权/穿透估值 | ⭐⭐⭐ |",
            "| ❓ 未知 | 数据不可用 | 无可靠数据源 | ❌ |",
            "",
            "**数据来源详细说明**：",
            "",
            "### ✅ 真实历史分位（乐咕乐股）",
            "- **数据性质**：真实历史分位（基于20年完整历史序列计算）",
            "- **数据来源**：乐咕乐股 (legulegu.com)，通过AkShare接口获取",
            "- **覆盖指数**：沪深300、中证500、上证50、科创50等12个宽基指数",
            "- **数据年限**：11-21年（取决于指数成立时间）",
            "- **更新频率**：日频更新",
            "- **可信度**：⭐⭐⭐⭐ （虽非官方，但数据真实可靠）",
            "- **适用ETF**：宽基ETF（如沪深300ETF、中证500ETF等）",
            "",
            "### ⚠️ 估算分位（申万行业/穿透估值）",
            "- **数据性质**：估算值（非该ETF自身历史分位）",
            "- **计算方法**：",
            "  1. 申万行业加权：该ETF跟踪行业的Top20成分股PE/PB加权平均",
            "  2. 穿透估值：该ETF持仓成分股的PE/PB加权平均（需季报数据）",
            "- **覆盖ETF**：行业ETF、主题ETF、策略ETF等",
            "- **可信度**：⭐⭐⭐ （仅供参考，误差可能±20%）",
            "- **使用建议**：结合其他指标（如PB、趋势、基本面）综合判断",
            "",
            "### ❓ 数据不可用",
            "- **原因**：无可靠数据源或计算失败",
            "- **处理**：不纳入筛选，或仅作参考",
            "",
        ])

        # 风险提示
        lines.extend([
            "## ⚠️ 风险提示",
            "",
            "1. **数据说明**：申万行业PE/PB为估算值，不代表ETF真实历史分位",
            "2. **流动性风险**：关注池ETF日均成交额较低，大额交易可能冲击价格",
            "3. **投资建议仅供参考**：不构成投资建议，投资者需自行判断",
            "4. **市场风险**：A股市场波动较大，请注意控制仓位和止损",
            "",
            "---",
            f"*数据来源：AkShare金融数据库 | ETF智能体 v4.0 | {self.today} | 仅供参考，投资有风险*",
        ])

        return "\n".join(lines)


# ============================================================================
# 主函数
# ============================================================================

def main():
    logger.info("")
    logger.info("=" * 60)
    logger.info("📰 ETF微信日报生成器")
    logger.info("=" * 60)

    gen = DailyReportGenerator()
    try:
        result = gen.generate()
    except Exception as e:
        logger.error(f"日报生成失败: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 打印预览
    print("\n" + "=" * 60)
    print("📰 微信日报预览")
    print("=" * 60)
    print(result["wechat"])
    print("\n" + "=" * 60)

    logger.info("")
    logger.info("✅ 日报生成完成！")
    logger.info(f"   微信版: {DAILY_TXT}")
    logger.info(f"   MD版:   {DAILY_MD}")
    return result


if __name__ == "__main__":
    main()
