#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF_估值数据采集 Agent v3.0
每日自动拉取全市场ETF基础与深度估值数据
支持多数据源回退机制 + 代理检测

v3.0 重大升级：
- 新增标准ETF采集（sh510/512/513/515/516/518/588 + sz159xxx）
- 覆盖从382只LOF扩展到1500+只全市场ETF
- 数据源：新浪LOF实时行情 + 同花顺ETF列表 + 新浪历史K线（标准ETF最新价/成交额）
"""

import akshare as ak
import json
import os
import sys
import socket
import time
from datetime import datetime, timedelta
import logging
import pandas as pd

# ============ 配置区域 ============
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = SCRIPT_DIR  # etf-agent is the workspace root
DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
LOG_DIR = os.path.join(WORKSPACE_DIR, "logs")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "agent_config.json")

# 确保目录存在
for d in [DATA_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

# 配置日志
log_file = os.path.join(LOG_DIR, f"etf_collector_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============ 网络检测 ============
def check_network():
    """检测网络连接状态"""
    try:
        sock = socket.create_connection(("push2.eastmoney.com", 443), timeout=5)
        sock.close()
        return True
    except:
        return False

def get_proxy_settings():
    """获取系统代理设置"""
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
    proxies = {}
    for var in proxy_vars:
        if os.environ.get(var):
            proxies[var.lower()] = os.environ.get(var)
    return proxies

# ============ 数据采集核心类 ============
class ETFDataCollector:
    """ETF数据采集器 v3.0 - 支持全市场ETF(LOF+标准ETF)"""
    
    def __init__(self):
        self.data_sources = ["akshare", "sina", "ths"]
        self.session_stats = {
            "start_time": datetime.now(),
            "records_collected": 0,
            "lof_count": 0,
            "standard_etf_count": 0,
            "errors": [],
            "data_source_used": None
        }
        
        # 检测代理并设置
        self.proxies = get_proxy_settings()
        if self.proxies:
            logger.info(f"检测到系统代理设置: {list(self.proxies.keys())}")
    
    def _clear_proxy_and_call(self, fn, *args, retries=3, **kwargs):
        """清除代理 + 重试机制"""
        old_env = {}
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
        for var in proxy_vars:
            if var in os.environ:
                old_env[var] = os.environ.pop(var)
        try:
            for attempt in range(1, retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt < retries:
                        logger.warning(f"  第{attempt}次失败，重试中... ({str(e)[:50]})")
                        time.sleep(2)
                    else:
                        raise
        finally:
            for var, val in old_env.items():
                os.environ[var] = val

    def get_etf_spot_sina(self):
        """
        主数据源1：新浪财经ETF实时行情 (LOF基金)
        ✅ 稳定：382只LOF基金，含实时价格/涨跌幅/成交额
        ❌ 仅LOF基金，无标准ETF(sh510/sz1599/sh512等)
        """
        try:
            logger.info("[数据源1: 新浪财经] 拉取LOF基金实时行情...")
            df = self._clear_proxy_and_call(ak.fund_etf_category_sina)
            
            column_mapping = {
                '代码': 'code',
                '名称': 'name',
                '最新价': 'price',
                '涨跌额': 'change_amount',
                '涨跌幅': 'change_pct',
                '买入': 'bid',
                '卖出': 'ask',
                '昨收': 'pre_close',
                '今开': 'open',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount'
            }
            available_cols = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=available_cols)
            
            numeric_cols = ['price', 'change_pct', 'change_amount', 'volume', 'amount', 'open', 'high', 'low', 'pre_close']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 标记数据类型
            df['fund_type'] = 'LOF'
            
            logger.info(f"✅ 新浪LOF成功，获取 {len(df)} 只基金")
            self.session_stats["lof_count"] = len(df)
            return df
        except Exception as e:
            error_msg = f"新浪财经LOF行情获取失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.session_stats["errors"].append(error_msg)
            return None

    def get_standard_etf_list_ths(self):
        """
        数据源2：同花顺ETF基金列表
        ✅ 全量1567只ETF代码+名称（含标准ETF）
        ❌ 只有净值数据，无实时价格/成交额
        """
        try:
            logger.info("[数据源2: 同花顺] 拉取全量ETF基金列表...")
            df = self._clear_proxy_and_call(ak.fund_etf_spot_ths)
            logger.info(f"✅ 同花顺ETF列表: {len(df)} 只")
            return df
        except Exception as e:
            error_msg = f"同花顺ETF列表获取失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.session_stats["errors"].append(error_msg)
            return None

    def fetch_standard_etf_latest_data(self, code_list, batch_size=20):
        """
        批量获取标准ETF最新交易数据（通过新浪历史K线）
        用最近一个交易日的数据代替实时行情
        
        Args:
            code_list: [(基金代码, 基金名称), ...] 
            batch_size: 每批数量（用于日志进度）
        
        Returns:
            list of dict: [{code, name, price, change_pct, amount, ...}, ...]
        """
        results = []
        total = len(code_list)
        success = 0
        fail = 0
        
        logger.info(f"[数据源3: 新浪历史K线] 开始获取 {total} 只标准ETF最新交易数据...")
        
        for i, (code, name) in enumerate(code_list):
            # 确定新浪代码前缀
            if code.startswith('15') or code.startswith('16'):
                prefix = 'sz'
            elif code.startswith('51') or code.startswith('56') or code.startswith('58'):
                prefix = 'sh'
            else:
                prefix = 'sz'  # 默认深市
            
            sym = f"{prefix}{code}"
            
            try:
                df = self._clear_proxy_and_call(ak.fund_etf_hist_sina, symbol=sym, retries=1)
                if df is not None and len(df) > 0:
                    latest = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else latest
                    
                    close = float(latest['close'])
                    prev_close = float(prev['close'])
                    change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
                    change_amount = round(close - prev_close, 3) if prev_close > 0 else 0
                    
                    results.append({
                        'code': sym,
                        'name': name,
                        'price': close,
                        'change_pct': change_pct,
                        'change_amount': change_amount,
                        'volume': float(latest.get('volume', 0)),
                        'amount': float(latest.get('amount', 0)),
                        'pre_close': prev_close,
                        'open': float(latest.get('open', close)),
                        'high': float(latest.get('high', close)),
                        'low': float(latest.get('low', close)),
                        'fund_type': '标准ETF',
                    })
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                if fail <= 5:  # 只打印前5个失败
                    logger.warning(f"  {sym}({name}) 获取失败: {str(e)[:50]}")
            
            # 进度日志
            if (i + 1) % 100 == 0:
                logger.info(f"  进度: {i+1}/{total} (成功{success}, 失败{fail})")
            
            # 限流：每5只休息0.2秒
            if (i + 1) % 5 == 0:
                time.sleep(0.15)
        
        logger.info(f"✅ 标准ETF数据获取完成: 成功{success}, 失败{fail}")
        self.session_stats["standard_etf_count"] = success
        return results

    def get_etf_spot_em(self):
        """
        备用数据源：东方财富ETF实时行情 (可能不稳定)
        """
        try:
            logger.info("[备用数据源: 东方财富] 尝试拉取ETF实时行情...")
            df = self._clear_proxy_and_call(ak.fund_etf_spot_em, retries=1)
            
            column_mapping = {
                '代码': 'code', '名称': 'name', '最新价': 'price',
                '涨跌幅': 'change_pct', '涨跌额': 'change_amount',
                '成交量': 'volume', '成交额': 'amount',
                '开盘价': 'open', '最高价': 'high', '最低价': 'low',
                '昨收': 'pre_close', '换手率': 'turnover_rate',
                '市盈率-动态': 'pe_ttm', '市净率': 'pb',
            }
            available_cols = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=available_cols)
            
            numeric_cols = ['price', 'change_pct', 'change_amount', 'volume', 'amount',
                          'open', 'high', 'low', 'pre_close', 'pe_ttm', 'pb']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            logger.info(f"✅ 东方财富成功，获取 {len(df)} 只ETF行情数据")
            self.session_stats["data_source_used"] = "em_fund_etf_spot"
            self.session_stats["records_collected"] = len(df)
            return df
        except Exception as e:
            error_msg = f"东方财富ETF行情获取失败: {str(e)}"
            logger.warning(f"⚠️ {error_msg}")
            self.session_stats["errors"].append(error_msg)
            return None
    
    def get_etf_category_mapping(self):
        """获取ETF分类映射"""
        category_keywords = {
            "宽基指数": ["沪深300", "上证50", "中证500", "中证1000", "创业板", "科创", "双创", "A50", "A500"],
            "科技": ["科技", "芯片", "半导体", "人工智能", "AI", "5G", "通信", "电子", "TMT", "软件", "计算机"],
            "医药": ["医药", "医疗", "生物", "创新药", "医疗器械", "中药", "疫苗", "健康"],
            "新能源": ["新能源", "光伏", "储能", "锂电", "电池", "碳中和", "清洁能源", "电网"],
            "消费": ["消费", "食品", "饮料", "白酒", "家电", "汽车", "旅游", "酒店", "农业", "畜牧", "养殖"],
            "金融": ["银行", "证券", "保险", "金融", "地产", "基建", "建筑", "建材"],
            "周期": ["煤炭", "钢铁", "有色", "化工", "石油", "能源", "稀土", "矿业", "资源"],
            "跨境": ["恒生", "港股", "纳斯达克", "标普", "道琼斯", "日经", "越南", "德国", "法国", "英国", "印度", "韩国", "亚太"],
            "商品": ["黄金", "白银", "有色", "豆粕", "能源", "商品", "期货", "原油"],
            "债券": ["债", "国债", "信用债", "可转债", "利率债", "企业债"]
        }
        return category_keywords
    
    def classify_etf(self, name):
        """根据ETF名称自动分类"""
        categories = self.get_etf_category_mapping()
        for category, keywords in categories.items():
            if any(kw in name for kw in keywords):
                return category
        return "其他"
    
    def enrich_etf_data(self, df):
        """丰富ETF数据：添加分类、估值标签等"""
        if df is None or df.empty:
            return df
        
        logger.info("开始数据增强处理...")
        
        # 添加分类
        if 'name' in df.columns:
            df['category'] = df['name'].apply(self.classify_etf)
        
        # 添加采集元数据
        df['collect_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['trade_date'] = datetime.now().strftime('%Y-%m-%d')
        
        # 计算成交额分级
        if 'amount' in df.columns:
            amount_median = df['amount'].median()
            df['liquidity_level'] = df['amount'].apply(
                lambda x: '高' if x >= amount_median * 2 else ('中' if x >= amount_median else '低')
            )
        
        # 涨跌幅标签
        if 'change_pct' in df.columns:
            df['change_tag'] = df['change_pct'].apply(
                lambda x: '涨停' if x >= 9.9 else ('大跌' if x <= -5 else ('上涨' if x > 0 else ('下跌' if x < 0 else '平盘')))
            )
        
        logger.info(f"✅ 数据增强完成，共 {len(df)} 条记录")
        return df
    
    def save_data(self, df, data_type="etf_spot"):
        """保存数据为标准化JSON格式"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            date_str = datetime.now().strftime('%Y%m%d')
            
            latest_filename = f"{data_type}_latest.json"
            latest_filepath = os.path.join(DATA_DIR, latest_filename)
            
            # 转换DataFrame为字典列表
            if isinstance(df, pd.DataFrame):
                df_clean = df.fillna('')
                records = df_clean.to_dict('records')
            else:
                records = df if isinstance(df, list) else [df]
            
            # 构建标准输出格式
            output = {
                "meta": {
                    "data_type": data_type,
                    "collect_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "trade_date": datetime.now().strftime('%Y-%m-%d'),
                    "total_count": len(records),
                    "lof_count": self.session_stats["lof_count"],
                    "standard_etf_count": self.session_stats["standard_etf_count"],
                    "data_source": self.session_stats["data_source_used"] or "multi_source",
                    "version": "3.0",
                    "fields": list(df.columns) if isinstance(df, pd.DataFrame) else []
                },
                "data": records
            }
            
            # 保存最新文件（覆盖）
            with open(latest_filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 最新文件已更新: {latest_filepath}")
            
            return {
                "latest_file": latest_filepath,
                "record_count": len(records)
            }
            
        except Exception as e:
            error_msg = f"保存数据失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.session_stats["errors"].append(error_msg)
            return None
    
    def generate_summary(self):
        """生成采集汇总报告"""
        end_time = datetime.now()
        duration = (end_time - self.session_stats["start_time"]).total_seconds()
        
        summary = {
            "meta": {
                "report_type": "collection_summary",
                "start_time": self.session_stats["start_time"].strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "duration_seconds": round(duration, 2),
                "status": "success" if len(self.session_stats["errors"]) == 0 else "partial_failure"
            },
            "stats": {
                "records_collected": self.session_stats["records_collected"],
                "lof_count": self.session_stats["lof_count"],
                "standard_etf_count": self.session_stats["standard_etf_count"],
                "data_source": self.session_stats["data_source_used"],
                "error_count": len(self.session_stats["errors"]),
                "errors": self.session_stats["errors"]
            },
            "output": {
                "data_dir": DATA_DIR,
                "log_file": log_file
            }
        }
        
        return summary

    def _filter_standard_etfs(self, df_ths):
        """从同花顺ETF列表中筛选标准ETF（排除LOF）"""
        codes = df_ths['基金代码'].tolist()
        names = df_ths['基金名称'].tolist()
        
        # 标准ETF前缀（交易所交易基金）
        standard_prefixes = ['510', '512', '513', '515', '516', '518', '588', '159']
        # LOF前缀（不在标准ETF中）
        lof_prefixes = ['160', '161', '162', '163', '164', '165', '166', '167', '168', '169',
                        '501', '502', '506']
        
        standard = []
        for code, name in zip(codes, names):
            code_str = str(code)
            # 是标准ETF前缀且不是LOF前缀
            is_standard = any(code_str.startswith(p) for p in standard_prefixes)
            is_lof = any(code_str.startswith(p) for p in lof_prefixes)
            if is_standard and not is_lof:
                standard.append((code_str, name))
        
        return standard

    def run(self):
        """
        执行完整采集流程 v3.0
        
        策略：
        1. 新浪财经 → LOF基金实时行情（382只）
        2. 同花顺 + 新浪历史K线 → 标准ETF最新数据（1100+只）
        3. 合并去重，保存全市场ETF数据
        """
        logger.info("=" * 70)
        logger.info("🚀 ETF估值数据采集Agent v3.0 启动（全市场ETF）")
        logger.info(f"📅 采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        
        all_records = []
        
        # ===== Step 1: 采集LOF基金（新浪实时行情） =====
        df_lof = self.get_etf_spot_sina()
        if df_lof is not None and len(df_lof) > 0:
            df_lof_enriched = self.enrich_etf_data(df_lof)
            lof_records = df_lof_enriched.to_dict('records')
            all_records.extend(lof_records)
            logger.info(f"📊 LOF基金: {len(lof_records)} 只")
        else:
            logger.warning("⚠️ LOF基金数据获取失败")
        
        # ===== Step 2: 采集标准ETF（同花顺列表 + 新浪历史K线） =====
        df_ths = self.get_standard_etf_list_ths()
        if df_ths is not None and len(df_ths) > 0:
            standard_etfs = self._filter_standard_etfs(df_ths)
            logger.info(f"📋 筛选出 {len(standard_etfs)} 只标准ETF（排除LOF）")
            
            if standard_etfs:
                std_records = self.fetch_standard_etf_latest_data(standard_etfs)
                if std_records:
                    all_records.extend(std_records)
                    logger.info(f"📊 标准ETF: {len(std_records)} 只")
        else:
            logger.warning("⚠️ 同花顺ETF列表获取失败，跳过标准ETF")
        
        # ===== Step 3: 合并去重 =====
        if not all_records:
            logger.error("❌ 所有数据源均失败")
            return None
        
        # 按code去重（优先保留LOF数据，因其有完整实时行情）
        seen_codes = set()
        unique_records = []
        lof_first = sorted(all_records, key=lambda x: 0 if x.get('fund_type') == 'LOF' else 1)
        for rec in lof_first:
            code = rec.get('code', '')
            if code and code not in seen_codes:
                seen_codes.add(code)
                unique_records.append(rec)
        
        logger.info(f"📊 合并后总计: {len(unique_records)} 只ETF（去重后）")
        self.session_stats["records_collected"] = len(unique_records)
        self.session_stats["data_source_used"] = "sina_lof+ths_list+sina_hist"
        
        # ===== Step 4: 保存 =====
        # 将records转为DataFrame以兼容save_data
        df_all = pd.DataFrame(unique_records)
        save_result = self.save_data(df_all, "etf_spot")
        
        # 分类统计
        if 'category' in df_all.columns:
            category_stats = df_all['category'].value_counts().to_dict()
            logger.info("📊 ETF分类统计:")
            for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"   {cat}: {count}只")
        
        # 基金类型统计
        if 'fund_type' in df_all.columns:
            type_stats = df_all['fund_type'].value_counts().to_dict()
            logger.info("📊 基金类型统计:")
            for ft, count in type_stats.items():
                logger.info(f"   {ft}: {count}只")
        
        # 生成汇总报告
        summary = self.generate_summary()
        
        logger.info("=" * 70)
        logger.info(f"✅ 采集完成! 状态: {summary['meta']['status']}")
        logger.info(f"📈 共采集 {summary['stats']['records_collected']} 只ETF")
        logger.info(f"   LOF: {summary['stats']['lof_count']}, 标准ETF: {summary['stats']['standard_etf_count']}")
        logger.info(f"⏱️ 耗时: {summary['meta']['duration_seconds']:.2f}秒")
        logger.info("=" * 70)
        
        return summary


# ============ 配置管理 ============
def load_config():
    """加载Agent配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return get_default_config()

def get_default_config():
    """获取默认配置"""
    return {
        "agent_name": "ETF_估值数据采集",
        "version": "3.0",
        "schedule": {
            "enabled": True,
            "cron": "0 20 9 * * *",
            "timezone": "Asia/Shanghai",
            "description": "每天09:20自动执行"
        },
        "data_collection": {
            "sources": ["sina_lof", "ths_list", "sina_hist"],
            "fields": ["code", "name", "price", "change_pct", "amount", "fund_type"],
            "categories": ["宽基指数", "科技", "医药", "新能源", "消费", "金融", "周期", "跨境", "商品", "债券"]
        },
        "output": {
            "data_dir": DATA_DIR,
            "log_dir": LOG_DIR,
            "format": "json",
            "retention_days": 30
        },
    }

def save_config(config):
    """保存Agent配置"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ============ 主入口 ============
def main():
    """主函数"""
    config = load_config()
    save_config(config)
    
    collector = ETFDataCollector()
    result = collector.run()
    
    if result:
        print("\n" + "=" * 70)
        print("📊 采集结果摘要:")
        print(f"  状态: {result['meta']['status']}")
        print(f"  总记录数: {result['stats']['records_collected']}")
        print(f"  LOF基金: {result['stats']['lof_count']}")
        print(f"  标准ETF: {result['stats']['standard_etf_count']}")
        print(f"  数据源: {result['stats']['data_source']}")
        print(f"  耗时: {result['meta']['duration_seconds']:.2f}秒")
        print("=" * 70)
    else:
        print("\n❌ 采集失败，请检查日志了解详情")
        sys.exit(1)
    
    return result

if __name__ == "__main__":
    main()
