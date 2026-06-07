#!/usr/bin/env python3
"""
ETF日报 V10 — 全自动生成与推送
===============================
数据源：申万指数官方估值(index_percentiles_latest.json)
        + ETF实时行情(etf_spot_latest.json)
规则：  用户定义的七条日报规则，纯确定性逻辑，零AI依赖
"""
import json, os, sys, subprocess
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).parent.parent.resolve()
PERCENTILE_FILE = BASE / "data" / "index_percentiles_latest.json"
SPOT_FILE = BASE / "data" / "etf_spot_latest.json"
SEND_SCRIPT = BASE / "scripts" / "send_wechat_message.py"
OUTPUT_FILE = BASE / "output" / "daily_report_v9.txt"

# === ETF → SW行业 硬映射（表驱动，稳定可靠）===
# code: (name_short, sw_code, category: cycle|growth|bias_cycle, turnover_min_yi)
ETF_REGISTRY = {
    "sh512000": ("券商ETF",   "801790", "cycle"),
    "sh512880": ("券商ETF",   "801790", "cycle"),
    "sh512690": ("酒ETF",     "801120", "growth"),
    "sh512170": ("医疗ETF",   "801150", "growth"),
    "sz159996": ("家电ETF",   "801110", "bias_cycle"),
    "sh512400": ("有色ETF",   "801050", "cycle"),
    "sh515220": ("煤炭ETF",   "801020", "cycle"),
    "sz159870": ("化工ETF",   "801030", "cycle"),
    "sh515210": ("钢铁ETF",   "801040", "cycle"),
    "sz159997": ("电子ETF",   "801080", "growth"),
    "sh512200": ("地产ETF",   "801180", "cycle"),
    "sh512800": ("银行ETF",   "801710", "cycle"),
    "sz159869": ("游戏ETF",   "801760", "growth"),
    "sh512660": ("军工ETF",   "801790", "cycle"),
    "sh515030": ("新能车ETF", "801740", "growth"),
    "sz159949": ("创业板50",  "000300", "growth"),
    "sh510050": ("上证50ETF", "000016", "cycle"),
    "sz159915": ("创业板ETF", "000300", "growth"),
    "sh512500": ("中证500ETF","000905", "growth"),
    "sh512100": ("中证1000ETF","000852", "growth"),
}

# 申万代码→行业中文名
SW_NAMES = {
    "801010": "农林牧渔", "801020": "采掘(煤炭)", "801030": "化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服装",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商业贸易",
    "801210": "休闲服务", "801230": "建筑材料", "801710": "银行",
    "801720": "非银金融", "801730": "建筑装饰", "801740": "电气设备",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "机械设备", "801790": "国防军工",
    "000300": "沪深300", "000016": "上证50", "000905": "中证500",
    "000852": "中证1000",
}

MIN_TURNOVER_YI = 0.5  # 最低日均成交额（亿）


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def calc_peg(pe, pb):
    """PEG = PE / g, g = ROE × 70% = (PB/PE) × 0.7, 所以 PEG = PE²/(PB×70)"""
    if pb and pb > 0:
        return round(pe * pe / (pb * 70), 2)
    return None


def get_spot_amounts(spot_data: list) -> dict:
    """从实时行情提取每只ETF的日成交额（亿）"""
    amounts = {}
    for etf in spot_data:
        code = etf.get("code", "")
        amt = etf.get("amount", 0) or 0
        amounts[code] = amt / 1e8  # 转亿
    return amounts


