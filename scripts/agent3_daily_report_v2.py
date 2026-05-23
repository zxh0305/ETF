#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF日报生成器 V2 - 优先真实数据
====================================
改进：
1. 只推荐PE%<30%的宽基指数ETF（真实历史分位数据）
2. 如果真实低估ETF不足5只，补充PE%在30-50%的（观望）
3. 行业/主题ETF（估算数据）作为补充，明确标注"估算-仅供参考"
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

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    logger = logging.getLogger("daily_report_v2")
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

    return {
        "icon": icon,
        "label": label,
        "avg_pe": avg_pe,
    }


# ============================================================================
# 日报生成器
# ============================================================================

class DailyReportGeneratorV2:
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
        
        # 2. 从全市场数据中提取所有ETF（包括不在正式池的）
        all_etfs = []
        all_etfs.extend(screener.get("formal_pool", []))
        all_etfs.extend(screener.get("watch_list", []))
        all_etfs.extend(screener.get("observation_pool", []))
        
        # 3. 筛选宽基指数ETF（有真实历史分位数据）
        broad_index_etfs = [e for e in all_etfs if e.get("percentile_real_flag", False)]
        
        # 去重（可能重复）
        seen = set()
        unique_broad = []
        for e in broad_index_etfs:
            code = e.get("code", "")
            if code not in seen:
                seen.add(code)
                unique_broad.append(e)
        broad_index_etfs = unique_broad
        
        # 4. 生成变化提醒
        changes = self._build_changes(change)

        # 5. 生成文本
        wechat_text = self._build_wechat(formal, watch, broad_index_etfs, changes, market_temp)
        
        # 6. 保存
        with open(DAILY_TXT, "w", encoding="utf-8") as f:
            f.write(wechat_text)
        logger.info(f"✅ 微信日报: {DAILY_TXT}")

        # 7. 打印预览
        print("\n" + "=" * 60)
        print("📰 微信日报预览")
        print("=" * 60)
        print(wechat_text)
        print("\n" + "=" * 60)

        logger.info("✅ 日报生成完成！")
        logger.info(f"   微信版: {DAILY_TXT}")

        return {
            "wechat": wechat_text,
            "meta": {
                "generate_time": self.today_full,
                "formal_count": len(formal),
                "watch_count": len(watch),
                "broad_index_count": len(broad_index_etfs),
                "market_temp": f"{market_temp.get('icon', '')} {market_temp.get('label', '')}",
            },
        }

    def _build_changes(self, change: dict) -> list:
        """构建变化提醒列表"""
        if not change or change.get("meta", {}).get("is_first_run"):
            return [{"type": "info", "text": "首次运行，无昨日数据对比"}]

        result = []
        for e in change.get("new_entries", [])[:3]:
            result.append({"type": "new", "text": f"+ {e.get('code', '')} {e.get('name', '')} 新入低估池"})
        for e in change.get("exits", [])[:3]:
            result.append({"type": "exit", "text": f"- {e.get('code', '')} {e.get('name', '')} 退出低估池"})

        if not result:
            result.append({"type": "stable", "text": "低估池标的无变化"})

        return result

    def _build_wechat(self, formal, watch, broad_index_etfs, changes, market_temp) -> str:
        """生成微信纯文本日报（优先真实数据）"""
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
        if temp_pe != "?":
            lines.append(f"   申万行业PE均值：{temp_pe}")
        lines.append("")

        # ========= 核心：优先推荐真实数据ETF =========
        
        # 1. 宽基指数ETF（有真实历史分位数据）- 只推荐PE%<30%的
        if broad_index_etfs:
            # 筛选PE% < 30%的（真正低估）
            undervalued_broad = [e for e in broad_index_etfs if to_float(e.get("pe_percentile"), 999) < 30]
            
            if undervalued_broad:
                # 按PE%排序（低到高）
                sorted_broad = sorted(undervalued_broad, key=lambda x: to_float(x.get("pe_percentile"), 999))
                top_broad = sorted_broad[:5]
                
                lines.append(f"✅ 宽基指数ETF（真实历史分位-低估）- TOP {len(top_broad)}")
                lines.append("   （以下均为乐咕乐股20年真实历史分位，数据可靠）")
                lines.append("")
                
                for i, e in enumerate(top_broad, 1):
                    code = e.get('code', '')
                    name = e.get('name', '')
                    pe_pct = to_float(e.get('pe_percentile'), 0) or 0
                    pb_pct = to_float(e.get('pb_percentile'), 0) or 0
                    amt = to_float(e.get('avg_amount_20d'), 0) or 0
                    amt_yi = amt / 1e8
                    
                    # 投资建议
                    if pe_pct <= 15 and pb_pct <= 15:
                        advice = f"极度低估，值得关注 | 日均{amt_yi:.1f}亿"
                    elif pe_pct <= 20:
                        advice = f"显著低估，可小仓位试探 | 日均{amt_yi:.1f}亿"
                    else:
                        advice = f"低估，持续观察 | 日均{amt_yi:.1f}亿"
                    
                    lines.append(f"{i}. ✅[真实] {code} {name}")
                    lines.append(f"   📊 PE{pe_pct:.0f}% PB{pb_pct:.0f}% | 💰日均{amt_yi:.1f}亿")
                    lines.append(f"   💡 {advice}")
                    lines.append("")
            
            # 如果真实低估ETF不足5只，补充显示PE%在30-50%的（观望）
            if len(undervalued_broad) < 5:
                watch_broad = [e for e in broad_index_etfs if 30 <= to_float(e.get("pe_percentile"), 999) < 50]
                if watch_broad:
                    sorted_watch = sorted(watch_broad, key=lambda x: to_float(x.get("pe_percentile"), 999))
                    lines.append(f"👀 宽基指数ETF（真实数据-观望）- TOP 3")
                    lines.append("   （以下PE%在30-50%，可持续观察）")
                    lines.append("")
                    
                    for i, e in enumerate(sorted_watch[:3], 1):
                        code = e.get('code', '')
                        name = e.get('name', '')
                        pe_pct = to_float(e.get('pe_percentile'), 0) or 0
                        pb_pct = to_float(e.get('pb_percentile'), 0) or 0
                        amt = to_float(e.get('avg_amount_20d'), 0) or 0
                        amt_yi = amt / 1e8
                        
                        advice = f"估值适中，持续观察 | 日均{amt_yi:.1f}亿"
                        
                        lines.append(f"{i}. 👀[真实] {code} {name}")
                        lines.append(f"   📊 PE{pe_pct:.0f}% PB{pb_pct:.0f}% | 💰日均{amt_yi:.1f}亿")
                        lines.append(f"   💡 {advice}")
                        lines.append("")
            
            # 如果没有低估的宽基ETF
            if not undervalued_broad:
                lines.append("⚠️ 宽基指数ETF（真实数据）- 无低估标的")
                lines.append("   （当前宽基指数估值偏高，无PE%<30%的标的）")
                lines.append("")
        
        # 2. 行业/主题ETF（正式池，估算数据）- 作为补充
        if formal:
            # 排序：PE%低 > 流动性好
            def sort_key(e):
                pe_pct = to_float(e.get("pe_percentile"), 999)
                amt = to_float(e.get("avg_amount_20d"), 0) or 0
                return (pe_pct, -amt)
            
            sorted_formal = sorted(formal, key=sort_key)
            top_formal = sorted_formal[:3]
            
            lines.append(f"⚠️ 行业/主题ETF（估算数据）- TOP {len(top_formal)}")
            lines.append("   ⚠️ 数据为估算值（申万行业/穿透估值），非真实历史分位，仅供参考")
            lines.append("")
            
            for i, e in enumerate(top_formal, 1):
                code = e.get('code', '')
                name = e.get('name', '')
                pe_pct = to_float(e.get('pe_percentile'), 0) or 0
                pb_pct = to_float(e.get('pb_percentile'), 0) or 0
                amt = to_float(e.get('avg_amount_20d'), 0) or 0
                amt_yi = amt / 1e8
                
                advice = f"估算数据，仅供参考（PE%={pe_pct}, PB%={pb_pct}）"
                
                lines.append(f"{i}. ⚠️[估算] {code} {name}")
                lines.append(f"   📊 PE{pe_pct:.0f}% PB{pb_pct:.0f}% | 💰日均{amt_yi:.1f}亿")
                lines.append(f"   💡 {advice}")
                lines.append("")
        
        # 3. 市场概况
        lines.append("---")
        lines.append(f"📈 市场概况：正式池{len(formal)}只 | 关注池{len(watch)}只 | 宽基指数{len(broad_index_etfs)}只")
        lines.append("")

        # 4. 变化提醒
        if changes:
            lines.append("🔄 重要变化：")
            for c in changes[:3]:
                lines.append(f"   {c['text']}")
            lines.append("")

        # 5. 操作建议
        lines.append("💡 操作建议：")
        if broad_index_etfs:
            undervalued_count = sum(1 for e in broad_index_etfs if to_float(e.get("pe_percentile"), 999) < 30)
            if undervalued_count > 0:
                lines.append(f"   今日有{undervalued_count}只宽基指数ETF低估（真实数据），可重点关注")
            else:
                lines.append("   宽基指数ETF暂无低估标的，建议观望")
        if formal:
            lines.append(f"   行业/主题ETF有{len(formal)}只满足筛选条件（估算数据），仅供参考")
        lines.append("   建议分批建仓，单只仓位≤20%")
        lines.append("")

        # 6. 数据说明
        lines.append("📊 数据质量说明：")
        lines.append("   ✅[真实] 乐咕乐股20年真实历史分位（最可靠）")
        lines.append("   ⚠️[估算] 申万行业/穿透估值（仅供参考，误差±20%）")
        lines.append("")

        # 7. 风险提示
        lines.append("⚠️ 风险提示：")
        lines.append("   • 以上建议基于量化数据，不构成投资建议")
        lines.append("   • 投资有风险，需自行判断并控制仓位")
        lines.append("   • 数据来源：AkShare + 乐咕乐股 | 仅供参考")

        return "\n".join(lines)


# ============================================================================
# 主函数
# ============================================================================

def main():
    logger.info("")
    logger.info("=" * 60)
    logger.info("📰 ETF微信日报生成器 V2（优先真实数据）")
    logger.info("=" * 60)

    gen = DailyReportGeneratorV2()
    try:
        result = gen.generate()
    except Exception as e:
        logger.error(f"日报生成失败: {e}")
        traceback.print_exc()
        sys.exit(1)

    return result


if __name__ == "__main__":
    main()
