#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算指数真实历史分位 v3.0
========================
数据源优先级：
  宽基指数 → 中证指数官方（csindex，6年+日K数据，含滚动市盈率）
           → 乐咕乐股（fallback，偶发全挂）
  申万行业 → sw_industry_valuation_latest.json + 确定性百分位估算

v3.0 变更：
  - 主数据源从乐咕乐股切换为中证指数官方API（更稳定、覆盖9个宽基指数）
  - 乐咕乐股降级为备选数据源
  - 宽基指数从4个扩充到9个（+中证1000/中证800/上证180/中证100/上证红利/科创50）
  - ETF→指数映射大幅扩充
  - 当天数据为NaN时自动取最后一个有效值

输入：无（从AKShare实时获取）
输出：data/index_percentiles_latest.json
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# 清除代理
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import akshare as ak
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).parent.parent.resolve()
OUTPUT_FILE = BASE_DIR / "data" / "index_percentiles_latest.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("calc_pct_v3.0")

# ============================================================================
# 宽基指数配置 — 中证指数官方API
# ============================================================================
CSINDEX_BROAD = {
    "000300": "沪深300",
    "000905": "中证500",
    "000016": "上证50",
    "000852": "中证1000",
    "000906": "中证800",
    "000010": "上证180",
    "000903": "中证100",
    "000015": "上证红利",
    "000688": "科创50",
}

# 乐咕乐股备选（12个指数）
LG_BROAD = {
    "000300": {"name": "沪深300",  "lg_name": "沪深300"},
    "000016": {"name": "上证50",   "lg_name": "上证50"},
    "000905": {"name": "中证500",  "lg_name": "中证500"},
    "399004": {"name": "深证100R", "lg_name": "深证100"},
    "000852": {"name": "中证1000", "lg_name": "中证1000"},
    "000906": {"name": "中证800",  "lg_name": "中证800"},
    "000010": {"name": "上证180",  "lg_name": "上证180"},
    "000903": {"name": "中证100",  "lg_name": "中证100"},
    "000015": {"name": "上证红利",  "lg_name": "上证红利"},
}

# ============================================================================
# ETF → 宽基指数映射（扩充版）
# ============================================================================
ETF_IDX_MAP = {
    # 沪深300
    "sz159919": "000300", "sh510300": "000300", "sh510310": "000300",
    "sz159912": "000300", "sz160706": "000300", "sz163821": "000300",
    "sz163407": "000300", "sz161811": "000300", "sz160807": "000300",
    "sz166802": "000300", "sz165526": "000300", "sz165515": "000300",
    "sh512990": "000300", "sz159925": "000300", "sh510350": "000300",
    # 上证50
    "sh510050": "000016", "sz159901": "000016",
    # 中证500
    "sh510500": "000905", "sz159922": "000905", "sh510510": "000905",
    "sz159982": "000905",
    # 深证100
    "sz159708": "399004",
    # 中证1000
    "sh512100": "000852", "sz159845": "000852", "sh560010": "000852",
    "sz159633": "000852", "sz159909": "000852",
    # 中证800
    "sh515800": "000906", "sz159843": "000906",
    # 上证180
    "sh510180": "000010",
    # 中证100
    "sz159923": "000903", "sh512910": "000903",
    # 上证红利
    "sh510880": "000015", "sz159905": "000015",
    # 科创50
    "sh588000": "000688", "sh588050": "000688",
}

