#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF估值补全脚本 v6.6 - csindex官方PE+申万行业+实时成交额
==========================================
数据源：
1. 中证指数官方(csindex) - 9个宽基指数6年真实PE分位(1539条历史)
2. 乐咕乐股(备用) - 12个宽基指数历史分位
3. 申万行业 - 31个一级行业加权PE/PB
4. 实时成交额 - 20日均成交额(全市场ETF)
4. 巨潮资讯cninfo - 国证行业PE（第三数据源）

更新 v6.4：
- 新增申万行业数据新鲜度检查（超过3天自动警告）
- 修复component_count显示：从sw_industry_valuation补充到percentiles数据
- 替换Sina实时成交额为20日均成交额（akshare fund_etf_hist_sina）
- LOF基金：hist_sina也有效，正常获取20日均
- 兜底：Sina实时成交额（当hist_sina失败时）

输出: data/etf_valuation_latest.json
"""

import json, logging, math, os, time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import akshare as ak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
logger = logging.getLogger("etf_val_v5")

BASE_DIR = Path(__file__).parent.parent.resolve()
INPUT_FILE = BASE_DIR / "data" / "etf_spot_latest.json"
OUTPUT_FILE = BASE_DIR / "data" / "etf_valuation_latest.json"
PERCENTILE_FILE = BASE_DIR / "data" / "index_percentiles_latest.json"
SW_FILE = BASE_DIR / "data" / "sw_industry_valuation_latest.json"
CNINFO_FILE = BASE_DIR / "data" / "cninfo_industry_latest.json"

# ============================================================================
# 宽基指数映射
# ============================================================================
BROAD_IDX_CODE_MAP = {
    # 沪深300 (000300) - 15只
    "sh510300": "000300", "sz159919": "000300", "sh510310": "000300",
    "sh512990": "000300", "sz159925": "000300", "sh510350": "000300",
    "sz159810": "000300", "sh512980": "000300",
    "sh501043": "000300", "sh501045": "000300",
    "sz165309": "000300", "sz163821": "000300", "sz163407": "000300",
    "sz161811": "000300", "sz160706": "000300",
    # 中证500 (000905) - 7只
    "sh510500": "000905", "sz159922": "000905", "sh510510": "000905",
    "sz159982": "000905", "sh512510": "000905",
    "sz162711": "000905", "sh501037": "000905",
    # 上证50 (000016) - 3只
    "sh510100": "000016", "sz159901": "000016", "sh502048": "000016",
    # 创业板50 (399673) - 2只
    "sz159682": "399673", "sz159795": "399673",
    # 创业板指(399005) → 映射到创业板50(399673)，因percentile文件缺399005数据
    "sz159915": "399673", "sz160637": "399673", "sz160223": "399673",
    "sz160325": "399673", "sz162720": "399673", "sz161914": "399673",
    "sz160926": "399673", "sz160529": "399673", "sz160143": "399673",
    "sz160420": "399673", "sz161040": "399673", "sz163209": "399673", "sz166027": "399673",
    # 科创50(000688) → 中证指数官方有PE数据
    "sh588000": "000688", "sz588080": "000688", "sh588050": "000688",
    "sh588080": "000688", "sh588010": "000688",
    "sh506000": "000688", "sh506001": "000688", "sh506002": "000688",
    "sh506003": "000688", "sh506005": "000688", "sh506006": "000688",
    "sh506008": "000688", "sh501079": "000688", "sh501080": "000688",
    "sh501081": "000688", "sh501082": "000688", "sh501083": "000688",
    "sh501085": "000688", "sh501096": "000688", "sh501097": "000688",
    "sh501098": "000688", "sh501200": "000688",
    # 中证1000 (000852) - 4只
    "sh512100": "000852", "sz159633": "000852", "sh512110": "000852",
    "sz159845": "000852",
    # 深证红利 (399324) - 1只
    "sz159905": "399324",
    # 上证红利 (000015) - 1只
    "sh510880": "000015",
    # 中证800 (000906) - 1只
    "sz159720": "000906",
    # 深证100 (399004) - 1只
    "sz159708": "399004",
    # 上证180 (000010) - 1只
    "sh510180": "000010",
    # 中证100 (000903) - 1只
    "sh512600": "000903",
    # 上证380 (000009) - 暂无直接跟踪ETF，保留占位
    # 中证90/中证A100 LOF → 映射到沪深300
    "sz161816": "000300", "sz162509": "000300", "sz164401": "000300", "sz164508": "000300",
}

BROAD_IDX_NAME_MAP = [
    ("沪深300", "000300"), ("中证500", "000905"), ("中证1000", "000852"),
    ("上证50", "000016"), ("创业板50", "399673"), ("创业板指", "399005"),
    ("科创50", "000688"), ("深证红利", "399324"), ("上证红利", "000015"),
    ("中证800", "000906"), ("深证100", "399004"), ("上证180", "000010"),
    ("中证100", "000903"),
]

# ============================================================================
# ETF名称关键词 → 申万行业
# ============================================================================
ETF_NAME_KW_MAP = {
    # ===== v3.0 申万一级行业 (sw_index_first_info 官方31行业) =====
    # --- 801010 农林牧渔 ---
    "农林牧渔": "801010", "种植业": "801010", "农业": "801010", "养殖": "801010", "种子": "801010",
    # --- 801950 煤炭 (v3.0从801020拆出) ---
    "煤炭": "801950", "采掘": "801950",
    # --- 801960 石油石化 (v3.0从801020拆出) ---
    "油气": "801960", "石油": "801960", "天然气": "801960", "石化": "801960",
    # --- 801030 基础化工 ---
    "化工": "801030", "化学": "801030", "化学制品": "801030", "农化": "801030", "精细化工": "801030",
    "原材料": "801030", "加工": "801030",
    # --- 801040 钢铁 ---
    "钢铁": "801040", "普钢": "801040", "特钢": "801040", "周期": "801040",
    # --- 801050 有色金属 ---
    "有色": "801050", "稀土": "801050", "能源金属": "801050", "贵金属": "801050", "工业金属": "801050",
    # --- 801080 电子 ---
    "电子": "801080", "半导体": "801080", "芯片": "801080",
    "光电子": "801080", "消费电子": "801080", "元件": "801080", "PCB": "801080", "LED": "801080",
    "成长": "801080",
    # --- 801110 家用电器 ---
    "家电": "801110", "电器": "801110",
    # --- 801120 食品饮料 ---
    "食品": "801120", "白酒": "801120", "饮料": "801120", "酒": "801120", "啤酒": "801120", "乳业": "801120",
    "消费品": "801120", "必选消费": "801120",
    # --- 801130 纺织服饰 ---
    "纺织": "801130", "服装": "801130", "家纺": "801130",
    # --- 801140 轻工制造 ---
    "轻工": "801140", "造纸": "801140", "包装": "801140", "家具": "801140",
    # --- 801150 医药生物 ---
    "医药": "801150", "医疗": "801150", "生物": "801150", "中药": "801150",
    "医疗器械": "801150", "CXO": "801150", "制药": "801150", "疫苗": "801150",
    # --- 801160 公用事业 ---
    "电力": "801160", "公用事业": "801160", "燃气": "801160",
    # --- 801970 环保 (v3.0新增) ---
    "环保": "801970", "水务": "801970", "环境治理": "801970", "绿化": "801970", "环保LOF": "801970",
    # --- 801170 交通运输 ---
    "交通": "801170", "航运": "801170", "航空": "801170",
    "物流": "801170", "港口": "801170", "铁路": "801170", "高速": "801170",
    "高铁": "801170", "铁路基金": "801170",
    # --- 801180 房地产 ---
    "房地产": "801180", "地产": "801180", "园区": "801180",
    # --- 801200 商贸零售 ---
    "贸易": "801200", "零售": "801200", "商业": "801200", "超市": "801200", "可选消费": "801200",
    # --- 801210 社会服务 ---
    "旅游": "801210", "酒店": "801210", "休闲": "801210", "景区": "801210",
    "教育": "801210", "体育": "801210",
    # --- 801710 建筑材料 ---
    "建材": "801710", "建筑材料": "801710", "水泥": "801710", "玻璃": "801710",
    # --- 801720 建筑装饰 (v3.0新增) ---
    "建筑装饰": "801720", "建筑": "801720", "基建": "801720", "工程": "801720", "钢结构": "801720",
    "一带": "801720", "大湾区": "801720",
    # --- 801730 电力设备 ---
    "电气设备": "801730", "电气": "801730", "光伏": "801730", "风电": "801730",
    "电网": "801730", "新能源": "801730", "储能": "801730", "锂电": "801730", "氢电": "801730",
    "低碳": "801730", "新能": "801730",
    # --- 801740 国防军工 ---
    "国防": "801740", "军工": "801740", "航天": "801740",
    "军工装备": "801740", "军工电子": "801740", "卫星导航": "801740",
    # --- 801750 计算机/科创 ---
    "计算机": "801750", "软件": "801750", "IT": "801750",
    "互联网": "801750", "电商": "801750", "云计算": "801750", "大数据": "801750", "AI": "801750",
    "人工智能": "801750", "信息安全": "801750", "国产软件": "801750",
    "TMT": "801750", "科技": "801750", "中概": "801750", "互联": "801750",
    "网络安全": "801750",
    "科创": "801750", "科创板": "801750", "科创50": "801750", "创业板": "801750",
    "纳斯达克": "801750", "标普信息": "801750", "美国": "801750",
    # --- 801760 传媒 ---
    "传媒": "801760", "游戏": "801760", "影视": "801760", "出版": "801760", "营销": "801760",
    # --- 801770 通信 ---
    "通信": "801770", "通信设备": "801770", "5G": "801770", "光通信": "801770",
    # --- 801780 银行 ---
    "银行": "801780", "农商行": "801780", "城商行": "801780", "港银": "801780", "香港银行": "801780",
    # --- 801790 非银金融 ---
    "保险": "801790", "险企": "801790", "险资": "801790",
    "证券": "801790", "券商": "801790", "投行": "801790", "多元金融": "801790", "非银金融": "801790",
    "金融": "801790",
    # --- 801880 汽车 (v3.0新增) ---
    "汽车整车": "801880", "汽车": "801880", "汽车零部件": "801880", "新能源车": "801880",
    # --- 801890 机械设备 (v3.0新增) ---
    "机械设备": "801890", "机械": "801890", "工程机械": "801890", "机床": "801890", "制造": "801890",
    "工业": "801890",
    # --- 801980 美容护理 (v3.0新增) ---
    "美容": "801980", "化妆品": "801980", "护肤": "801980",
    # --- 801230 综合 (无特定行业关键词，留空) ---
    # --- 模糊/兜底映射 ---
    "家居": "801140",
    "能源": "801960",
    # --- 宽基数字简写（已禁用跨行业误匹配；仅作last resort模糊匹配）---
    # "300": "801120", "500": "801050",
}

SW_CODE_TO_NAME = {
    # v3.0: 申万官方31行业（sw_index_first_info）
    "801010": "农林牧渔", "801030": "基础化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商贸零售",
    "801210": "社会服务", "801230": "综合", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "银行", "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备", "801950": "煤炭", "801960": "石油石化",
    "801970": "环保", "801980": "美容护理",
}

# ============================================================================
# ETF名称关键词 → 国证行业(cninfo) - 第三数据源
# ============================================================================
CNINFO_KW_MAP = {
    # 一级行业 (C01-C11)
    "能源": "C01", "煤炭": "C010103", "石油": "C010102", "天然气": "C010102",
    "原材料": "C02", "化工": "C0201", "化学": "C0201", "有色": "C0202", "稀土": "C0202",
    "工业": "C03", "机械": "C0301", "制造": "C0301", "基建": "C0302", "建筑": "C0302",
    "运输": "C0303", "航运": "C0303", "航空": "C0303", "物流": "C0303", "铁路": "C0303",
    "可选消费": "C04", "汽车": "C0401", "家电": "C0402", "家居": "C0402",
    "纺织": "C0403", "服装": "C0403", "旅游": "C0404", "酒店": "C0404",
    "传媒": "C0405", "游戏": "C0405", "影视": "C0405",
    "零售": "C0406", "商业": "C0406", "超市": "C0406",
    "主要消费": "C05", "食品": "C0503", "白酒": "C0503", "饮料": "C0503", "酒": "C0503",
    "农业": "C0502", "养殖": "C0502", "种子": "C0502",
    "医药卫生": "C06", "医药": "C0602", "医疗": "C0601", "生物": "C0603", "中药": "C0602",
    "医疗器械": "C0601", "制药": "C0602", "疫苗": "C0602",
    "金融": "C07", "银行": "C0701", "保险": "C0702", "券商": "C0703", "证券": "C0703",
    "信息技术": "C08", "计算机": "C0801", "软件": "C0801", "AI": "C0801",
    "云计算": "C0801", "大数据": "C0801", "信息安全": "C0801",
    "电子": "C0802", "半导体": "C0803", "芯片": "C0803", "消费电子": "C0802",
    "电信": "C09", "通信": "C0902", "5G": "C0902",
    "公用事业": "C10", "电力": "C1001", "燃气": "C1001", "环保": "C1001", "水务": "C1001",
    "房地产": "C11", "地产": "C11", "园区": "C11",
    # 三级行业精细映射
    "钢铁": "C0202", "水泥": "C0202", "玻璃": "C0202",
    "电气设备": "C0301", "光伏": "C0301", "风电": "C0301", "新能源": "C0301",
    "储能": "C0301", "锂电": "C0301",
    "PCB": "C0802", "LED": "C0802", "光电子": "C0802",
    "CXO": "C0602",
    "国防": "C0301", "军工": "C0301", "航天": "C0301", "军工电子": "C0301",
    # 精确行业关键词
    "科技": "C08", "TMT": "C08", "信息技术": "C08",
    "美国消费": "C04", "消费ETF": "C04", "消费龙头": "C04", "南方消费": "C04",
    "纯债": "C03", "强债": "C03", "信用债": "C03", "债券": "C03", "债": "C03",
    "商品": "C01", "大宗商品": "C01",
    "港股": "C07", "港股通": "C07",
    "纳斯达克": "C08", "标普": "C08", "美国": "C08", "海外": "C08",
    "REIT": "C07",
    # 主动LOF/定开基金默认映射（PE=27.7的工业行业，仅作参考）
    # 注：这些基金本质无行业归属，此PE仅供参考，不应作为筛选依据
    "LOF": "C03", "定开": "C03", "FOF": "C03",
    "配置": "C03", "优选": "C03", "精选": "C03", "优势": "C03",
    # 主动管理基金特征词（无明显行业标识）
    "瑞虹": "C03", "睿阳": "C03", "明择": "C03", "瑞享": "C03",
    "瑞利": "C03", "瑞丰": "C03", "瑞盛": "C03", "瑞泰": "C03",
}


def estimate_pe_percentile(pe: Optional[float]) -> Optional[float]:
    """估算PE历史分位（适用于宽基指数PE，非行业PE）
    
    对于行业ETF（申万/cninfo来源），PE绝对值与宽基指数不可比：
    - 申万银行 PE=2.43 → 低估（银行业PE通常5-10）
    - 申万非银金融 PE=1.94 → 低估
    - cninfo能源 PE=14.94 → 合理
    
    此函数仅用于无法获取真实历史分位时的近似估算。
    对于行业ETF，建议直接使用PE绝对值判断，而非估算分位。
    """
    if pe is None or pe <= 0:
        return None
    # 宽基指数PE范围估算（适用于沪深300/中证500等）
    # PE=10以下：历史极低位，10-15：低位，15-25：正常，25-35：高位，35+：极高
    if pe < 10.0: return 10.0   # 历史极低（深证红利PE≈18.6在20%分位）
    elif pe < 15.0: return 20.0
    elif pe < 20.0: return 35.0
    elif pe < 25.0: return 50.0
    elif pe < 30.0: return 65.0
    elif pe < 40.0: return 78.0
    else: return 90.0


def estimate_pb_percentile(pb: Optional[float]) -> Optional[float]:
    if pb is None or pb <= 0:
        return None
    if pb < 1.0: return 10.0
    elif pb < 2.0: return 25.0
    elif pb < 3.0: return 45.0
    elif pb < 4.0: return 60.0
    elif pb < 6.0: return 75.0
    else: return 90.0


class SinaETFSpotFetcher:
    """新浪历史K线20日均成交额获取（v6.3）
    
    通过akshare fund_etf_hist_sina获取历史K线，计算20日均成交额。
    hist_sina对标准ETF和LOF基金均有效（已验证）。
    兜底：Sina实时成交额（当hist_sina失败时）。
    """

    def __init__(self):
        self._cache: Dict[str, float] = {}
        self._loaded = False
        self._hist_cache: Dict[str, float] = {}  # 20日均成交额缓存

    def load(self):
        """"预加载新浪实时成交额（兜底用）"""
        if self._loaded:
            return
        try:
            df = ak.fund_etf_category_sina()
            for _, row in df.iterrows():
                code = row['代码'].lower()
                amt = float(row.get('成交额', 0) or 0)
                self._cache[code] = amt
            self._loaded = True
            logger.info(f"  兜底实时成交额加载: {len(self._cache)}只ETF")
        except Exception as e:
            logger.warning(f"  兜底实时成交额加载失败: {e}")
            self._loaded = True

    def _get_20d_avg(self, code: str) -> Optional[float]:
        """获取单只ETF历史K线20日均成交额（从缓存）"""
        sym = code.lower()
        if sym in self._hist_cache:
            return self._hist_cache[sym]
        try:
            df = ak.fund_etf_hist_sina(symbol=sym)
            recent = df.sort_values('date').tail(20)
            avg = recent['amount'].astype(float).mean()
            self._hist_cache[sym] = round(avg, 2)
            return self._hist_cache[sym]
        except Exception as e:
            # 兜底：返回实时成交额
            amt = self._cache.get(sym)
            if amt and amt > 0:
                self._hist_cache[sym] = amt
                return amt
            self._hist_cache[sym] = None
            return None

    def get_amount(self, code: str, existing_amount: float = None) -> Optional[float]:
        """获取20日均成交额（主入口）
        v6.5: 优先使用已有的成交额数据（来自采集器），避免重复API调用
        """
        if not self._loaded:
            self.load()
        # v6.5: 如果record已有成交额（采集器提供的），直接用它
        if existing_amount and existing_amount > 0:
            self._hist_cache[code.lower()] = round(existing_amount, 2)
            return round(existing_amount, 2)
        return self._get_20d_avg(code)


