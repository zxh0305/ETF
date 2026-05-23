#!/usr/bin/env python3
"""
build_etf_index_mapping.py
==========================
从 etf_spot_latest.json 自动构建 ETF → 跟踪指数映射表。

映射策略（从高到低优先级）：
  1. 精确映射表  → confidence=exact
  2. 关键词匹配  → confidence=high/medium/low
  3. 保留不匹配记录 → mapping_status=unresolved

输出：
  data/etf_index_mapping.json
"""

import json, sys, os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUT_FILE = os.path.join(DATA_DIR, "etf_index_mapping.json")

# ──────────────────────────────────────────────
# 精确映射表：ETF代码 → 指数信息
#   (来源：akshare fund_etf_spot_em + 人工标注)
# ──────────────────────────────────────────────
EXACT_MAP = {
    # 宽基ETF
    "sh510050": {"index_code": "000016", "index_name": "上证50",   "source": "精确映射表"},
    "sh510100": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh510300": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},
    "sh510310": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},  # 300ETF易方达
    "sh510330": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},  # 300ETF华夏
    "sh510350": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},  # 300ETF工银
    "sh510360": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},  # 300ETF广发
    "sh510390": {"index_code": "000300", "index_name": "沪深300",   "source": "精确映射表"},  # 300ETF
    "sh510800": {"index_code": "000905", "index_name": "中证500",   "source": "精确映射表"},
    "sh510500": {"index_code": "000905", "index_name": "中证500",   "source": "精确映射表"},
    "sh510560": {"index_code": "000905", "index_name": "中证500",   "source": "精确映射表"},
    "sh510580": {"index_code": "000905", "index_name": "中证500",   "source": "精确映射表"},
    "sh510180": {"index_code": "000001", "index_name": "上证180",   "source": "精确映射表"},
    "sh510020": {"index_code": "000010", "index_name": "上证180",   "source": "精确映射表"},  # 上证180 → 000010
    "sh510880": {"index_code": "000015", "index_name": "上证红利",  "source": "精确映射表"},
    "sh515000": {"index_code": "000689", "index_name": "中证医疗",  "source": "精确映射表"},  # 科技ETF华宝 → 中证医疗
    "sh515080": {"index_code": "000922", "index_name": "中证红利",  "source": "精确映射表"},
    "sh515220": {"index_code": "399677", "index_name": "国证证券",  "source": "精确映射表"},  # 证券ETF国泰
    "sh512010": {"index_code": "399933", "index_name": "中证医药",  "source": "精确映射表"},
    "sh512000": {"index_code": "399975", "index_name": "证券公司",  "source": "精确映射表"},  # 证券ETF华宝
    "sh512200": {"index_code": "399958", "index_name": "中证银行",  "source": "精确映射表"},  # 银行ETF
    "sh512400": {"index_code": "000928", "index_name": "中证军工",  "source": "精确映射表"},
    "sh512660": {"index_code": "399967", "index_name": "中证军工",  "source": "精确映射表"},
    "sh512680": {"index_code": "399967", "index_name": "中证军工",  "source": "精确映射表"},  # 军工ETF
    "sh512760": {"index_code": "990001", "index_name": "中华半导体芯片", "source": "精确映射表"},
    "sh512480": {"index_code": "H30306", "index_name": "半导体",   "source": "精确映射表"},
    "sh512800": {"index_code": "801780", "index_name": "中证银行",  "source": "精确映射表"},  # 银行ETF中证
    "sh512690": {"index_code": "399986", "index_name": "中证银行",  "source": "精确映射表"},
    "sh512980": {"index_code": "399971", "index_name": "中证传媒",  "source": "精确映射表"},  # 传媒ETF
    "sh512170": {"index_code": "931728", "index_name": "医疗器械",  "source": "精确映射表"},
    "sh512380": {"index_code": "931789", "index_name": "医药健康",  "source": "精确映射表"},
    "sh512760": {"index_code": "990001", "index_name": "中华半导体芯片", "source": "精确映射表"},
    "sh512360": {"index_code": "931796", "index_name": "中证军工",  "source": "精确映射表"},
    "sh512580": {"index_code": "931798", "index_name": "中证光伏",  "source": "精确映射表"},  # 光伏ETF
    "sh512790": {"index_code": "000905", "index_name": "中证500",   "source": "精确映射表"},
    "sh515790": {"index_code": "931798", "index_name": "中证光伏",  "source": "精确映射表"},
    "sh515030": {"index_code": "931532", "index_name": "新能源",    "source": "精确映射表"},  # 新能源ETF
    "sh515100": {"index_code": "000015", "index_name": "上证红利",  "source": "精确映射表"},
    "sh512980": {"index_code": "399971", "index_name": "中证传媒",  "source": "精确映射表"},
    "sh512960": {"index_code": "000015", "index_name": "上证红利",  "source": "精确映射表"},
    "sh512170": {"index_code": "931728", "index_name": "医疗器械",  "source": "精确映射表"},
    "sh512010": {"index_code": "399933", "index_name": "中证医药",  "source": "精确映射表"},
    "sh512000": {"index_code": "399975", "index_name": "证券公司",  "source": "精确映射表"},
    "sh515220": {"index_code": "399677", "index_name": "国证证券",  "source": "精确映射表"},

    # 科创板ETF
    "sh588000": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588050": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588080": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588090": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588180": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588220": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh588260": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},

    # 创业板ETF
    "sz159915": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz159949": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz159952": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz159977": {"index_code": "399673", "index_name": "创业板50", "source": "精确映射表"},  # 创业板50
    "sz159604": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz159620": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},

    # QDII ETF
    "sh513100": {"index_code": "IXIC",  "index_name": "纳斯达克100", "source": "精确映射表"},
    "sh513500": {"index_code": "SPX",   "index_name": "标普500",     "source": "精确映射表"},
    "sh513660": {"index_code": "HSI",   "index_name": "恒生指数",   "source": "精确映射表"},
    "sh513180": {"index_code": "HSTECH","index_name": "恒生科技",   "source": "精确映射表"},
    "sh513080": {"index_code": "NKY",   "index_name": "日经225",    "source": "精确映射表"},
    "sh513520": {"index_code": "DAX",   "index_name": "德国DAX",    "source": "精确映射表"},
    "sh518880": {"index_code": "XAUUSD", "index_name": "现货黄金",   "source": "精确映射表"},
    "sh159628": {"index_code": "XAUUSD", "index_name": "现货黄金",   "source": "精确映射表"},
    "sh518880": {"index_code": "XAUUSD", "index_name": "现货黄金",   "source": "精确映射表"},
    "sz159934": {"index_code": "XAUUSD", "index_name": "现货黄金",   "source": "精确映射表"},
    "sz159815": {"index_code": "XAUUSD", "index_name": "现货黄金",   "source": "精确映射表"},
    "sz162411": {"index_code": "CL",     "index_name": "WTI原油",    "source": "精确映射表"},
    "sz160723": {"index_code": "CL",     "index_name": "WTI原油",    "source": "精确映射表"},  # 嘉实原油LOF

    # QDII LOF
    "sz161125": {"index_code": "SPX",    "index_name": "标普500",    "source": "精确映射表"},
    "sz161130": {"index_code": "IXIC",   "index_name": "纳斯达克100", "source": "精确映射表"},
    "sz160924": {"index_code": "HSI",    "index_name": "恒生指数",    "source": "精确映射表"},
    "sz164705": {"index_code": "HSI",    "index_name": "恒生指数",    "source": "精确映射表"},
    "sz161831": {"index_code": "HSCEI",  "index_name": "恒生国企指数","source": "精确映射表"},
    "sz164906": {"index_code": "HSTECH", "index_name": "中概互联",    "source": "精确映射表"},
    "sz162415": {"index_code": "SPX",    "index_name": "标普美国消费","source": "精确映射表"},
    "sz161126": {"index_code": "SPX",    "index_name": "标普生物科技","source": "精确映射表"},
    "sz161127": {"index_code": "SPX",    "index_name": "标普医疗保健","source": "精确映射表"},
    "sz161128": {"index_code": "SPX",    "index_name": "标普信息科技","source": "精确映射表"},
    "sz164824": {"index_code": "NSE",    "index_name": "印度Nifty50","source": "精确映射表"},
    "sz160140": {"index_code": "RMZ",    "index_name": "美国REIT指数","source": "精确映射表"},
    "sh501312": {"index_code": "IXIC",   "index_name": "纳斯达克科技","source": "精确映射表"},
    "sh501303": {"index_code": "HSI",    "index_name": "恒生中型股","source": "精确映射表"},
    "sh501302": {"index_code": "HSI",    "index_name": "恒生指数","source": "精确映射表"},
    "sh501225": {"index_code": "SOX",    "index_name": "全球芯片","source": "精确映射表"},
    "sz163208": {"index_code": "XOI",    "index_name": "全球油气能源","source": "精确映射表"},

    # 沪深300 LOF
    "sz160706": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},
    "sz161811": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},
    "sz160807": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},
    "sz163407": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},
    "sz163821": {"index_code": "000300", "index_name": "沪深300等权","source": "精确映射表"},
    "sz165309": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},
    "sz165515": {"index_code": "000300", "index_name": "沪深300",  "source": "精确映射表"},

    # 中证500 LOF
    "sz162711": {"index_code": "000905", "index_name": "中证500",  "source": "精确映射表"},
    "sz160637": {"index_code": "000905", "index_name": "中证500",  "source": "精确映射表"},
    "sz161017": {"index_code": "000905", "index_name": "中证500增强","source": "精确映射表"},
    "sz162216": {"index_code": "000905", "index_name": "中证500增强","source": "精确映射表"},
    "sz165511": {"index_code": "000905", "index_name": "中证500",  "source": "精确映射表"},

    # 上证50 LOF / 50ETF
    "sz160716": {"index_code": "000016", "index_name": "基本面50",  "source": "精确映射表"},
    "sz160125": {"index_code": "000016", "index_name": "上证50",   "source": "精确映射表"},
    "sz165312": {"index_code": "000016", "index_name": "建信50",   "source": "精确映射表"},

    # 创业板相关
    "sz160420": {"index_code": "399006", "index_name": "创业板50", "source": "精确映射表"},
    "sz162720": {"index_code": "000905", "index_name": "中证500",  "source": "精确映射表"},
    "sz163209": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz162107": {"index_code": "399006", "index_name": "创业板指", "source": "精确映射表"},
    "sz160636": {"index_code": "IXIC",   "index_name": "中概互联", "source": "精确映射表"},  # 互联网L
    "sz160137": {"index_code": "IXIC",   "index_name": "中概互联", "source": "精确映射表"},  # 互联基金

    # 科创板LOF
    "sh506001": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506002": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506003": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506005": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506006": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506008": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
    "sh506000": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},

    # 行业ETF（精确）
    "sz159938": {"index_code": "399933", "index_name": "中证医药", "source": "精确映射表"},
    "sz159992": {"index_code": "399932", "index_name": "中证消费", "source": "精确映射表"},
    "sz159755": {"index_code": "399932", "index_name": "中证消费", "source": "精确映射表"},
    "sz159745": {"index_code": "931729", "index_name": "中证农业", "source": "精确映射表"},
    "sz159995": {"index_code": "990001", "index_name": "中华半导体芯片","source": "精确映射表"},
    "sz159941": {"index_code": "IXIC",   "index_name": "纳斯达克100","source": "精确映射表"},
    "sz159920": {"index_code": "HSI",    "index_name": "恒生指数", "source": "精确映射表"},
    "sz159607": {"index_code": "000300", "index_name": "沪深300", "source": "精确映射表"},
    "sz159603": {"index_code": "000905", "index_name": "中证500", "source": "精确映射表"},
    "sz159601": {"index_code": "000300", "index_name": "中证A50",  "source": "精确映射表"},
    "sz159691": {"index_code": "000905", "index_name": "中证500", "source": "精确映射表"},
    "sh588090": {"index_code": "000688", "index_name": "科创50",   "source": "精确映射表"},
}