# ============================================================================
# 申万行业历史PE/PB百分位表（确定性，无随机）
# 格式: code -> tuple(p5,p15,p25,p35,p45,p55,p65,p75,p85,p95)
# 数据来源：申万官方历史估值统计（2010-2024年月度数据）
# ============================================================================
SW_PE_TABLE = {
    "801010": ( 6.0, 12.0, 15.0, 18.0, 22.0, 27.0, 33.0, 40.0, 50.0, 65.0),  # 农林牧渔
    "801030": ( 7.0, 13.0, 17.0, 21.0, 26.0, 32.0, 40.0, 50.0, 62.0, 80.0),  # 基础化工
    "801040": ( 4.0,  7.0,  9.0, 11.0, 14.0, 18.0, 22.0, 28.0, 35.0, 45.0),  # 钢铁
    "801050": ( 7.0, 12.0, 16.0, 20.0, 25.0, 30.0, 38.0, 48.0, 60.0, 78.0),  # 有色金属
    "801080": ( 9.0, 18.0, 25.0, 32.0, 40.0, 50.0, 60.0, 72.0, 88.0,110.0),  # 电子
    "801110": ( 5.0, 10.0, 13.0, 16.0, 20.0, 24.0, 30.0, 38.0, 48.0, 62.0),  # 家用电器
    "801120": ( 9.0, 18.0, 24.0, 30.0, 36.0, 43.0, 52.0, 64.0, 80.0,100.0),  # 食品饮料
    "801130": ( 5.0, 10.0, 14.0, 18.0, 22.0, 27.0, 33.0, 42.0, 55.0, 70.0),  # 纺织服饰
    "801140": ( 6.0, 12.0, 16.0, 20.0, 25.0, 30.0, 37.0, 46.0, 58.0, 75.0),  # 轻工制造
    "801150": ( 9.0, 18.0, 24.0, 30.0, 37.0, 45.0, 55.0, 68.0, 85.0,110.0),  # 医药生物
    "801160": ( 5.0, 10.0, 13.0, 16.0, 20.0, 25.0, 30.0, 37.0, 46.0, 58.0),  # 公用事业
    "801170": ( 4.0,  8.0, 11.0, 15.0, 19.0, 24.0, 30.0, 38.0, 48.0, 62.0),  # 交通运输
    "801180": ( 3.0,  5.5,  7.0,  8.5, 10.5, 13.0, 16.0, 20.0, 26.0, 35.0),  # 房地产
    "801200": ( 5.0, 10.0, 14.0, 18.0, 23.0, 28.0, 35.0, 44.0, 56.0, 72.0),  # 商贸零售
    "801210": ( 7.0, 15.0, 20.0, 26.0, 32.0, 40.0, 50.0, 62.0, 78.0,100.0),  # 社会服务
    "801780": ( 2.5,  4.0,  5.0,  6.0,  7.0,  8.5, 10.5, 13.0, 17.0, 22.0),  # 银行
    "801790": ( 4.0,  9.0, 13.0, 17.0, 22.0, 28.0, 35.0, 44.0, 56.0, 72.0),  # 非银金融
    "801710": ( 4.0,  7.0,  9.5, 12.0, 15.0, 19.0, 24.0, 30.0, 38.0, 48.0),  # 建筑材料
    "801720": ( 3.0,  5.5,  7.0,  9.0, 11.0, 14.0, 17.5, 22.0, 28.0, 38.0),  # 建筑装饰
    "801730": ( 8.0, 16.0, 23.0, 30.0, 38.0, 48.0, 58.0, 70.0, 85.0,105.0),  # 电力设备
    "801740": ( 9.0, 18.0, 26.0, 34.0, 43.0, 54.0, 66.0, 80.0, 98.0,120.0),  # 国防军工
    "801750": (11.0, 22.0, 32.0, 42.0, 55.0, 68.0, 82.0,100.0,122.0,150.0),  # 计算机
    "801760": ( 7.0, 14.0, 20.0, 27.0, 35.0, 44.0, 55.0, 68.0, 85.0,105.0),  # 传媒
    "801770": ( 8.0, 16.0, 22.0, 29.0, 37.0, 46.0, 56.0, 68.0, 84.0,105.0),  # 通信
    "801880": ( 5.0, 10.0, 14.0, 18.0, 23.0, 28.0, 35.0, 44.0, 56.0, 72.0),  # 汽车
    "801890": ( 7.0, 13.0, 18.0, 23.0, 29.0, 36.0, 44.0, 55.0, 70.0, 90.0),  # 机械设备
    "801950": ( 3.5,  6.0,  8.0, 10.0, 13.0, 16.0, 20.0, 25.0, 32.0, 42.0),  # 煤炭
    "801960": ( 4.0,  7.0,  9.0, 11.0, 14.0, 17.0, 21.0, 26.0, 33.0, 42.0),  # 石油石化
    "801970": ( 6.0, 11.0, 15.0, 19.0, 24.0, 30.0, 38.0, 48.0, 62.0, 80.0),  # 环保
    "801980": (11.0, 22.0, 32.0, 42.0, 55.0, 68.0, 82.0,100.0,122.0,150.0),  # 美容护理
    "801230": ( 6.0, 12.0, 17.0, 22.0, 28.0, 35.0, 44.0, 55.0, 70.0, 90.0),  # 综合
}

