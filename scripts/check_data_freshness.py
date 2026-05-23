#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF数据时效监控脚本
功能:
1. 检查 etf_valuation_latest.json 的数据日期
2. 若超过2个交易日未更新 → 输出告警
3. 超出阈值则返回非零退出码，便于 cron 告警机制捕获
"""

import json
import os
import sys
from datetime import datetime, timedelta

# 交易日判断：用前后各3天排除法
# A股周末休市，节假日另行判断（简化：只用周末排除）
TRADING_DAYS_THRESHOLD = 2  # 超过2个交易日未更新 → 告警

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VALUATION_FILE = os.path.join(DATA_DIR, "etf_valuation_latest.json")


def is_trading_day(dt: datetime) -> bool:
    """判断是否为交易日（排除周末，节假日简化处理）"""
    return dt.weekday() < 5


def count_trading_days_between(start: datetime, end: datetime) -> int:
    """计算两个日期之间的交易日天数（不包含start当天）"""
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def get_latest_trading_day() -> datetime:
    """获取最近一个交易日（不含今天，如果今天是周末）"""
    today = datetime.now()
    
    # 如果今天是非交易日，向前回溯到最近的周五
    if not is_trading_day(today):
        days_back = today.weekday() - 4  # 周六=5, 周日=6
        return today - timedelta(days=days_back)
    
    return today


def check_freshness():
    """检查数据新鲜度"""
    print(f"[数据时效检查] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not os.path.exists(VALUATION_FILE):
        print(f"❌ 告警: 数据文件不存在: {VALUATION_FILE}")
        print(f"   采集任务可能未执行，请检查！")
        return 2  # 严重错误
    
    try:
        with open(VALUATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        meta = data.get("meta", {})
        # 兼容多种字段名
        data_trade_date_str = (
            meta.get("trade_date") or
            meta.get("generated_at", "")[:10] or  # "2026-05-02T16:50:22" → "2026-05-02"
            meta.get("collect_time", "")[:10] or
            ""
        )
        collect_time = meta.get("collect_time") or meta.get("generated_at", "未知")
        record_count = meta.get("total_count", 0) or meta.get("total", 0)
        
        if not data_trade_date_str:
            # 备选：直接从spot文件读取
            spot_file = os.path.join(DATA_DIR, "etf_spot_latest.json")
            if os.path.exists(spot_file):
                with open(spot_file, "r", encoding="utf-8") as f2:
                    spot_data = json.load(f2)
                    spot_meta = spot_data.get("meta", {})
                    data_trade_date_str = spot_meta.get("trade_date", "")[:10]
                    collect_time = spot_meta.get("collect_time", "未知")
                    record_count = spot_meta.get("total_count", 0)
            
            if not data_trade_date_str:
                print(f"❌ 告警: 数据文件中无trade_date字段")
                return 2
        
        data_trade_date = datetime.strptime(data_trade_date_str, "%Y-%m-%d")
        latest_trading_day = get_latest_trading_day()
        
        # 计算间隔交易日数
        stale_days = count_trading_days_between(data_trade_date, latest_trading_day)
        
        print(f"   数据最新交易日: {data_trade_date_str}")
        print(f"   最近交易日:      {latest_trading_day.strftime('%Y-%m-%d')}")
        print(f"   采集时间:        {collect_time}")
        print(f"   记录数:          {record_count}")
        print(f"   间隔交易日数:    {stale_days}")
        
        if stale_days == 0:
            print(f"✅ 数据新鲜，无需告警")
            return 0
        elif stale_days == 1:
            print(f"⚠️  注意: 数据已有1个交易日未更新（正常，采集时间可能稍晚）")
            return 0
        elif stale_days <= TRADING_DAYS_THRESHOLD:
            print(f"⚠️  警告: 数据已超过{stale_days}个交易日未更新")
            print(f"   建议检查定时任务执行状态")
            return 1
        else:
            print(f"❌ 严重: 数据已超过{stale_days}个交易日未更新！")
            print(f"   请立即检查:")
            print(f"   1. 定时任务是否正常执行 (cron jobs)")
            print(f"   2. 采集脚本是否报错 (logs/)")
            print(f"   3. akshare接口是否正常")
            return 2
            
    except json.JSONDecodeError as e:
        print(f"❌ 错误: JSON解析失败: {e}")
        return 2
    except Exception as e:
        print(f"❌ 错误: {e}")
        return 2


if __name__ == "__main__":
    exit_code = check_freshness()
    sys.exit(exit_code)