class ETFValuationEnricherV5:
    def __init__(self):
        # v2.1: 宽基分位(index_percentiles_latest.json)已含申万行业数据
        self.idx_data = self._load_json(PERCENTILE_FILE, {})  # 含 indices{} + sw_industries{}
        self.sw_data = self._load_json(SW_FILE, {})            # 保留备用（原始格式）
        self.cninfo_data = self._load_json(CNINFO_FILE, {})
        self.sina_fetcher = SinaETFSpotFetcher()
        self.stats = {"total": 0, "idx_covered": 0, "sw_covered": 0,
                      "cninfo_covered": 0, "unavailable": 0, "amount_ok": 0}
        # v6.4: 检查申万数据新鲜度
        self._check_sw_freshness()

    def _check_sw_freshness(self):
        """检查申万行业数据新鲜度，超过3天发出警告"""
        if not self.sw_data:
            logger.warning("⚠️ 申万行业估值文件不存在或为空，请先运行 sw_industry_valuation.py")
            return
        meta = self.sw_data.get('meta', {})
        gen_at = meta.get('generated_at', '')
        if not gen_at:
            logger.warning("⚠️ 申万行业估值文件缺少 generated_at 字段")
            return
        try:
            from datetime import datetime as _dt
            gen_time = _dt.fromisoformat(gen_at)
            now = _dt.now()
            age_days = (now - gen_time).days
            if age_days > 3:
                logger.warning(f"⚠️ 申万行业数据已过期 {age_days} 天（生成于 {gen_at[:10]}），建议重新运行 sw_industry_valuation.py")
            else:
                logger.info(f"✅ 申万行业数据新鲜（生成于 {gen_at[:10]}，{age_days}天前）")
        except Exception as e:
            logger.warning(f"⚠️ 无法解析申万数据时间: {e}")

    def _load_json(self, path: Path, default):
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return default

    # 宽基指数 → 申万行业近似映射（乐咕API失败时的降级方案）
    BROAD_TO_SW_FALLBACK = {
        "000300": "801010",  # 沪深300 → 农林牧渔大类加权，用全市场综合
        "000905": "801010",  # 中证500
        "000016": "801780",  # 上证50 → 银行(大金融)
        "000852": "801080",  # 中证1000 → 电子(中小成长)
        "399673": "801080",  # 创业板50 → 电子
        "399005": "801080",  # 创业板指 → 电子
        "000688": "801080",  # 科创50 → 电子
        "399324": "801120",  # 深证红利 → 食品饮料
        "000015": "801120",  # 上证红利 → 食品饮料
        "000906": "801010",  # 中证800
        "399004": "801080",  # 深证100
        "000010": "801780",  # 上证180 → 银行
        "000903": "801010",  # 中证100
    }
    # 更精确：宽基指数对应综合市场（用全市场PE中位数近似）
    BROAD_PE_APPROX = {
        "000300": {"pe": 14.0, "pb": 1.4},  # 沪深300 近似PE/PB
        "000905": {"pe": 22.0, "pb": 1.8},  # 中证500
        "000016": {"pe": 10.5, "pb": 1.1},  # 上证50
        "000852": {"pe": 30.0, "pb": 2.2},  # 中证1000
        "399673": {"pe": 38.0, "pb": 3.5},  # 创业板50
        "399005": {"pe": 35.0, "pb": 3.2},  # 创业板指
        "000688": {"pe": 50.0, "pb": 4.0},  # 科创50
        "399324": {"pe": 18.0, "pb": 3.0},  # 深证红利
        "000015": {"pe": 10.0, "pb": 1.2},  # 上证红利
        "000906": {"pe": 16.0, "pb": 1.5},  # 中证800
        "399004": {"pe": 25.0, "pb": 2.5},  # 深证100
        "000010": {"pe": 11.0, "pb": 1.2},  # 上证180
        "000903": {"pe": 15.0, "pb": 1.4},  # 中证100
    }

    # 中证指数 → 申万行业 PB分位降级映射
    CSINDEX_TO_SW_PB = {
        "000300": "801780",  # 沪深300 → 银行(大金融代表)
        "000905": "801120",  # 中证500 → 食品饮料
        "000016": "801780",  # 上证50 → 银行
        "000852": "801080",  # 中证1000 → 电子
        "000906": "801780",  # 中证800 → 银行
        "000010": "801780",  # 上证180 → 银行
        "000903": "801010",  # 中证100 → 农林牧渔(综合)
        "000015": "801120",  # 上证红利 → 食品饮料(红利多消费)
        "000688": "801080",  # 科创50 → 电子
    }

    def _get_idx_data(self, code: str, name: str) -> Optional[Dict]:
        idx_code = BROAD_IDX_CODE_MAP.get(code.lower())
        # ETF代码不在映射表时，通过name精确匹配指数名
        if not idx_code:
            for kw, ic in BROAD_IDX_NAME_MAP:
                if kw in name:
                    idx_code = ic; break
        if not idx_code:
            return None
        idx = self.idx_data.get("indices", {}).get(idx_code)

        # 主路径：中证指数官方真实PE分位 (v6.7: 2010至今16.5年)
        if idx and idx.get("is_real_pe") and "csindex" in (idx.get("source") or "").lower():
            pe_val = idx.get("pe")
            pe_pct = idx.get("pe_percentile")
            data_years = round(idx.get("pe_count", 0) / 252, 1)
            source_tag = f"中证指数官方(6年{idx.get('pe_count',0)}条)"

            # PB分位：中证指数不提供PB，用申万行业PB分位近似
            sw_code = self.CSINDEX_TO_SW_PB.get(idx_code)
            sw_ind = self.idx_data.get("sw_industries", {}).get(sw_code) if sw_code else None
            pb_val = sw_ind.get("pb") if sw_ind else None
            pb_pct = sw_ind.get("pb_percentile") if sw_ind else None

            return {
                "pe": pe_val, "pb": pb_val,
                "pe_percentile": pe_pct,
                "pb_percentile": pb_pct,
                "index_code": idx_code, "index_name": idx.get("name"),
                "source": source_tag,
                "data_years": data_years,
                "percentile_real_flag": True,
                "pe_real": True, "pb_real": False,
                "pe_note": "6年真实分位(2020至今)",
                "pb_note": f"申万{sw_ind.get('name','')}行业PB分位近似" if sw_ind else "无PB数据",
            }

        # 次选：乐咕真实分位(如果csindex没数据但乐咕有)
        if idx and idx.get("is_real_pe"):
            return {
                "pe": idx.get("pe"), "pb": idx.get("pb"),
                "pe_percentile": idx.get("pe_percentile"),
                "pb_percentile": idx.get("pb_percentile"),
                "index_code": idx_code, "index_name": idx.get("name"),
                "source": "乐咕乐股",
                "data_years": round(idx.get("pe_count", 0) / 252, 1),
            }

        # v6.5降级路径：无真实分位时，用申万行业数据+估算分位
        idx_name = idx.get("name", "") if idx else ""
        approx = self.BROAD_PE_APPROX.get(idx_code)
        sw_fallback_code = self.BROAD_TO_SW_FALLBACK.get(idx_code)

        sw_ind = self.idx_data.get("sw_industries", {}).get(sw_fallback_code) if sw_fallback_code else None
        pe_pct = sw_ind.get("pe_percentile") if sw_ind else None
        pb_pct = sw_ind.get("pb_percentile") if sw_ind else None

        idx_name_map = {ic: kw for kw, ic in BROAD_IDX_NAME_MAP}
        idx_name = idx_name_map.get(idx_code, idx_name or idx_code)

        if approx:
            pe_val = approx["pe"]
            pb_val = approx["pb"]
            if not pe_pct and pe_val:
                pe_pct = estimate_pe_percentile(pe_val)
            if not pb_pct and pb_val:
                pb_pct = estimate_pb_percentile(pb_val)
            return {
                "pe": pe_val, "pb": pb_val,
                "pe_percentile": pe_pct,
                "pb_percentile": pb_pct,
                "index_code": idx_code, "index_name": idx_name,
                "source": f"降级(估算PE+申万分位)",
                "data_years": 0,
                "percentile_real_flag": False,
            }

        return None

    def _detect_cninfo_industry(self, name: str) -> Optional[Dict]:
        """读取CNINFO行业分类：
        1. 过滤掉"LOF/FOF/定开"等基金类型关键词
        2. 用真实行业关键词匹配，按长度排序取最精确
        3. 若无任何行业词匹配 → 标记为主动管理LOF（无PE）
        """
        FUND_TYPE_KWS = {"LOF", "FOF", "定开", "优选", "精选", "配置",
                         "量化", "强债", "纯债", "信用债", "债券", "债",
                         "商品", "海外", "美国", "标普", "港股", "港股通",
                         "主要消费", "REIT", "ETF", "绝对", "多策略"}
        matched = []
        has_fund_kw = False
        for kw, code in CNINFO_KW_MAP.items():
            if kw in name:
                if kw in FUND_TYPE_KWS:
                    has_fund_kw = True
                    continue  # 跳过基金类型词
                ind = self.cninfo_data.get(code)
                if ind and "error" not in ind:
                    matched.append((len(kw), kw, code, ind))

        if not matched:
            if has_fund_kw:
                # 只有基金类型词，无真实行业词 → 主动管理LOF（无PE数据）
                return {"code": "LOF", "name": "主动管理LOF", "pe": None}
            return None
        # 关键词最长=最精确优先；同长度时SW行业优先于GICS
        matched.sort(key=lambda x: (-x[0], SW_CODE_TO_NAME.get(x[2], '') == ''))
        kw, code, ind = matched[0][1], matched[0][2], matched[0][3]
        return {"code": code, "name": ind.get("name", code), "pe": ind.get("pe")}

    def _get_sw_data(self, name: str) -> Optional[Dict]:
        sw_code = None
        match_source = None  # "sw" | "cninfo"

        # 优先：申万行业关键词（精准行业分类）
        for kw, sc in ETF_NAME_KW_MAP.items():
            if kw in name:
                # 排除宽基指数名称中的误匹配关键词
                if kw in ("300", "500", "1000", "50", "688"):
                    if any(b in name for b in ["沪深300","中证500","中证1000","上证50","深证100",
                                                "创业板指","科创50","深证红利","中证800"]):
                        continue
                sw_code = sc; match_source = "sw"; break

        # 兜底：CNINFO行业关键词（扩展覆盖，尤其是LOF基金）
        if not sw_code:
            # 读取cninfo行业分类（扁平dict格式）
            cninfo_industry = self._detect_cninfo_industry(name)
            if cninfo_industry:
                sw_code = cninfo_industry["code"]
                sw_name = cninfo_industry["name"]
                match_source = "cninfo"
                return {
                    "pe": None, "pb": None,
                    "pe_percentile": None, "pb_percentile": None,
                    "sw_code": sw_code,
                    "sw_name": sw_name,
                    "source": f"CNINFO-{sw_name}",
                    "cninfo_pe": cninfo_industry.get("pe"),
                    "cninfo_name": sw_name,
                }

        if not sw_code:
            return None
        # 优先从 index_percentiles_latest.json 读（含确定性分位）
        ind = self.idx_data.get("sw_industries", {}).get(sw_code)
        if not ind:
            # 兜底：读 sw_industry_valuation_latest.json（原始数据）
            ind = self.sw_data.get("industries", {}).get(sw_code)
        else:
            # v6.4: 从sw_industry_valuation_latest.json补充component_count（percentiles文件不含此字段）
            sw_ind = self.sw_data.get("industries", {}).get(sw_code)
            if sw_ind and "component_count" not in ind and "component_count" in sw_ind:
                ind = dict(ind)  # 复制避免修改原数据
                ind["component_count"] = sw_ind["component_count"]
        # CNINFO命中（match_source=cninfo）时，从cninfo_data读PE（扁平dict）
        cninfo_pe = None
        if match_source == "cninfo":
            cninfo_val = self.cninfo_data.get(sw_code)
            if cninfo_val and "error" not in cninfo_val:
                cninfo_pe = cninfo_val.get("pe")
        if not ind or "error" in ind:
            return None
        pe_val = ind.get("pe") or ind.get("pe_ttm")
        pb_val = ind.get("pb")
        if pe_val is not None and pe_val <= 0:
            return None
        # v6.1: 分位来源优先级：真实分位 > 申万确定性分位 > CNINFO行业分位 > 通用估算
        pe_pct = ind.get("pe_percentile") if ind else None
        pb_pct = ind.get("pb_percentile") if ind else None

        # CNINFO命中时：用cninfo的PE，申万分位表估算分位（CNINFO无历史分位）
        if match_source == "cninfo" and cninfo_pe and cninfo_pe > 0:
            pe_val = cninfo_pe
            # 用申万百分位表估算（同一行业大类）
            if not pe_pct:
                pe_pct = estimate_pe_percentile(cninfo_pe)
        elif not pe_val and cninfo_pe and cninfo_pe > 0:
            pe_val = cninfo_pe
            pe_pct = pe_pct or estimate_pe_percentile(cninfo_pe)

        return {
            "pe": pe_val, "pb": pb_val,
            "pe_percentile": pe_pct, "pb_percentile": pb_pct,
            "sw_code": sw_code,
            "sw_name": ind.get("name") if ind else SW_CODE_TO_NAME.get(sw_code, sw_code),
            "component_count": ind.get("component_count") if ind else None,
            "source": "申万官方估值+历史分位",
        }

    def _get_cninfo_data(self, name: str) -> Optional[Dict]:
        """从巨潮资讯国证行业获取PE数据（第三数据源）"""
        # 按关键词长度降序：最长关键词 = 最精确行业（避免"LOF"抢占"证券LOF"）
        matched = []
        for kw, cc in CNINFO_KW_MAP.items():
            if kw in name:
                matched.append((len(kw), kw, cc))
        if not matched:
            return None
        # 关键词最长优先；长度相同时用SW_CODE_TO_NAME里有的（行业名更精确）
        matched.sort(key=lambda x: (-x[0], SW_CODE_TO_NAME.get(x[2], '') != ''))
        cninfo_code = matched[0][2]
        # 优先用精确行业，找不到用上级行业（三级→二级→一级）
        for level_pref in [cninfo_code, cninfo_code[:4], cninfo_code[:3], cninfo_code[:2]]:
            ind = self.cninfo_data.get(level_pref)
            if ind and ind.get('pe') and ind['pe'] > 0:
                return {
                    "pe": ind['pe'],
                    "pb": None,
                    "cninfo_code": level_pref,
                    "cninfo_name": ind['name'],
                    "source": "巨潮资讯",
                }
        return None

    def enrich(self, record: Dict) -> Dict:
        code = record.get("code", "")
        name = record.get("name", "")

        idx_data = self._get_idx_data(code, name)
        sw_data = self._get_sw_data(name) if not idx_data else None
        cninfo_data = self._get_cninfo_data(name) if not idx_data and not sw_data else None

        if idx_data:
            pe = idx_data["pe"]; pb = idx_data.get("pb")
            pe_pct = idx_data["pe_percentile"]; pb_pct = idx_data.get("pb_percentile")
            source = idx_data.get("source", "指数") + f"-{idx_data['index_name']}"
            percentile_real = idx_data.get("percentile_real_flag", True)
            # v6.6: 标记PB分位是否真实（csindex不提供PB，申万近似的不纳入筛选）
            pb_real = idx_data.get("pb_real", True)  # 默认True(兼容旧数据)
            if not pb_real and pb_pct is not None:
                # PB分位是申万行业近似，标记为非真实，筛选器会忽略
                pb_pct = None  # 不使用不可靠的PB分位
                pb = None
            self.stats["idx_covered"] += 1
        elif sw_data:
            sw_src = sw_data.get("source", "")
            is_sw_match = "申万" in sw_src
            # CNINFO关键词命中时：PE在cninfo_pe字段（pe字段为None）
            if is_sw_match:
                pe = sw_data["pe"]; pb = sw_data["pb"]
                pe_pct = sw_data.get("pe_percentile") or estimate_pe_percentile(pe)
                pb_pct = sw_data.get("pb_percentile") or estimate_pb_percentile(pb)
                source = f"申万-{sw_data['sw_name']}({sw_data.get('component_count', '?')}股)"
                percentile_real = False
                self.stats["sw_covered"] += 1
            else:
                # CNINFO关键词命中：cninfo_pe=None表示主动管理LOF（无行业PE）
                pe = sw_data.get("cninfo_pe") or sw_data.get("pe")
                pb = sw_data.get("pb")
                pe_pct = sw_data.get("pe_percentile") if sw_data.get("pe_percentile") is not None else (estimate_pe_percentile(pe) if pe else None)
                pb_pct = sw_data.get("pb_percentile") or estimate_pb_percentile(pb) if pb else None
                source = sw_src
                percentile_real = False
                self.stats["cninfo_covered"] += 1
        elif cninfo_data:
            pe = cninfo_data["pe"]; pb = cninfo_data.get("pb")
            pe_pct = estimate_pe_percentile(pe)
            pb_pct = estimate_pb_percentile(pb) if pb else None
            cninfo_name = cninfo_data.get("cninfo_name") or cninfo_data.get("name", "未知")
            source = f"巨潮资讯-{cninfo_name}"
            percentile_real = False
            self.stats["cninfo_covered"] += 1
        else:
            pe = pb = pe_pct = pb_pct = None
            source = "unavailable"
            percentile_real = False
            self.stats["unavailable"] += 1

        # -------------------- PEG计算（ROE法）---------------------
        # PEG = PE / 可持续增速
        # 可持续增速 ≈ ROE × (1 - 分红率)，ROE ≈ PB/PE
        # 分红率默认30%，留存率=70%
        peg = None
        peg_source = None
        if pe and pb and pb > 0 and pe > 0:
            roe_estimate = (pb / pe) * 100  # ROE百分比
            retention_ratio = 0.7
            growth_rate = roe_estimate * retention_ratio
            if growth_rate >= 0.5:  # 有效增速门槛
                peg = round(pe / growth_rate, 2)
                peg_source = "ROE法(留存70%)"

        avg_amount = self.sina_fetcher.get_amount(code, existing_amount=record.get('amount'))
        if avg_amount:
            self.stats["amount_ok"] += 1

        if pe and pe > 0:
            valuation_signal = "低估" if pe <= 15 else "高估" if pe >= 35 else "合理"
        elif pe is not None and pe < 0:
            valuation_signal = "亏损"
        else:
            valuation_signal = "数据不可用"

        if pe_pct is not None:
            growth_signal = "历史低位" if pe_pct <= 30 else "历史高位" if pe_pct >= 70 else "历史中位"
        else:
            growth_signal = "无历史数据"

        if avg_amount:
            liq_signal = "充裕" if avg_amount >= 500_000_000 else "一般" if avg_amount >= 100_000_000 else "偏弱"
            liq_level = "高" if avg_amount >= 500_000_000 else "中" if avg_amount >= 100_000_000 else "低"
        else:
            liq_signal = "未知"; liq_level = "无数据"

        quality = "real" if percentile_real and avg_amount else "partial" if (percentile_real or avg_amount) else "unavailable"

        # NaN防护：将NaN转为None，避免json.dump写出非法JSON
        if isinstance(pe, float) and math.isnan(pe): pe = None
        if isinstance(pb, float) and math.isnan(pb): pb = None
        if isinstance(pe_pct, float) and math.isnan(pe_pct): pe_pct = None
        if isinstance(pb_pct, float) and math.isnan(pb_pct): pb_pct = None

        return {
            **record,
            "pe_ttm": pe, "pb": pb,
            "pe_percentile": pe_pct, "pb_percentile": pb_pct,
            "percentile_real_flag": percentile_real,
            "pe_pb_source": source,
            "avg_amount_20d": avg_amount,
            "valuation_signal": valuation_signal,
            "peg": peg,
            "peg_source": peg_source,
            "growth_signal": growth_signal,
            "liquidity_level": liq_level,
            "liquidity_signal": liq_signal,
            "data_quality_flag": quality,
        }

    def run(self) -> Dict:
        logger.info("=" * 70)
        logger.info("ETF估值补全 v6.6 - csindex官方PE+申万行业+实时成交额")
        logger.info("数据源: 中证指数官方(9指数) + 乐咕(备用) + 申万行业(31行业) + 实时成交额")
        logger.info("=" * 70)
        t0 = datetime.now()

        # 预加载成交额（一次请求获取全部）
        self.sina_fetcher.load()

        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            records = json.load(f).get("data", [])
        self.stats["total"] = len(records)
        logger.info(f"加载 {len(records)} 条ETF记录")

        enriched = []
        for i, rec in enumerate(records, 1):
            if i % 50 == 0:
                logger.info(f"  进度: {i}/{len(records)}")
            enriched.append(self.enrich(rec))
            time.sleep(0.05)

        t1 = datetime.now()
        dur = (t1 - t0).total_seconds()
        total = self.stats['total']
        cov = (self.stats['idx_covered'] + self.stats['sw_covered']) / max(total, 1) * 100

        output = {
            "meta": {
                "generated_at": t1.isoformat(),
                "duration_seconds": round(dur, 1),
                "version": "v6.2-dual-source",
                "data_sources": {
                    "乐咕乐股": {
                        "description": "12个宽基指数真实历史PE/PB分位",
                        "indices": list(self.idx_data.get("indices", {}).keys()),
                        "data_years": "11~21年",
                        "api": "akshare: stock_index_pe_lg, stock_index_pb_lg",
                    },
                    "申万行业": {
                        "description": "26个申万一级行业加权PE/PB（Top20成分股权重×个股估值）",
                        "api": "akshare: index_component_sw + stock_value_em",
                        "note": "分位为当前值相对排名估算，非严格历史分位",
                    },
                    "新浪20日均成交额": {
                        "description": "新浪历史K线20日均成交额（hist_sina，LOF也有效）",
                        "api": "akshare: fund_etf_hist_sina",
                        "fallback": "fund_etf_category_sina实时成交额",
                    }
                }
            },
            "stats": self.stats,
            "data": enriched,
        }

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, ensure_ascii=False, indent=2, fp=f)

        logger.info("=" * 70)
        logger.info(f"✅ 完成！耗时: {dur:.1f}秒")
        cov = (self.stats['idx_covered'] + self.stats['sw_covered'] + self.stats.get('cninfo_covered',0)) / max(total,1) * 100
        logger.info(f"   宽基指数: {self.stats['idx_covered']} ({self.stats['idx_covered']/max(total,1)*100:.1f}%)")
        logger.info(f"   申万行业: {self.stats['sw_covered']} ({self.stats['sw_covered']/max(total,1)*100:.1f}%)")
        logger.info(f"   巨潮资讯: {self.stats.get('cninfo_covered',0)} ({self.stats.get('cninfo_covered',0)/max(total,1)*100:.1f}%)")
        logger.info(f"   无数据: {self.stats['unavailable']} ({self.stats['unavailable']/max(total,1)*100:.1f}%)")
        logger.info(f"   20日均成交额: {self.stats['amount_ok']} ({self.stats['amount_ok']/max(total,1)*100:.1f}%)")
        logger.info(f"   ✅ 总覆盖率: {cov:.1f}%")
        logger.info("=" * 70)

        return output


def main():
    enricher = ETFValuationEnricherV5()
    result = enricher.run()
    s = result["stats"]
    print("\n" + "=" * 60)
    print("数据源与覆盖率报告")
    print("=" * 60)
    print(f"总ETF数: {s['total']}")
    print(f"宽基指数(乐咕乐股): {s['idx_covered']} ({s['idx_covered']/max(s['total'],1)*100:.1f}%)")
    print(f"申万行业覆盖: {s['sw_covered']} ({s['sw_covered']/max(s['total'],1)*100:.1f}%)")
    print(f"无估值数据: {s['unavailable']} ({s['unavailable']/max(s['total'],1)*100:.1f}%)")
    print(f"✅ 总覆盖率: {(s['idx_covered']+s['sw_covered'])/max(s['total'],1)*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