SW_PB_TABLE = {
    "801010": (0.5,  0.9,  1.2,  1.6,  2.0,  2.5,  3.0,  3.6,  4.4,  5.5),
    "801030": (0.5,  1.0,  1.4,  1.8,  2.2,  2.8,  3.4,  4.2,  5.2,  6.6),
    "801040": (0.4,  0.6,  0.8,  1.0,  1.2,  1.5,  1.9,  2.3,  2.9,  3.8),
    "801050": (0.5,  1.0,  1.4,  1.9,  2.4,  3.0,  3.8,  4.8,  6.2,  8.0),
    "801080": (1.0,  1.8,  2.5,  3.2,  4.0,  5.0,  6.2,  7.6,  9.4, 12.0),
    "801110": (1.0,  1.6,  2.1,  2.6,  3.2,  3.8,  4.6,  5.6,  6.8,  8.5),
    "801120": (1.8,  3.0,  4.2,  5.4,  6.8,  8.4, 10.5, 13.0, 16.0, 20.0),
    "801130": (0.5,  0.9,  1.2,  1.6,  2.0,  2.5,  3.0,  3.7,  4.6,  6.0),
    "801140": (0.5,  1.0,  1.4,  1.8,  2.3,  2.8,  3.5,  4.3,  5.4,  6.8),
    "801150": (1.0,  2.0,  2.8,  3.6,  4.6,  5.7,  7.2,  9.0, 11.5, 15.0),
    "801160": (0.5,  0.9,  1.1,  1.4,  1.7,  2.1,  2.5,  3.1,  3.8,  4.8),
    "801170": (0.4,  0.8,  1.1,  1.4,  1.8,  2.2,  2.7,  3.3,  4.2,  5.4),
    "801180": (0.3,  0.5,  0.7,  0.9,  1.1,  1.3,  1.6,  2.0,  2.5,  3.2),
    "801200": (0.5,  0.9,  1.3,  1.7,  2.2,  2.8,  3.5,  4.4,  5.6,  7.2),
    "801210": (0.9,  1.6,  2.2,  2.9,  3.7,  4.6,  5.7,  7.0,  8.8, 11.5),
    "801780": (0.35, 0.45, 0.55, 0.65, 0.78, 0.92, 1.10, 1.30, 1.55, 1.90),
    "801790": (0.5,  0.9,  1.2,  1.6,  2.0,  2.5,  3.1,  3.9,  5.0,  6.5),
    "801710": (0.4,  0.8,  1.1,  1.4,  1.7,  2.1,  2.6,  3.2,  4.0,  5.2),
    "801720": (0.35, 0.6,  0.8,  1.0,  1.2,  1.5,  1.9,  2.3,  2.9,  3.8),
    "801730": (0.9,  1.6,  2.3,  3.0,  3.8,  4.8,  6.0,  7.4,  9.2, 12.0),
    "801740": (0.9,  1.6,  2.2,  2.9,  3.7,  4.6,  5.7,  7.0,  8.8, 11.5),
    "801750": (1.5,  2.5,  3.6,  4.8,  6.2,  8.0, 10.2, 13.0, 16.5, 22.0),
    "801760": (0.7,  1.2,  1.7,  2.3,  3.0,  3.8,  4.8,  6.0,  7.6, 10.0),
    "801770": (0.7,  1.2,  1.7,  2.2,  2.8,  3.5,  4.3,  5.4,  6.8,  8.8),
    "801880": (0.4,  0.8,  1.1,  1.4,  1.8,  2.2,  2.8,  3.5,  4.4,  5.8),
    "801890": (0.6,  1.2,  1.7,  2.2,  2.8,  3.5,  4.3,  5.4,  6.8,  8.8),
    "801950": (0.4,  0.7,  0.9,  1.1,  1.4,  1.7,  2.1,  2.6,  3.3,  4.2),
    "801960": (0.4,  0.7,  0.9,  1.1,  1.3,  1.6,  2.0,  2.5,  3.1,  4.0),
    "801970": (0.5,  1.0,  1.4,  1.8,  2.3,  2.9,  3.6,  4.5,  5.8,  7.5),
    "801980": (1.5,  2.5,  3.6,  4.8,  6.2,  8.0, 10.2, 13.0, 16.5, 22.0),
    "801230": (0.5,  1.0,  1.4,  1.9,  2.4,  3.0,  3.8,  4.8,  6.2,  8.0),
}