# ──────────────────────────────────────────────
# 关键词匹配规则（按优先级排列，每条包含：关键词 → 指数信息 + 置信度）
# ──────────────────────────────────────────────
# 格式: (关键词, 是否须精确匹配单词, 指数代码, 指数名称, 置信度, 来源)
KEYWORD_RULES = [
    # ---- 宽基指数（高置信度）----
    ("沪深300",    True,  "000300", "沪深300",           "high",   "名称关键词"),
    ("300ETF",     True,  "000300", "沪深300",           "high",   "名称关键词"),
    ("300 LOF",    True,  "000300", "沪深300",           "high",   "名称关键词"),
    ("中证A100",   True,  "000132", "中证A100",          "high",   "名称关键词"),
    ("基本面50",   True,  "000016", "基本面50",          "high",   "名称关键词"),
    ("上证50",     True,  "000016", "上证50",            "high",   "名称关键词"),
    ("50ETF",      True,  "000016", "上证50",            "high",   "名称关键词"),
    ("中证500",    True,  "000905", "中证500",           "high",   "名称关键词"),
    ("500ETF",     True,  "000905", "中证500",           "high",   "名称关键词"),
    ("500 LOF",    True,  "000905", "中证500",           "high",   "名称关键词"),
    ("中证A50",    True,  "000016", "中证A50",           "high",   "名称关键词"),
    ("MSCI中国A50","True", "000016", "MSCI中国A50",      "high",   "名称关键词"),
    ("创业板指",   True,  "399006", "创业板指",          "high",   "名称关键词"),
    ("创业板",     True,  "399006", "创业板指",          "medium", "名称关键词"),
    ("创50",       True,  "399673", "创业板50",          "high",   "名称关键词"),
    ("科创50",     True,  "000688", "科创50",            "high",   "名称关键词"),
    ("科创板",     True,  "000688", "科创50",            "medium", "名称关键词"),
    ("科创",       True,  "000688", "科创50",            "medium", "名称关键词"),
    ("上证180",    True,  "000010", "上证180",           "high",   "名称关键词"),
    ("上证380",    True,  "000009", "上证380",           "high",   "名称关键词"),
    ("中证1000",   True,  "000852", "中证1000",          "high",   "名称关键词"),
    ("中证800",    True,  "000906", "中证800",           "high",   "名称关键词"),
    ("中证2000",   True,  "932000", "中证2000",          "high",   "名称关键词"),

    # ---- QDII / 跨境（中高置信度）----
    ("纳斯达克100", True,  "IXIC",   "纳斯达克100",       "high",   "名称关键词"),
    ("纳斯达克",    True,  "IXIC",   "纳斯达克综合",      "medium", "名称关键词"),
    ("标普500",     True,  "SPX",    "标普500",           "high",   "名称关键词"),
    ("标普",        True,  "SPX",    "标普",              "medium", "名称关键词"),
    ("恒生指数",    True,  "HSI",    "恒生指数",          "high",   "名称关键词"),
    ("恒生中型股",  True,  "HSMC",   "恒生中型股",        "high",   "名称关键词"),
    ("恒生科技",    True,  "HSTECH", "恒生科技",          "high",   "名称关键词"),
    ("恒生",        True,  "HSI",    "恒生指数",          "medium", "名称关键词"),
    ("恒生国企",    True,  "HSCEI",  "恒生国企指数",       "high",   "名称关键词"),
    ("中概互联",    True,  "IXIC",   "中概互联",          "high",   "名称关键词"),
    ("中概",        True,  "IXIC",   "中概股",            "medium", "名称关键词"),
    ("日经",        True,  "NKY",    "日经225",           "high",   "名称关键词"),
    ("德国DAX",    True,  "DAX",    "德国DAX",          "high",   "名称关键词"),
    ("印度",        True,  "NSE",    "印度Nifty50",       "medium", "名称关键词"),
    ("美国REIT",    True,  "RMZ",    "美国REIT指数",      "high",   "名称关键词"),
    ("海外科技",    True,  "IXIC",   "海外科技",          "medium", "名称关键词"),
    ("全球芯片",    True,  "SOX",    "费城半导体",        "medium", "名称关键词"),
    ("全球油气",    True,  "XOI",    "全球油气能源",        "medium", "名称关键词"),
    ("油气能源",    True,  "XOI",    "全球油气能源",        "medium", "名称关键词"),
    ("海外",        True,  "IXIC",   "海外市场",          "low",    "名称关键词"),

    # ---- 商品（高置信度）----
    ("黄金ETF",     True,  "XAUUSD", "现货黄金",           "high",   "名称关键词"),
    ("黄金LOF",     True,  "XAUUSD", "现货黄金",           "high",   "名称关键词"),
    ("黄金",        True,  "XAUUSD", "现货黄金",           "medium", "名称关键词"),
    ("原油ETF",     True,  "CL",     "WTI原油",            "high",   "名称关键词"),
    ("原油LOF",     True,  "CL",     "WTI原油",            "high",   "名称关键词"),
    ("大宗商品",    True,  "CCI",    "大宗商品",           "medium", "名称关键词"),
    ("商品",        True,  "CCI",    "大宗商品",           "low",    "名称关键词"),
    ("白银",        True,  "XAGUSD", "现货白银",           "medium", "名称关键词"),
    ("石油",        True,  "CL",     "WTI原油",            "medium", "名称关键词"),
    ("豆粕",        True,  "ZM",     "豆粕",              "medium", "名称关键词"),
    ("饲料",        True,  "FTOP",   "饲料",              "low",    "名称关键词"),
    ("能源化工",    True,  "XOP",    "能源化工",           "low",    "名称关键词"),

    # ---- 行业指数（中高置信度）----
    ("中证银行",    True,  "399975", "中证银行",          "high",   "名称关键词"),
    ("银行ETF",     True,  "399975", "中证银行",          "high",   "名称关键词"),
    ("银行LOF",     True,  "399975", "中证银行",          "medium", "名称关键词"),
    ("银行基金",    True,  "399975", "中证银行",          "medium", "名称关键词"),
    ("中证证券",    True,  "399975", "证券公司",          "high",   "名称关键词"),
    ("证券ETF",     True,  "399975", "证券公司",          "high",   "名称关键词"),
    ("证券LOF",     True,  "399975", "证券公司",          "medium", "名称关键词"),
    ("券商基金",    True,  "399975", "证券公司",          "medium", "名称关键词"),
    ("中证医药",    True,  "399933", "中证医药",          "high",   "名称关键词"),
    ("医药ETF",     True,  "399933", "中证医药",          "high",   "名称关键词"),
    ("医药LOF",     True,  "399933", "中证医药",          "medium", "名称关键词"),
    ("中证医疗",    True,  "399932", "中证医疗",          "high",   "名称关键词"),
    ("医疗器械",    True,  "931728", "医疗器械",          "medium", "名称关键词"),
    ("中证消费",    True,  "399932", "中证消费",          "high",   "名称关键词"),
    ("消费ETF",     True,  "399932", "中证消费",          "high",   "名称关键词"),
    ("消费LOF",     True,  "399932", "中证消费",          "medium", "名称关键词"),
    ("食品饮料",    True,  "399396", "国证食品饮料",       "high",   "名称关键词"),
    ("白酒",        True,  "399397", "中证白酒",          "medium", "名称关键词"),
    ("中证军工",    True,  "399967", "中证军工",          "high",   "名称关键词"),
    ("军工ETF",     True,  "399967", "中证军工",          "high",   "名称关键词"),
    ("军工LOF",     True,  "399967", "中证军工",          "medium", "名称关键词"),
    ("中航军工",    True,  "399967", "中证军工",          "high",   "名称关键词"),
    ("半导体芯片",  True,  "990001", "中华半导体芯片",     "high",   "名称关键词"),
    ("半导体ETF",   True,  "990001", "中华半导体芯片",     "high",   "名称关键词"),
    ("芯片ETF",     True,  "990001", "中华半导体芯片",     "high",   "名称关键词"),
    ("芯片LOF",     True,  "990001", "中华半导体芯片",     "medium", "名称关键词"),
    ("集成电路",    True,  "990001", "中华半导体芯片",     "medium", "名称关键词"),
    ("中证光伏",    True,  "931798", "中证光伏产业",       "high",   "名称关键词"),
    ("光伏ETF",     True,  "931798", "中证光伏产业",       "high",   "名称关键词"),
    ("新能源ETF",   True,  "931798", "中证光伏产业",       "medium", "名称关键词"),
    ("新能源车",    True,  "399976", "中证新能源汽车",     "high",   "名称关键词"),
    ("锂电池",      True,  "399976", "中证新能源汽车",     "medium", "名称关键词"),
    ("中证红利",    True,  "000922", "中证红利",          "high",   "名称关键词"),
    ("红利ETF",     True,  "000922", "中证红利",          "high",   "名称关键词"),
    ("红利LOF",     True,  "000922", "中证红利",          "medium", "名称关键词"),
    ("中证煤炭",    True,  "399812", "中证煤炭",          "high",   "名称关键词"),
    ("煤炭LOF",     True,  "399812", "中证煤炭",          "high",   "名称关键词"),
    ("有色金属",    True,  "000819", "中证有色金属",       "medium", "名称关键词"),
    ("地产ETF",     True,  "000005", "中证全指房地产",     "medium", "名称关键词"),
    ("地产LOF",     True,  "000005", "中证全指房地产",     "medium", "名称关键词"),
    ("中证传媒",    True,  "399971", "中证传媒",          "high",   "名称关键词"),
    ("传媒ETF",     True,  "399971", "中证传媒",          "high",   "名称关键词"),
    ("传媒LOF",    True,  "399971", "中证传媒",          "medium", "名称关键词"),
    ("游戏",        True,  "399971", "中证传媒",          "medium", "名称关键词"),
    ("动漫",        True,  "399971", "中证传媒",          "low",    "名称关键词"),
    ("中证环保",    True,  "000827", "中证环保",          "high",   "名称关键词"),
    ("环境治理",    True,  "000827", "中证环保",          "medium", "名称关键词"),
    ("一带一路",    True,  "000001", "一带一路",          "low",    "名称关键词"),
    ("国企改革",    True,  "000861", "国企改革",          "low",    "名称关键词"),
    ("央企改革",    True,  "000861", "央企改革",          "low",    "名称关键词"),
    ("互联基金",    True,  "IXIC",   "中概互联",          "medium", "名称关键词"),
    ("互联网L",     True,  "IXIC",   "中概互联",          "medium", "名称关键词"),
    ("云计算",      True,  "931071", "中证云计算",         "medium", "名称关键词"),
    ("信息安全",    True,  "399994", "中证信息安全",       "medium", "名称关键词"),
    ("智能家居",    True,  "931008", "中证智能家居",        "medium", "名称关键词"),
    ("物联网",      True,  "399552", "中证物联网",         "low",    "名称关键词"),
    ("中证农业",    True,  "931729", "中证农业",          "high",   "名称关键词"),
    ("中证健康",    True,  "399933", "中证健康",          "medium", "名称关键词"),
    ("养老产业",    True,  "399811", "中证养老产业",        "medium", "名称关键词"),
    ("国防ETF",     True,  "399967", "中证军工",          "high",   "名称关键词"),
    ("国防LOF",     True,  "399967", "中证军工",          "medium", "名称关键词"),
    ("农业ETF",     True,  "931729", "中证农业",          "medium", "名称关键词"),
    ("化工ETF",     True,  "000990", "中证化工",          "medium", "名称关键词"),
    ("钢铁LOF",     True,  "801040", "中证钢铁",          "medium", "名称关键词"),
    ("煤炭ETF",     True,  "399812", "中证煤炭",          "medium", "名称关键词"),
    ("物流ETF",     True,  "000099", "中证物流",          "medium", "名称关键词"),
    ("汽车ETF",     True,  "000803", "中证汽车",          "medium", "名称关键词"),
    ("家用电器",    True,  "930697", "中证家用电器",        "medium", "名称关键词"),
    ("金融科技",    True,  "399699", "中证金融科技",        "medium", "名称关键词"),
    ("人工智能",    True,  "931071", "中证人工智能",        "medium", "名称关键词"),
    ("机器人",      True,  "931073", "中证机器人",          "medium", "名称关键词"),
    ("数字经济",    True,  "931583", "中证数字经济",        "low",    "名称关键词"),
    ("数据要素",    True,  "931583", "中证数字经济",        "low",    "名称关键词"),
    ("教育ETF",     True,  "935103", "中证教育",            "medium", "名称关键词"),
    ("在线消费",    True,  "931638", "中证在线消费",        "low",    "名称关键词"),
    ("旅游ETF",     True,  "931111", "中证旅游",            "medium", "名称关键词"),
    ("REITs",       True,  "000006", "中证REITs",           "medium", "名称关键词"),
    ("钢铁ETF",     True,  "801040", "中证钢铁",            "medium", "名称关键词"),
    ("基建ETF",     True,  "399965", "中证基建",            "medium", "名称关键词"),
    ("交运ETF",     True,  "000099", "中证物流",            "medium", "名称关键词"),
    ("粤港澳",      True,  "980001", "粤港澳大湾区",         "medium", "名称关键词"),
    ("湾区ETF",     True,  "980001", "粤港澳大湾区",         "medium", "名称关键词"),
    ("大湾区",      True,  "980001", "粤港澳大湾区",         "medium", "名称关键词"),
    ("先进制造",    True,  "000812", "中证先进制造",         "medium", "名称关键词"),
    ("科技50",      True,  "000688", "科创50",              "medium", "名称关键词"),
    ("科技ETF",     True,  "000689", "中证科技",            "medium", "名称关键词"),
    ("科技LOF",     True,  "000689", "中证科技",            "low",    "名称关键词"),
    ("300增强",     True,  "000300", "沪深300增强",         "medium", "名称关键词"),
    ("500增强",     True,  "000905", "中证500增强",         "medium", "名称关键词"),
    ("基本面",      True,  "000016", "基本面50",            "medium", "名称关键词"),
    ("低波",        True,  "000016", "中证红利低波",        "medium", "名称关键词"),
    ("价值",        True,  "000919", "中证价值",            "low",    "名称关键词"),
    ("成长",        True,  "000938", "中证成长",            "low",    "名称关键词"),
    ("质量",        True,  "000847", "中证质量",            "low",    "名称关键词"),
    ("均衡",        True,  "000833", "中证均衡",            "low",    "名称关键词"),
    ("稳健",        True,  "000836", "中证稳健",            "low",    "名称关键词"),
    ("ESG",         True,  "931468", "中证ESG",             "medium", "名称关键词"),
    ("ESG责任",     True,  "931468", "中证ESG",             "medium", "名称关键词"),
    ("质量价值",    True,  "000847", "中证质量价值",         "medium", "名称关键词"),
    ("竞争优势",    True,  "931739", "中证竞争优势",        "low",    "名称关键词"),
    ("金牛",        True,  "000920", "金牛",               "low",    "名称关键词"),
    ("ESGETF",      True,  "931468", "中证ESG",            "high",   "名称关键词"),
    ("创成长",      True,  "399673", "创业板动量成长",       "high",   "名称关键词"),
    ("创蓝筹",      True,  "399673", "创业板蓝筹",           "high",   "名称关键词"),
    ("创业板50",    True,  "399673", "创业板50",             "high",   "名称关键词"),
    ("创业50",      True,  "399673", "创业板50",             "high",   "名称关键词"),
    ("创业富国",    True,  "399673", "创业板50",             "high",   "名称关键词"),
    ("创业博时",    True,  "399673", "创业板50",             "high",   "名称关键词"),
    ("创业南方",    True,  "399673", "创业板50",             "high",   "名称关键词"),
    ("浙商300",     True,  "000300", "沪深300",             "medium", "名称关键词"),
    ("信诚新旺",    True,  "000300", "沪深300",             "low",    "名称关键词"),
]


