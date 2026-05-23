#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF结果对比脚本 (ETF Comparator)
================================
Agent3: 对比今日与昨日的低估候选结果，生成变化报告

功能说明:
  - 读取 output/low_valuation_candidates_latest.json（今日）
  - 读取 output/low_valuation_candidates_prev.json（昨日备份）
  - 对比两份结果，识别：
    - 新入选ETF（今日有、昨日无）
    - 退出ETF（昨日有、今日无）
    - 排名变化ETF
  - 输出 change_report_latest.json

输入文件:
  - output/low_valuation_candidates_latest.json（今日）
  - output/low_valuation_candidates_prev.json（昨日备份，自动生成）

输出文件:
  - output/change_report_latest.json
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ============================================================================
# 配置区
# ============================================================================

BASE_DIR = Path(__file__).parent.parent.resolve()
LATEST_JSON = BASE_DIR / "output" / "low_valuation_candidates_latest.json"
PREV_JSON = BASE_DIR / "output" / "low_valuation_candidates_prev.json"
CHANGE_JSON = BASE_DIR / "output" / "change_report_latest.json"

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# 日志设置
# ============================================================================

def setup_logging(name: str = "etf_comparator") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(LOG_LEVEL)
        formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = setup_logging()


# ============================================================================
# 工具函数
# ============================================================================

def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ("", "N/A", "-", "nan", "None"):
            return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def load_json(file: Path) -> Optional[Dict[str, Any]]:
    """安全加载JSON文件，不存在时返回None"""
    if not file.exists():
        return None
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(file: Path, data: Dict[str, Any]):
    """保存JSON文件"""
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# ETF结果对比器
# ============================================================================