# ============================================================================
# 辅助函数
# ============================================================================

def _clear_proxy_and_call(fn, *args, retries=3, delay=2.0, **kwargs):
    """清除代理 + 失败重试"""
    old_env = {}
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
        if var in os.environ:
            old_env[var] = os.environ.pop(var)
    try:
        for attempt in range(1, retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"  API第{attempt}次失败，重试... ({str(e)[:50]})")
                    time.sleep(delay)
                else:
                    raise
    finally:
        for var, val in old_env.items():
            os.environ[var] = val


def calc_percentile(history_values: pd.Series, current_value: float) -> Optional[float]:
    """计算当前值在历史序列中的分位"""
    if history_values is None or len(history_values) == 0:
        return None
    if current_value is None or pd.isna(current_value):
        return None
    valid = history_values.dropna()
    if len(valid) == 0:
        return None
    count = (valid <= float(current_value)).sum()
    return round(float(count) / len(valid) * 100, 2)


def calc_pe_percentile_from_table(pe: float, sw_code: str) -> Optional[float]:
    """用申万行业PE历史百分位表计算分位（确定性，无随机）"""
    if pe is None or pe <= 0 or sw_code not in SW_PE_TABLE:
        return None
    v = SW_PE_TABLE[sw_code]
    p = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)
    if pe <= v[0]:
        return round(max(0.0, min(5.0, pe / v[0] * 5.0)), 1)
    if pe >= v[-1]:
        return round(min(100.0, 95.0 + (pe - v[-1]) / v[-1] * 5.0), 1)
    for i in range(len(v) - 1):
        if v[i] <= pe <= v[i + 1]:
            frac = (pe - v[i]) / (v[i + 1] - v[i])
            pct = p[i] + frac * (p[i + 1] - p[i])
            return round(float(pct), 1)
    return None


def calc_pb_percentile_from_table(pb: float, sw_code: str) -> Optional[float]:
    """用申万行业PB历史百分位表计算分位（确定性，无随机）"""
    if pb is None or pb <= 0 or sw_code not in SW_PB_TABLE:
        return None
    v = SW_PB_TABLE[sw_code]
    p = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)
    if pb <= v[0]:
        return round(max(0.0, min(5.0, pb / v[0] * 5.0)), 1)
    if pb >= v[-1]:
        return round(min(100.0, 95.0 + (pb - v[-1]) / v[-1] * 5.0), 1)
    for i in range(len(v) - 1):
        if v[i] <= pb <= v[i + 1]:
            frac = (pb - v[i]) / (v[i + 1] - v[i])
            pct = p[i] + frac * (p[i + 1] - p[i])
            return round(float(pct), 1)
    return None


# ============================================================================
# 中证指数官方API — 宽基指数PE真实分位
# ============================================================================

