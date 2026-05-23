#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline 健康检查脚本
=====================
每日检查 ETF-Agent 数据采集和处理是否正常运行，
确保长期稳定积累历史数据。

检查项：
  1. 关键文件是否存在
  2. 今天是否已执行 pipeline
  3. 指数估值快照条数
  4. 最近7天快照是否有缺失

输出：
  output/pipeline_health_latest.json

状态等级：
  - healthy: 一切正常
  - warning: 有非致命问题（如历史快照缺失）
  - error: 关键文件缺失或 pipeline 未执行
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
ARCHIVE_DIR = BASE_DIR / "archive" / "index_valuation_history"

# 关键文件
KEY_FILES = {
    "etf_spot_latest.json": DATA_DIR / "etf_spot_latest.json",
    "etf_valuation_latest.json": DATA_DIR / "etf_valuation_latest.json",
    "dialog_brief_latest.txt": OUTPUT_DIR / "dialog_brief_latest.txt",
    "candidates_latest.json": OUTPUT_DIR / "low_valuation_candidates_latest.json",
}

OUTPUT_FILE = OUTPUT_DIR / "pipeline_health_latest.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("health_check")


def get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def check_file_exists(path: Path) -> Dict[str, Any]:
    """检查文件是否存在，返回状态和修改时间"""
    if not path.exists():
        return {"exists": False, "mtime": None, "size": 0}
    
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return {"exists": True, "mtime": mtime, "size": stat.st_size}


def check_key_files() -> Dict[str, Any]:
    """检查关键文件"""
    results = {}
    all_ok = True
    
    for name, path in KEY_FILES.items():
        info = check_file_exists(path)
        results[name] = info
        if not info["exists"]:
            all_ok = False
            logger.warning(f"  ⚠ 文件缺失: {name}")
        else:
            logger.info(f"  ✓ {name}: {info['size']} bytes, {info['mtime']}")
    
    return {"all_ok": all_ok, "files": results}