class ETFComparator:
    """
    ETF候选结果对比器
    
    对比维度:
    1. 新入选ETF（今日有、昨日无）
    2. 退出ETF（昨日有、今日无）
    3. 排名变化（名次升降）
    4. 评分变化
    5. 亮点标签变化
    """
    
    def __init__(self):
        self.today: Optional[Dict[str, Any]] = None
        self.yesterday: Optional[Dict[str, Any]] = None
        self.change_report: Optional[Dict[str, Any]] = None
        
        # 统计
        self.stats = {
            "today_count": 0,
            "yesterday_count": 0,
            "new_entries": 0,
            "exits": 0,
            "rank_up": 0,
            "rank_down": 0,
            "score_changes": 0,
        }
    
    def load(self) -> bool:
        """加载今日和昨日数据，优先使用 prev.json，若其来自当天则从归档恢复"""
        from datetime import datetime
        
        self.today = load_json(LATEST_JSON)
        self.yesterday = load_json(PREV_JSON)
        
        if self.today is None:
            logger.warning(f"今日数据不存在: {LATEST_JSON}")
            return False
        
        self.stats["today_count"] = self._get_count(self.today)
        
        # 检查 prev.json 是否来自当天（pipeline 多次运行会覆盖 prev.json）
        if self.yesterday is not None:
            prev_meta = self.yesterday.get("meta", {})
            prev_time = prev_meta.get("generated_at", "")[:10]  # 取日期部分 YYYY-MM-DD
            today_str = datetime.now().strftime("%Y-%m-%d")
            if prev_time == today_str:
                logger.info(f"  prev.json 来自今天({prev_time})，从归档恢复昨日数据")
                self.yesterday = None  # 触发归档加载
        
        # 如果 prev.json 不存在或无效，从归档加载最近一次非今天的候选数据
        if self.yesterday is None:
            archive_base = Path(__file__).parent.parent / "archive"
            candidates_from_archive = None
            candidates_date = None
            
            if archive_base.exists():
                # 遍历所有日期目录，找最接近的非今天的 candidates.json
                date_dirs = sorted(
                    [d for d in archive_base.iterdir() if d.is_dir() and d.name.startswith("202")],
                    reverse=True  # 从新到旧
                )
                today_str = datetime.now().strftime("%Y-%m-%d")
                for d in date_dirs:
                    if d.name != today_str:
                        candidates_path = d / "candidates.json"
                        if candidates_path.exists():
                            data = load_json(candidates_path)
                            if data and data.get("candidates"):
                                candidates_from_archive = data
                                candidates_date = d.name
                                break
            
            if candidates_from_archive:
                self.yesterday = candidates_from_archive
                logger.info(f"✓ 从归档加载昨日数据: {candidates_date}，{len(candidates_from_archive.get('candidates', []))}条候选")
            else:
                logger.info("昨日数据不存在（首次运行或归档为空），视为首次对比")
        
        self.stats["yesterday_count"] = self._get_count(self.yesterday)
        
        logger.info(f"✓ 加载今日数据: {self.stats['today_count']}条候选")
        if self.yesterday:
            logger.info(f"✓ 加载昨日数据: {self.stats['yesterday_count']}条候选")
        else:
            logger.info("  昨日数据: 无（首次运行）")
        
        return True
    
    def _get_candidates(self, data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从数据中提取候选ETF列表（兼容新旧格式）
        - 新格式: formal_pool（7只正式低估）
        - 旧格式: candidates
        """
        if data is None:
            return []
        if "formal_pool" in data:
            return data.get("formal_pool", [])
        return data.get("candidates", [])
    
    def _get_count(self, data: Optional[Dict[str, Any]]) -> int:
        """从数据中提取候选数量（兼容新旧格式）
        - 新格式: top-level formal_pool 是列表，stats.formal_pool 是整数
        - 旧格式: meta.passed_count
        """
        if data is None:
            return 0
        # 新格式优先: top-level formal_pool 列表
        if "formal_pool" in data:
            val = data["formal_pool"]
            if isinstance(val, list):
                return len(val)
            if isinstance(val, int):  # stats 里是整数
                return val
        # 新格式备选: stats 里统计数
        if "stats" in data:
            val = data["stats"].get("formal_pool")
            if isinstance(val, int):
                return val
        # 旧格式: meta.passed_count
        return data.get("meta", {}).get("passed_count", 0)
    
    def _build_code_map(self, candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """构建code -> ETF记录的映射"""
        return {c.get("code", ""): c for c in candidates}
    
    def _build_rank_map(self, candidates: List[Dict[str, Any]]) -> Dict[str, int]:
        """构建code -> 排名（从1开始）的映射"""
        return {c.get("code", ""): i + 1 for i, c in enumerate(candidates)}
    
    def compare(self) -> Dict[str, Any]:
        """
        执行对比分析
        """
        today_candidates = self._get_candidates(self.today)
        yesterday_candidates = self._get_candidates(self.yesterday)
        
        today_map = self._build_code_map(today_candidates)
        yesterday_map = self._build_code_map(yesterday_candidates)
        today_rank_map = self._build_rank_map(today_candidates)
        yesterday_rank_map = self._build_rank_map(yesterday_candidates)
        
        today_codes: Set[str] = set(today_map.keys())
        yesterday_codes: Set[str] = set(yesterday_map.keys())
        
        # 1. 新入选ETF
        new_codes = today_codes - yesterday_codes
        new_entries = []
        for code in sorted(new_codes):
            etf = today_map[code]
            new_entries.append({
                "code": code,
                "name": etf.get("name", ""),
                "category": etf.get("category", ""),
                "rank": today_rank_map.get(code),
                "score": etf.get("score"),
                "reason_tags": etf.get("reason_tags", []),
                "recommendation": etf.get("recommendation", ""),
            })
        
        # 2. 退出ETF
        exit_codes = yesterday_codes - today_codes
        exits = []
        for code in sorted(exit_codes):
            etf = yesterday_map[code]
            exits.append({
                "code": code,
                "name": etf.get("name", ""),
                "category": etf.get("category", ""),
                "prev_score": etf.get("score"),
                "prev_reason_tags": etf.get("reason_tags", []),
            })
        
        # 3. 共同持有ETF的排名和评分变化
        common_codes = today_codes & yesterday_codes
        rank_changes = []
        score_changes = []
        
        for code in sorted(common_codes):
            today_etf = today_map[code]
            yesterday_etf = yesterday_map[code]
            
            prev_rank = yesterday_rank_map.get(code)
            curr_rank = today_rank_map.get(code)
            rank_diff = prev_rank - curr_rank if (prev_rank and curr_rank) else 0
            
            prev_score = to_float(yesterday_etf.get("score"))
            curr_score = to_float(today_etf.get("score"))
            score_diff = round(curr_score - prev_score, 2) if (prev_score is not None and curr_score is not None) else None
            
            if rank_diff != 0:
                rank_changes.append({
                    "code": code,
                    "name": today_etf.get("name", ""),
                    "prev_rank": prev_rank,
                    "curr_rank": curr_rank,
                    "rank_diff": rank_diff,
                    "direction": "up" if rank_diff > 0 else "down",
                })
            
            if score_diff is not None and abs(score_diff) >= 0.5:
                score_changes.append({
                    "code": code,
                    "name": today_etf.get("name", ""),
                    "prev_score": prev_score,
                    "curr_score": curr_score,
                    "score_diff": score_diff,
                })
        
        # 统计
        self.stats["new_entries"] = len(new_entries)
        self.stats["exits"] = len(exits)
        self.stats["rank_up"] = sum(1 for r in rank_changes if r["direction"] == "up")
        self.stats["rank_down"] = sum(1 for r in rank_changes if r["direction"] == "down")
        self.stats["score_changes"] = len(score_changes)
        
        # 获取时间信息
        today_meta = self.today.get("meta", {}) if self.today else {}
        yesterday_meta = self.yesterday.get("meta", {}) if self.yesterday else {}
        
        # 构建对比报告
        self.change_report = {
            "meta": {
                "data_type": "etf_change_report",
                "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "today_file": str(LATEST_JSON.name),
                "today_source_time": today_meta.get("generate_time", ""),
                "yesterday_file": str(PREV_JSON.name) if self.yesterday else None,
                "yesterday_source_time": yesterday_meta.get("generate_time", "") if self.yesterday else None,
                "is_first_run": self.yesterday is None,
                "is_mock_data": today_meta.get("is_mock_data", False),
                "stats": self.stats,
            },
            "summary": {
                "today_count": self.stats["today_count"],
                "yesterday_count": self.stats["yesterday_count"],
                "change": self.stats["today_count"] - self.stats["yesterday_count"],
                "new_entries_count": self.stats["new_entries"],
                "exits_count": self.stats["exits"],
            },
            "new_entries": new_entries,
            "exits": exits,
            "rank_changes": rank_changes,
            "score_changes": score_changes,
            "today_top5": [
                {
                    "rank": i + 1,
                    "code": c.get("code"),
                    "name": c.get("name"),
                    "score": c.get("score"),
                    "reason_tags": c.get("reason_tags", [])[:3],
                }
                for i, c in enumerate(today_candidates[:5])
            ] if today_candidates else [],
        }
        
        return self.change_report
    
    def save(self):
        """保存对比报告"""
        if self.change_report is None:
            logger.warning("没有对比报告可保存")
            return
        
        # 保存change_report
        save_json(CHANGE_JSON, self.change_report)
        logger.info(f"✓ 写入对比报告: {CHANGE_JSON}")
        
        # 自动备份今日数据为昨日数据
        save_json(PREV_JSON, self.today)
        logger.info(f"✓ 备份今日数据为昨日: {PREV_JSON}")
    
    def print_summary(self):
        """打印统计摘要"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 ETF结果对比统计")
        logger.info("=" * 60)
        logger.info(f"  今日候选:   {self.stats['today_count']}")
        logger.info(f"  昨日候选:   {self.stats['yesterday_count']}")
        logger.info(f"  变化:       {'+' if self.stats['today_count'] - self.stats['yesterday_count'] > 0 else ''}{self.stats['today_count'] - self.stats['yesterday_count']}")
        logger.info(f"  新入选:     {self.stats['new_entries']}")
        logger.info(f"  退出:       {self.stats['exits']}")
        logger.info(f"  排名上升:   {self.stats['rank_up']}")
        logger.info(f"  排名下降:   {self.stats['rank_down']}")
        logger.info(f"  评分显著变化: {self.stats['score_changes']}")
        logger.info("=" * 60)


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主入口"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("🚀 ETF结果对比器启动")
    logger.info(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    comparator = ETFComparator()
    
    # 1. 加载数据
    if not comparator.load():
        logger.warning("⚠️ 今日数据不存在，跳过对比")
        # 创建空报告
        empty_report = {
            "meta": {
                "data_type": "etf_change_report",
                "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_first_run": True,
                "stats": {},
            },
            "summary": {
                "today_count": 0,
                "yesterday_count": 0,
                "change": 0,
                "new_entries_count": 0,
                "exits_count": 0,
            },
            "new_entries": [],
            "exits": [],
            "rank_changes": [],
            "score_changes": [],
            "today_top5": [],
        }
        save_json(CHANGE_JSON, empty_report)
        logger.info(f"✓ 写入空对比报告: {CHANGE_JSON}")
        return empty_report
    
    # 2. 执行对比
    try:
        report = comparator.compare()
    except Exception as e:
        logger.error(f"对比过程失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # 3. 保存结果
    try:
        comparator.save()
    except Exception as e:
        logger.error(f"保存对比报告失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # 4. 打印摘要
    comparator.print_summary()
    
    # 5. 打印新入选
    if report["new_entries"]:
        logger.info("")
        logger.info("📋 新入选ETF:")
        for e in report["new_entries"][:5]:
            logger.info(f"  + {e['code']} {e['name']} (排名{e['rank']})")
    
    # 6. 打印退出
    if report["exits"]:
        logger.info("")
        logger.info("📋 退出ETF:")
        for e in report["exits"][:5]:
            logger.info(f"  - {e['code']} {e['name']}")
    
    logger.info("")
    logger.info("✅ ETF结果对比完成！")
    logger.info(f"   对比报告: {CHANGE_JSON}")
    
    return report


if __name__ == "__main__":
    main()