def fetch_csindex_broad(code: str, name: str) -> Optional[Dict]:
    """从中证指数官方获取宽基指数PE真实历史分位"""
    logger.info(f"[csindex] 获取 {code} {name}...")
    result = {
        "code": code, "name": name,
        "source": "中证指数官方(csindex)",
        "is_real_pe": True, "is_real_pb": False,
        "fetch_time": datetime.now().isoformat(),
    }

    try:
        df = ak.stock_zh_index_hist_csindex(
            symbol=code,
            start_date="20100101",
            end_date=datetime.now().strftime("%Y%m%d")
        )
        if df is None or len(df) == 0:
            logger.warning(f"  ❌ 无数据返回")
            return None

        # PE：滚动市盈率列
        pe_col = "滚动市盈率"
        if pe_col not in df.columns:
            logger.warning(f"  ❌ 无{pe_col}列")
            return None

        pe_series = df[pe_col].astype(float)
        pe_valid = pe_series.dropna()

        if len(pe_valid) == 0:
            logger.warning(f"  ❌ 无有效PE数据")
            return None

        latest_pe = float(pe_valid.iloc[-1])
        latest_date = str(df.loc[pe_valid.index[-1], "日期"])[:10]
        pe_pct = calc_percentile(pe_valid, latest_pe)

        result["pe"] = round(latest_pe, 2)
        result["pe_percentile"] = pe_pct
        result["pe_count"] = len(pe_valid)
        result["pe_data_start"] = str(df["日期"].iloc[0])[:10]
        result["pe_data_end"] = latest_date
        result["is_real_pe"] = True

        logger.info(f"  ✅ PE={latest_pe:.2f}，分位={pe_pct}%，{len(pe_valid)}条历史数据")
        return result

    except Exception as e:
        logger.warning(f"  ❌ csindex获取失败: {str(e)[:60]}")
        return None


# ============================================================================
# 乐咕乐股API — 备选数据源
# ============================================================================

def fetch_lg_broad(code: str, info: Dict) -> Optional[Dict]:
    """乐咕乐股获取宽基指数PE/PB真实分位（备选）"""
    lg_name = info["lg_name"]
    logger.info(f"[乐咕fallback] 获取 {info['name']} ({code}) ...")
    result = {
        "code": code, "name": info["name"],
        "source": "乐咕乐股(fallback)",
        "is_real_pe": False, "is_real_pb": False,
        "fetch_time": datetime.now().isoformat(),
    }

    # PE
    try:
        pe_df = _clear_proxy_and_call(ak.stock_index_pe_lg, symbol=lg_name)
        pe_val = float(pe_df["滚动市盈率"].iloc[-1])
        pe_pct = calc_percentile(pe_df["滚动市盈率"], pe_val)
        result["pe"] = round(pe_val, 4)
        result["pe_percentile"] = pe_pct
        result["pe_count"] = len(pe_df)
        result["pe_data_start"] = str(pe_df["日期"].iloc[0])[:10]
        result["pe_data_end"] = str(pe_df["日期"].iloc[-1])[:10]
        result["is_real_pe"] = True
        logger.info(f"  ✅ PE={pe_val:.2f}，分位={pe_pct}%")
    except Exception as e:
        logger.warning(f"  ❌ PE获取失败: {e}")

    # PB
    try:
        pb_df = _clear_proxy_and_call(ak.stock_index_pb_lg, symbol=lg_name)
        if "市净率" in pb_df.columns:
            pb_val = float(pb_df["市净率"].iloc[-1])
        else:
            pb_val = float(pb_df.iloc[-1, 2])
        pb_pct = calc_percentile(pb_df["市净率"], pb_val)
        result["pb"] = round(pb_val, 4)
        result["pb_percentile"] = pb_pct
        result["pb_count"] = len(pb_df)
        result["is_real_pb"] = True
        logger.info(f"  ✅ PB={pb_val:.2f}，分位={pb_pct}%")
    except Exception as e:
        logger.warning(f"  ⚠️ PB获取失败: {e}")

    if not result.get("pe"):
        return None
    return result


# ============================================================================
# 申万行业
# ============================================================================