def build_candidates(percentiles: dict, spot_amounts: dict) -> list:
    """从SW行业数据+实时行情构建候选池"""
    sw_ind = percentiles.get("sw_industries", {})
    candidates = []

    for code, (name_short, sw_code, etype) in ETF_REGISTRY.items():
        # 获取SW行业估值数据
        sw = sw_ind.get(sw_code)
        if not sw:
            continue
        pe = sw.get("pe")
        pep = sw.get("pe_percentile")
        pb = sw.get("pb")
        pbp = sw.get("pb_percentile")
        if pe is None or pep is None or pb is None:
            continue

        # 获取成交额
        daily_amt = spot_amounts.get(code, 0)
        if daily_amt < MIN_TURNOVER_YI:
            continue  # 流动性不足

        # 计算PEG（仅成长类）
        peg = None
        if etype == "growth":
            peg = calc_peg(pe, pb)

        # 星级（规则3）
        if pep < 25:
            stars_n = 5
            stars = "★★★★★"
        elif pep <= 40:
            stars_n = 4
            stars = "★★★★"
        else:
            stars_n = 3
            stars = "★★★"

        # 指标列（规则1&2）
        if etype in ("cycle", "bias_cycle"):
            indicator = f"PB{pb}"
        elif peg and peg > 10:
            # PEG极端值，用PB替代
            indicator = f"PB{pb}"
            etype = "bias_cycle"  # 降级处理
        else:
            indicator = f"PEG{peg}" if peg else f"PB{pb}"

        # 建议仓位（规则4）
        pos_range = ""
        if stars_n == 5:
            pos_range = "6-8%"
            actual_pos = 7
        elif stars_n == 4 and pep < 33:
            pos_range = "5-7%"
            actual_pos = 6
        else:
            pos_range = "3-5%"
            actual_pos = 4

        # 备注（规则5）
        prefix = "✅"
        if stars_n == 5:
            if "券商" in name_short:
                note = f"PE历史低位，PB低估，建议分批建仓（{pos_range}）"
            elif "酒" in name_short:
                note = f"PE历史低位，PEG合理，逢回调布局（{pos_range}）"
            else:
                note = f"PE历史低位，建议分批建仓（{pos_range}）"
        elif stars_n == 4:
            # 成长ETF PEG提示
            peg_warn = ""
            if etype == "growth" and peg and peg > 3:
                peg_warn = "，PEG偏高"
            elif etype == "growth" and peg and peg > 2:
                peg_warn = "，PEG合理偏高"
            
            if "医疗" in name_short:
                note = f"PE中低位{peg_warn}，需耐心持有（{pos_range}）"
            elif "家电" in name_short:
                note = f"PE中低位，PB适中，逢跌小仓（{pos_range}）"
            else:
                note = f"PE接近中位，PB偏高{peg_warn}，防御配置（{pos_range}）"
        else:
            if pep < 50:
                note = f"PE中位，PB偏高，防御配置（{pos_range}）"
            else:
                note = f"PE偏高，暂不建议重仓（{pos_range}）"

        # 行业名
        industry = SW_NAMES.get(sw_code, sw_code)

        candidates.append({
            "sw_code": sw_code,
            "industry": industry,
            "code": code,
            "name": name_short,
            "pe": pe,
            "pep": pep,
            "pb": pb,
            "pbp": pbp,
            "peg": peg,
            "indicator": indicator,
            "daily_amt": daily_amt,
            "stars_n": stars_n,
            "stars": stars,
            "pos_range": pos_range,
            "actual_pos": actual_pos,
            "note": note,
            "prefix": prefix,
            "etype": etype,
        })

    return candidates


def select_top5(candidates: list) -> list:
    """选择TOP5：按星级降序→分位升序，行业不重复"""
    candidates.sort(key=lambda x: (-x["stars_n"], x["pep"]))
    selected = []
    used_industries = set()
    used_codes = set()

    for c in candidates:
        if c["sw_code"] in used_industries:
            continue
        if c["code"] in used_codes:
            continue
        selected.append(c)
        used_industries.add(c["sw_code"])
        used_codes.add(c["code"])
        if len(selected) >= 5:
            break

    return selected