def check_today_snapshot() -> Dict[str, Any]:
    """检查今天的指数估值快照"""
    today = get_today_str()
    snapshot_file = ARCHIVE_DIR / f"{today}.json"
    
    if not snapshot_file.exists():
        logger.warning(f"  ⚠ 今日快照缺失: {snapshot_file.name}")
        return {"exists": False, "index_count": 0, "date": today}
    
    try:
        with open(snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        indices = data.get("indices", [])
        count = len(indices)
        logger.info(f"  ✓ 今日快照: {count} 个指数")
        return {"exists": True, "index_count": count, "date": today}
    except Exception as e:
        logger.error(f"  ⚠ 快照读取失败: {e}")
        return {"exists": False, "index_count": 0, "date": today, "error": str(e)}


def check_recent_snapshots(days: int = 7) -> Dict[str, Any]:
    """检查最近 N 天的快照是否有缺失"""
    today = datetime.now()
    missing_dates: List[str] = []
    existing_dates: List[str] = []
    
    for i in range(days):
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        snapshot_file = ARCHIVE_DIR / f"{date_str}.json"
        
        if snapshot_file.exists():
            existing_dates.append(date_str)
        else:
            # 跳过周末（周六、周日）
            if d.weekday() < 5:  # 0-4 是工作日
                missing_dates.append(date_str)
    
    # 统计总快照数
    total_snapshots = len(list(ARCHIVE_DIR.glob("*.json")))
    
    logger.info(f"  最近{days}天快照: {len(existing_dates)} 存在, {len(missing_dates)} 缺失")
    if missing_dates:
        logger.warning(f"  缺失日期: {missing_dates}")
    
    return {
        "days_checked": days,
        "existing_count": len(existing_dates),
        "missing_count": len(missing_dates),
        "missing_dates": missing_dates,
        "total_snapshots": total_snapshots,
    }


def check_data_freshness() -> Dict[str, Any]:
    """检查数据新鲜度"""
    results = {}
    warnings = []
    
    # 检查 etf_valuation_latest.json 的数据时间
    valuation_file = DATA_DIR / "etf_valuation_latest.json"
    if valuation_file.exists():
        try:
            with open(valuation_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            collect_time = meta.get("collect_time", "")
            mode = meta.get("mode", "")
            
            results["valuation_collect_time"] = collect_time
            results["valuation_mode"] = mode
            
            # 检查是否是今天的数据
            today = get_today_str()
            if collect_time and not collect_time.startswith(today):
                warnings.append(f"估值数据非今日: {collect_time}")
                logger.warning(f"  ⚠ 估值数据非今日: {collect_time}")
            else:
                logger.info(f"  ✓ 估值数据时间: {collect_time}")
        except Exception as e:
            warnings.append(f"估值数据读取失败: {e}")
            logger.error(f"  ⚠ 估值数据读取失败: {e}")
    
    return {"freshness": results, "warnings": warnings}


def determine_status(
    files_ok: bool,
    snapshot_exists: bool,
    missing_count: int,
    warnings: List[str]
) -> str:
    """判定健康状态"""
    if not files_ok or not snapshot_exists:
        return "error"
    elif missing_count > 0 or len(warnings) > 0:
        return "warning"
    else:
        return "healthy"


def run_health_check() -> Dict[str, Any]:
    """执行完整健康检查"""
    logger.info("=" * 60)
    logger.info("🏥 Pipeline 健康检查启动")
    logger.info(f"  日期: {get_today_str()}")
    logger.info("=" * 60)
    
    # 1. 检查关键文件
    logger.info("")
    logger.info("【1】检查关键文件...")
    files_result = check_key_files()
    
    # 2. 检查今日快照
    logger.info("")
    logger.info("【2】检查今日指数快照...")
    snapshot_result = check_today_snapshot()
    
    # 3. 检查最近7天快照
    logger.info("")
    logger.info("【3】检查最近7天快照...")
    recent_result = check_recent_snapshots(7)
    
    # 4. 检查数据新鲜度
    logger.info("")
    logger.info("【4】检查数据新鲜度...")
    freshness_result = check_data_freshness()
    
    # 收集所有警告
    all_warnings = freshness_result.get("warnings", [])
    if recent_result["missing_count"] > 0:
        all_warnings.append(f"最近7天缺失{recent_result['missing_count']}个快照")
    
    # 判定状态
    status = determine_status(
        files_ok=files_result["all_ok"],
        snapshot_exists=snapshot_result["exists"],
        missing_count=recent_result["missing_count"],
        warnings=all_warnings
    )
    
    # 构建输出
    output = {
        "date": get_today_str(),
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "pipeline_status": "executed" if snapshot_result["exists"] else "not_executed",
        "files_ok": files_result["all_ok"],
        "files": files_result["files"],
        "today_snapshot": snapshot_result,
        "recent_7d": {
            "existing_count": recent_result["existing_count"],
            "missing_count": recent_result["missing_count"],
            "missing_dates": recent_result["missing_dates"],
        },
        "total_snapshots": recent_result["total_snapshots"],
        "data_freshness": freshness_result["freshness"],
        "warning_messages": all_warnings,
    }
    
    return output


def main():
    """主入口"""
    # 执行检查
    result = run_health_check()
    
    # 输出结果
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"📊 健康检查结果: {result['status'].upper()}")
    logger.info("=" * 60)
    
    if result["status"] == "healthy":
        logger.info("✅ 系统运行正常")
    elif result["status"] == "warning":
        logger.warning("⚠️ 存在警告:")
        for w in result["warning_messages"]:
            logger.warning(f"  - {w}")
    else:
        logger.error("❌ 发现错误:")
        if not result["files_ok"]:
            logger.error("  - 关键文件缺失")
        if not result["today_snapshot"]["exists"]:
            logger.error("  - 今日快照缺失（pipeline 未执行）")
    
    logger.info("")
    logger.info(f"📄 详细报告: {OUTPUT_FILE}")
    
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
