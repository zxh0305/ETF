#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF智能体日志清理脚本
功能:
1. 清理超过指定天数的旧日志文件
2. 保留最新N份报告文件（report_*.json）
3. 清理 __pycache__
"""

import json
import os
import sys
import shutil
from datetime import datetime, timedelta

# 配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RETENTION_DAYS = 7          # 日志保留天数
REPORT_RETENTION_DAYS = 14  # 报告文件保留天数
DRY_RUN = False             # 模拟运行，不实际删除

# 关键文件（绝对不删除）
PROTECTED_PATTERNS = [
    "etf_collector_",   # 当天正在运行的采集日志
]


def get_file_age_days(filepath: str) -> int:
    """获取文件年龄（天）"""
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    return (datetime.now() - mtime).days


def should_protect(filename: str) -> bool:
    """判断文件是否应受保护（不清理）"""
    today = datetime.now().strftime("%Y%m%d")
    for pattern in PROTECTED_PATTERNS:
        if pattern in filename and today in filename:
            return True
    return False


def cleanup_logs():
    """清理旧日志"""
    if not os.path.exists(LOGS_DIR):
        print("ℹ️  日志目录不存在，跳过")
        return 0, 0
    
    today = datetime.now()
    deleted_count = 0
    kept_count = 0
    freed_bytes = 0
    
    deleted_files = []
    kept_files = []
    
    for filename in os.listdir(LOGS_DIR):
        filepath = os.path.join(LOGS_DIR, filename)
        
        if not os.path.isfile(filepath):
            continue
        
        # 跳过受保护文件
        if should_protect(filename):
            kept_files.append(f"  🛡️  {filename} (今日运行中，受保护)")
            kept_count += 1
            continue
        
        age_days = get_file_age_days(filepath)
        file_size = os.path.getsize(filepath)
        
        # 报告文件：更长的保留期
        is_report = filename.startswith("report_")
        retention = REPORT_RETENTION_DAYS if is_report else RETENTION_DAYS
        
        if age_days > retention:
            if not DRY_RUN:
                try:
                    os.remove(filepath)
                    deleted_files.append(f"  🗑️  {filename} ({age_days}天前, {file_size//1024}KB)")
                    deleted_count += 1
                    freed_bytes += file_size
                except Exception as e:
                    kept_files.append(f"  ⚠️  {filename} (删除失败: {e})")
                    kept_count += 1
            else:
                deleted_files.append(f"  🗑️  [DRY] {filename} ({age_days}天前, {file_size//1024}KB)")
                deleted_count += 1
                freed_bytes += file_size
        else:
            kept_files.append(f"  ✅ {filename} ({age_days}天前)")
            kept_count += 1
    
    # 清理 __pycache__
    pycache_dirs = []
    scripts_dir = os.path.join(BASE_DIR, "scripts")
    for root, dirs, files in os.walk(scripts_dir):
        for d in dirs:
            if d == "__pycache__":
                pycache_path = os.path.join(root, d)
                pycache_dirs.append(pycache_path)
                if not DRY_RUN:
                    try:
                        shutil.rmtree(pycache_path)
                    except Exception:
                        pass
    
    # 打印结果
    mode = "[模拟运行]" if DRY_RUN else "[正式运行]"
    print(f"\n{'='*60}")
    print(f"🧹 ETF日志清理 {mode}")
    print(f"{'='*60}")
    print(f"   目录: {LOGS_DIR}")
    print(f"   今日: {today.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   日志保留: {RETENTION_DAYS}天 | 报告保留: {REPORT_RETENTION_DAYS}天")
    print(f"")
    print(f"   删除: {deleted_count} 个")
    print(f"   保留: {kept_count} 个")
    
    freed_mb = freed_bytes / 1024 / 1024
    if freed_bytes > 1024 * 1024:
        print(f"   释放空间: {freed_mb:.1f} MB")
    else:
        print(f"   释放空间: {freed_bytes / 1024:.1f} KB")
    
    if pycache_dirs:
        print(f"   __pycache__: {len(pycache_dirs)} 个已清理")
    
    print(f"\n   --- 保留文件 ---")
    for f in kept_files:
        print(f)
    print(f"\n   --- 已删除 ---")
    for f in deleted_files:
        print(f)
    print(f"{'='*60}")
    
    return deleted_count, freed_bytes


if __name__ == "__main__":
    # 支持 --dry-run 参数
    if "--dry-run" in sys.argv or "-n" in sys.argv:
        DRY_RUN = True
    
    deleted, freed = cleanup_logs()
    sys.exit(0)