def generate_report(candidates: list) -> str:
    """生成日报文本"""
    now = datetime.now()
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    max_amt = max(c["daily_amt"] for c in candidates) if candidates else 1
    total_pos = sum(c["actual_pos"] for c in candidates)

    lines = [
        f"🎯 ETF低估精选 | {now.strftime('%m/%d')}",
        "",
        f"扫描全市场 ETF，TOP5 低估标的：",
    ]

    for i, c in enumerate(candidates):
        lines.append("")
        lines.append(f"{medals[i]} {c['name']} {c['code']}")
        lines.append(f"   PE{c['pe']} | 分位{round(c['pep'],1)}% | {c['indicator']}")
        lines.append(f"   日均{c['daily_amt']:.2f}亿 | {c['stars']}")
        lines.append(f"   {c['prefix']} {c['note']}")

    lines.append("")
    lines.append("─" * 22)
    lines.append("⚠️ 以上基于历史数据，不构成投资建议")
    lines.append(f"📍 {now.strftime('%m/%d %H:%M')} 自动生成")
    lines.append("数据源：申万指数官方估值 + 十年历史百分位表")

    return "\n".join(lines)


def push_to_wechat(text: str) -> bool:
    """推送到微信"""
    if not SEND_SCRIPT.exists():
        print(f"❌ 推送脚本不存在: {SEND_SCRIPT}", file=sys.stderr)
        return False

    try:
        result = subprocess.run(
            ["python3", str(SEND_SCRIPT), text],
            capture_output=True, text=True, timeout=30
        )
        if "HTTP 200" in result.stdout:
            print("✅ 微信推送成功")
            return True
        else:
            print(f"⚠️ 推送返回: {result.stdout.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 推送超时")
        return False
    except Exception as e:
        print(f"❌ 推送失败: {e}")
        return False


def main():
    # 1. 检查数据文件
    if not PERCENTILE_FILE.exists():
        print(f"❌ 分位数据不存在: {PERCENTILE_FILE}", file=sys.stderr)
        sys.exit(1)
    if not SPOT_FILE.exists():
        print(f"❌ 行情数据不存在: {SPOT_FILE}", file=sys.stderr)
        sys.exit(1)

    # 2. 加载数据
    percentiles = load_json(PERCENTILE_FILE)
    spot_raw = load_json(SPOT_FILE)

    # 检查数据新鲜度
    gen_time = percentiles.get("meta", {}).get("generated_at", "")
    spot_time = spot_raw.get("meta", {}).get("collect_time", "")
    print(f"📊 分位数据: {gen_time}")
    print(f"📈 行情数据: {spot_time}")

    spot_data = spot_raw.get("data", [])
    if not spot_data:
        print("❌ 行情数据为空", file=sys.stderr)
        sys.exit(1)

    # 3. 提取成交额 & 今日日期
    spot_amounts = get_spot_amounts(spot_data)
    print(f"📈 加载 {len(spot_amounts)} 只ETF成交额")

    # 4. 构建候选池
    candidates = build_candidates(percentiles, spot_amounts)
    print(f"🔍 候选池: {len(candidates)} 只满足流动性要求")

    if not candidates:
        print("❌ 无合格候选ETF", file=sys.stderr)
        sys.exit(1)

    # 5. 选择TOP5
    top5 = select_top5(candidates)
    if len(top5) < 5:
        print(f"⚠️ 仅选出 {len(top5)} 只（行业覆盖不足），仍将推送", file=sys.stderr)

    # 6. 生成报告
    report = generate_report(top5)
    print("\n" + report)

    # 保存到文件
    with open(OUTPUT_FILE, "w") as f:
        f.write(report)
    print(f"\n📄 已保存: {OUTPUT_FILE}")

    # 仓位合计
    total_pos = sum(c["actual_pos"] for c in top5)
    pos_detail = " + ".join(f"{c['name']}{c['actual_pos']}%" for c in top5)
    print(f"💰 仓位: {pos_detail} = {total_pos}% {'✅' if total_pos <= 30 else '⚠️ 超30%上限!'}")

    # 7. 推送到微信
    success = push_to_wechat(report)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