# ──────────────────────────────────────────────
# 主映射逻辑
# ──────────────────────────────────────────────
def map_etf(code: str, name: str) -> dict:
    """为单只ETF返回映射结果"""
    # 1. 精确匹配
    if code in EXACT_MAP:
        m = EXACT_MAP[code]
        return {
            "etf_code": code,
            "etf_name": name,
            "index_code": m["index_code"],
            "index_name": m["index_name"],
            "source": m["source"],
            "confidence": "exact",
            "mapping_status": "resolved",
            "mapping_method": "exact_code_match"
        }

    # 2. 关键词匹配（按顺序，找到第一个即返回）
    for keyword, _, index_code, index_name, confidence, source in KEYWORD_RULES:
        if keyword in name:
            return {
                "etf_code": code,
                "etf_name": name,
                "index_code": index_code,
                "index_name": index_name,
                "source": source,
                "confidence": confidence,
                "mapping_status": "resolved",
                "mapping_method": "keyword_match"
            }

    # 3. 无法匹配 → unresolved
    return {
        "etf_code": code,
        "etf_name": name,
        "index_code": None,
        "index_name": None,
        "source": None,
        "confidence": None,
        "mapping_status": "unresolved",
        "mapping_method": None
    }


def run():
    # 读取 ETF 列表
    spot_file = os.path.join(DATA_DIR, "etf_spot_latest.json")
    if not os.path.exists(spot_file):
        print(f"[ERROR] {spot_file} not found. Run etf_data_collector.py first.")
        sys.exit(1)

    with open(spot_file) as f:
        raw = json.load(f)
    etfs = raw["data"] if isinstance(raw, dict) else raw

    # 执行映射
    mappings = [map_etf(e["code"], e.get("name", "")) for e in etfs]

    # 统计
    stats = {
        "total": len(mappings),
        "resolved_exact": sum(1 for m in mappings if m["mapping_status"] == "resolved" and m["confidence"] == "exact"),
        "resolved_high":   sum(1 for m in mappings if m["mapping_status"] == "resolved" and m["confidence"] == "high"),
        "resolved_medium":sum(1 for m in mappings if m["mapping_status"] == "resolved" and m["confidence"] == "medium"),
        "resolved_low":   sum(1 for m in mappings if m["mapping_status"] == "resolved" and m["confidence"] == "low"),
        "unresolved":     sum(1 for m in mappings if m["mapping_status"] == "unresolved"),
    }
    stats["resolved"] = stats["total"] - stats["unresolved"]
    stats["high_confidence"] = stats["resolved_exact"] + stats["resolved_high"]

    # 输出 JSON
    result = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_etf_count": stats["total"],
            "stats": stats,
            "note": "mapping_status=unresolved 需要人工补充"
        },
        "data": mappings
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=" * 55)
    print(f"  ETF → 跟踪指数 映射构建完成")
    print("=" * 55)
    print(f"  总 ETF 数:              {stats['total']}")
    print(f"  成功映射 (resolved):    {stats['resolved']}  ({100*stats['resolved']/max(stats['total'],1):.1f}%)")
    print(f"  ├─ exact (精确匹配):    {stats['resolved_exact']}")
    print(f"  ├─ high (高置信度):     {stats['resolved_high']}")
    print(f"  ├─ medium (中置信度):   {stats['resolved_medium']}")
    print(f"  └─ low (低置信度):      {stats['resolved_low']}")
    print(f"  无法匹配 (unresolved): {stats['unresolved']} ({100*stats['unresolved']/max(stats['total'],1):.1f}%)")
    print(f"  高置信度合计:           {stats['high_confidence']} ({100*stats['high_confidence']/max(stats['total'],1):.1f}%)")
    print(f"  输出文件: {OUT_FILE}")
    print()

    # 打印 unresolved 示例
    unresolved = [m for m in mappings if m["mapping_status"] == "unresolved"]
    if unresolved:
        print(f"  unresolved 示例（前10只）:")
        for m in unresolved[:10]:
            print(f"    {m['etf_code']} | {m['etf_name']}")

    return result


if __name__ == "__main__":
    run()