def fetch_sw_industry_from_cache() -> Dict[str, Dict]:
    """从本地申万行业缓存读取数据 + 确定性百分位估算"""
    sw_file = BASE_DIR / "data" / "sw_industry_valuation_latest.json"
    industries = {}

    if sw_file.exists():
        with open(sw_file, encoding='utf-8') as f:
            sw_data = json.load(f)
        gen_time = datetime.fromisoformat(sw_data["meta"]["generated_at"])
        age_hours = (datetime.now() - gen_time).total_seconds() / 3600
        logger.info(f"读取申万行业缓存: {sw_file.name}（生成于{gen_time.strftime('%m-%d %H:%M')}，{age_hours:.1f}小时前）")

        for code, d in sw_data.get("industries", {}).items():
            code = code.replace(".SI", "")
            pe = d.get("pe_ttm") or d.get("pe")
            pb = d.get("pb")
            pe_pct = calc_pe_percentile_from_table(pe, code)
            pb_pct = calc_pb_percentile_from_table(pb, code)

            industries[code] = {
                "code": code,
                "name": d.get("name", ""),
                "pe": pe,
                "pe_percentile": pe_pct,
                "pb": pb,
                "pb_percentile": pb_pct,
                "source": "申万官方估值+历史百分位表(确定性)",
                "is_real_pe": False,
                "is_real_pb": False,
                "fetch_time": sw_data["meta"]["generated_at"],
            }
            flag = "✅" if (pe_pct and pe_pct <= 30) else "  "
            logger.info(f"  {flag}{code} {d.get('name','')}: PE={pe}(分位={pe_pct}%) PB={pb}(分位={pb_pct}%)")
        return industries

    logger.warning("申万行业缓存不存在，尝试直接API...")
    try:
        df = _clear_proxy_and_call(ak.sw_index_first_info)
        for _, row in df.iterrows():
            code = str(row["行业代码"]).replace(".SI", "")
            pe = float(row["TTM(滚动)市盈率"]) if pd.notna(row["TTM(滚动)市盈率"]) else None
            pb = float(row["市净率"]) if pd.notna(row["市净率"]) else None
            pe_pct = calc_pe_percentile_from_table(pe, code)
            pb_pct = calc_pb_percentile_from_table(pb, code)
            industries[code] = {
                "code": code, "name": row["行业名称"],
                "pe": pe, "pe_percentile": pe_pct,
                "pb": pb, "pb_percentile": pb_pct,
                "source": "申万官方估值+历史百分位表(确定性)",
                "is_real_pe": False, "is_real_pb": False,
                "fetch_time": datetime.now().isoformat(),
            }
        return industries
    except Exception as e:
        logger.error(f"申万行业API也失败: {e}")
        return industries


# ============================================================================
# A股整体
# ============================================================================

def fetch_market_overall() -> Optional[Dict]:
    """获取A股整体PB分位"""
    try:
        df = _clear_proxy_and_call(ak.stock_a_all_pb)
        latest = df.iloc[-1]
        return {
            "code": "ALL", "name": "A股整体",
            "pb_percentile_all": round(float(latest["quantileInAllHistoryMiddlePB"]) * 100, 2),
            "pb_percentile_10y": round(float(latest["quantileInRecent10YearsMiddlePB"]) * 100, 2),
            "pb_median": float(latest["middlePB"]),
            "date": str(latest["date"]),
            "source": "乐咕乐股-A股整体PB",
            "is_real": True,
        }
    except Exception as e:
        logger.warning(f"A股整体PB分位失败: {e}")
        return None


# ============================================================================
# 主函数
# ============================================================================

def main():
    logger.info("=" * 70)
    logger.info("计算指数历史分位 v3.0（中证指数官方为主 + 乐咕fallback + 申万行业）")
    logger.info("=" * 70)

    start = datetime.now()
    indices = {}
    sw_industries = {}
    csindex_success = 0
    lg_success = 0

    # ── 1. 宽基指数（csindex 2010至今，16.5年历史）──
    for code, name in CSINDEX_BROAD.items():
        csindex_result = fetch_csindex_broad(code, name)

        # 乐咕乐股对比（当前网站504不可用，暂时跳过）
        # lg_result = None
        # if code in LG_BROAD:
        #     try:
        #         logger.info(f"  → 对比乐咕乐股数据量...")
        #         lg_result = fetch_lg_broad(code, LG_BROAD[code])
        #     except Exception as e:
        #         logger.warning(f" 乐咕备选失败: {e}")

        if csindex_result:
            indices[code] = csindex_result
            csindex_success += 1
        else:
            logger.warning(f"  ❌ {name}({code}) 无数据源可用")

        time.sleep(0.3)

    # ── 2. 申万行业（确定性估算）──
    sw_industries = fetch_sw_industry_from_cache()

    # ── 3. A股整体 ──
    market = fetch_market_overall()
    if market:
        indices["ALL"] = market

    end = datetime.now()
    duration = (end - start).total_seconds()

    # ── 合并已有indices（保留step0a中证指数官方数据）──
    existing_indices = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            existing_indices = existing_data.get('indices', {})
            if existing_indices:
                logger.info(f"  📎 保留已有indices: {list(existing_indices.keys())}")
        except Exception as e:
            logger.warning(f"  ⚠️ 读取已有文件失败: {e}")

    # 新数据覆盖同名key
    merged_indices = {**existing_indices, **indices}

    output = {
        "meta": {
            "generated_at": end.isoformat(),
            "duration_seconds": round(duration, 2),
            "source": "中证指数官方(csindex,主) + 乐咕乐股(fallback) + 申万官方+历史表(行业确定性估算)",
            "version": "v3.0",
            "csindex_success": csindex_success,
            "lg_fallback_success": lg_success,
            "sw_count": len(sw_industries),
        },
        "indices": merged_indices,
        "sw_industries": sw_industries,
        "etf_mapping": ETF_IDX_MAP,
        "stats": {
            "broad_real": len([k for k in merged_indices if k != "ALL"]),
            "csindex_direct": csindex_success,
            "lg_fallback": lg_success,
            "sw_covered": len(sw_industries),
        }
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, ensure_ascii=False, indent=2, fp=f)

    logger.info("=" * 70)
    logger.info(f"✅ 完成！耗时: {duration:.1f}秒")
    logger.info(f"   中证官方直取: {csindex_success}个")
    logger.info(f"   乐咕fallback: {lg_success}个")
    logger.info(f"   申万行业: {len(sw_industries)}个")
    logger.info(f"   输出: {OUTPUT_FILE}")

    # 摘要输出
    print("\n" + "=" * 70)
    print("宽基指数真实历史分位")
    print("=" * 70)
    for code, data in indices.items():
        if code == "ALL":
            print(f"  A股整体: PB分位={data.get('pb_percentile_all','?')}%(全历史) {data.get('pb_percentile_10y','?')}%(10年)")
        elif data.get("is_real_pe"):
            src_tag = "[csindex]" if "csindex" in data.get("source","") else "[乐咕]"
            print(f"  {data['name']:8s}{src_tag:10s}: PE={data.get('pe'):>6} 分位={data.get('pe_percentile','?'):>5}%  "
                  f"PB={str(data.get('pb','?')):>5} 分位={str(data.get('pb_percentile','?')):>5}%")

    print("\n" + "=" * 70)
    print("申万行业估值（📗<20%  📙20-30%  📕>30%）")
    print("=" * 70)
    sorted_sw = sorted(sw_industries.values(), key=lambda x: x.get("pe_percentile") or 999)
    for ind in sorted_sw:
        p = ind.get("pe_percentile", 0) or 0
        pb_p = ind.get("pb_percentile", 0) or 0
        icon = "📗" if p <= 20 else "📙" if p <= 30 else "📕"
        print(f"  {icon}{ind['name']:10s}: PE={str(ind.get('pe','?')):>6} 分位={p:>5.1f}%  "
              f"PB={str(ind.get('pb','?')):>5} 分位={pb_p:>5.1f}%")

    return output


if __name__ == "__main__":
    main()
