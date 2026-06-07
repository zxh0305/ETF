#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF全流程自动化脚本
==================
串联 ETF 行情采集 → 估值补全 → 低估筛选 → 结果对比 → 简报生成

目标: 每天09:20自动执行，生成简报文件
当前约束: 仅生成本地文件，不发送任何外部推送

流程:
  Step0 → Step1 → Step2 → Step3 → Step4 → Step5 → Step6 → Step7 → Step8

输出文件:
  - data/sw_industry_valuation_latest.json  # Step0: 申万行业估值
  - data/etf_spot_latest.json          # Step1: 行情数据
  - data/etf_valuation_latest.json    # Step2: 估值补全数据
  - output/low_valuation_candidates_latest.json  # Step3: 低估候选
  - output/low_valuation_report_latest.md       # Step3: Markdown报告
  - output/change_report_latest.json    # Step4: 变化报告
  - output/daily_report_latest.txt       # Step5: 微信日报 ← 最终交付物
  - output/daily_report_latest.md       # Step5: Markdown版日报
  - archive/index_valuation_history/   # Step6: 每日指数快照
  - data/index_percentiles_latest.json # Step7: 历史分位（积累中）
  - output/etf_analysis_latest.json    # Step8: 趋势分析与板块轮动
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ============================================================================
# 配置区
# ============================================================================

BASE_DIR = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"
ARCHIVE_DIR = BASE_DIR / "archive"

# 关键文件路径
SPOT_JSON = DATA_DIR / "etf_spot_latest.json"
VALUATION_JSON = DATA_DIR / "etf_valuation_latest.json"
CANDIDATES_JSON = OUTPUT_DIR / "low_valuation_candidates_latest.json"
REPORT_MD = OUTPUT_DIR / "low_valuation_report_latest.md"
CHANGE_JSON = OUTPUT_DIR / "change_report_latest.json"
BRIEF_TXT = OUTPUT_DIR / "daily_report_latest.txt"  # v4.0: 微信日报
DAILY_MD = OUTPUT_DIR / "daily_report_latest.md"  # v4.0: Markdown日报
SW_VALUATION_JSON = DATA_DIR / "sw_industry_valuation_latest.json"  # 申万行业估值

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# 步骤定义
# ============================================================================

STEPS = [
    {
        "id": "step0",
        "name": "申万行业估值刷新",
        "desc": "调用akshare获取申万31行业官方PE/PB/股息率",
        "script": "sw_industry_valuation.py",
        "output": SW_VALUATION_JSON,
        "required": False,  # 非交易时间可能失败，不阻塞流水线
    },
    {
        "id": "step0a",
        "name": "中证指数官方PE",
        "desc": "从中证指数官网获取9个宽基指数历史PE，计算真实分位",
        "script": "fetch_csindex_pe.py",
        "output": DATA_DIR / "index_percentiles_latest.json",
        "required": False,  # 乐咕备用，不阻塞流水线
    },
    {
        "id": "step1",
        "name": "行情采集",
        "desc": "从东方财富/新浪/腾讯获取全市场ETF实时行情",
        "script": "../etf_data_collector.py",
        "output": SPOT_JSON,
        "required": True,
    },
    {
        "id": "step2",
        "name": "估值补全",
        "desc": "补齐PE/PB/PEG等估值字段（当前为Mock）",
        "script": "etf_valuation_enricher.py",
        "output": VALUATION_JSON,
        "required": True,
    },
    {
        "id": "step2a_calc",
        "name": "穿透估值计算",
        "desc": "基于ETF持仓×申万行业PE/PB加权计算穿透估值（约32分钟，输出etf_penetration_valuation_latest.json）",
        "script": "penetration_valuation_v1_real.py",
        "output": DATA_DIR / "etf_penetration_valuation_latest.json",
        "required": False,  # 计算失败不阻塞流水线，使用旧数据
    },
    {
        "id": "step2a_merge",
        "name": "穿透估值合并",
        "desc": "将行业穿透估值数据合并到主估值文件（补充无分位ETF的PE/PB分位）",
        "script": "sw_industry_valuation.py",
        "output": VALUATION_JSON,
        "required": False,  # 穿透估值文件不存在时跳过
    },
    {
        "id": "step3",
        "name": "低估筛选",
        "desc": "基于分位数、PEG、流动性筛选低估ETF",
        "script": "agent2_etf_screener_v5.py",
        "output": CANDIDATES_JSON,
        "required": True,
    },
    {
        "id": "step4",
        "name": "结果对比",
        "desc": "对比今日与昨日候选，识别新增/退出",
        "script": "agent3_etf_comparator.py",
        "output": CHANGE_JSON,
        "required": False,  # 首次运行可以不执行
    },
    {
        "id": "step5",
        "name": "微信日报生成",
        "desc": "生成PPT标准格式微信日报（含市场温度、投资建议）",
        "script": "daily_report_v10.py",
        "output": None,
        "required": True,
    },
    {
        "id": "step6",
        "name": "指数快照归档",
        "desc": "按跟踪指数聚合ETF估值数据，生成每日历史快照",
        "script": "archive_index_snapshot.py",
        "output": None,
        "required": True,
    },
    {
        "id": "step7",
        "name": "历史分位计算",
        "desc": "从归档快照计算各指数PE/PB历史分位数（过渡期积累中）",
        "script": "calc_index_percentiles.py",
        "output": DATA_DIR / "index_percentiles_latest.json",
        "required": False,  # 积累不足时仍可运行，只是无 real_percentile
    },
    {
        "id": "step8",
        "name": "趋势分析与板块轮动",
        "desc": "基于历史归档分析ETF排名变化、分位变化、板块轮动信号",
        "script": "etf_analysis.py",
        "output": OUTPUT_DIR / "etf_analysis_latest.json",
        "required": False,
    },
]

# ============================================================================
# 日志设置
# ============================================================================

class StepLogAdapter(logging.LoggerAdapter):
    """带步骤标签的日志适配器"""
    def process(self, msg, kwargs):
        return f"[{self.extra.get('step', 'main')}] {msg}", kwargs


def setup_logging() -> logging.Logger:
    """配置日志到文件和终端"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 日志文件名: run_YYYYMMDD_HHMMSS.log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"run_{timestamp}.log"
    
    logger = logging.getLogger("etf_pipeline")
    logger.setLevel(LOG_LEVEL)
    logger.handlers = []  # 清除已有handler
    
    # 文件handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(LOG_LEVEL)
    file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 终端handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    logger.info(f"日志文件: {log_file}")
    
    return logger


logger = setup_logging()


# ============================================================================
# 步骤执行器
# ============================================================================

class StepExecutor:
    """步骤执行器"""
    
    def __init__(self, step: Dict[str, Any], logger: logging.Logger):
        self.step = step
        self.logger = logger
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.success = False
        self.error: Optional[str] = None
    
    def run(self, force: bool = False) -> bool:
        """执行单个步骤"""
        self.start_time = datetime.now()
        
        step_id = self.step["id"]
        step_name = self.step["name"]
        script_name = self.step["script"]
        output_path = self.step["output"]
        required = self.step["required"]
        
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"【{step_id.upper()}】{step_name}")
        self.logger.info(f"  脚本: {script_name}")
        self.logger.info(f"  输出: {output_path}")
        self.logger.info(f"  必需: {'是' if required else '否'}")
        self.logger.info("=" * 60)
        
        # 检查是否需要跳过
        if output_path and not force and output_path.exists():
            self.logger.info(f"  ⏭️  输出已存在，跳过（force=True可重新执行）")
            self.success = True
            self.end_time = datetime.now()
            return True
        
        # 执行脚本
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            self.error = f"脚本不存在: {script_path}"
            self.logger.error(f"  ✗ {self.error}")
            if required:
                return False
            else:
                self.success = False
                return True  # 非必需步骤，警告后继续
        
        try:
            self.logger.info(f"  ▶️  执行脚本...")
            
            # 使用Python解释器执行
            exit_code = os.system(f'cd "{SCRIPTS_DIR}" && python3 "{script_name}" >> /dev/null 2>&1')
            
            if exit_code != 0:
                # 尝试带输出执行看错误
                self.logger.warning(f"  ⚠️ 脚本退出码: {exit_code}，重新执行并显示输出...")
                exit_code = os.system(f'cd "{SCRIPTS_DIR}" && python3 "{script_name}"')
                self.error = f"脚本执行失败，退出码: {exit_code}"
                self.logger.error(f"  ✗ {self.error}")
                if required:
                    return False
                else:
                    self.success = False
                    return True
            
            # 验证输出
            if output_path and output_path.exists():
                self.logger.info(f"  ✓ 输出文件已生成: {output_path.name}")
                self.success = True
            elif output_path is None:
                # 无输出文件的步骤，只要脚本执行成功即可
                self.logger.info(f"  ✓ 脚本执行完成（无输出文件）")
                self.success = True
            else:
                self.error = f"输出文件未生成: {output_path}"
                self.logger.warning(f"  ⚠️ {self.error}")
                if required:
                    return False
            
        except Exception as e:
            self.error = str(e)
            self.logger.error(f"  ✗ 执行异常: {e}")
            self.logger.debug(traceback.format_exc())
            if required:
                return False
        
        self.end_time = datetime.now()
        return True
    
    def get_duration(self) -> str:
        """获取执行时长"""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return f"{delta.total_seconds():.1f}秒"
        return "N/A"
    
    def get_summary(self) -> Dict[str, Any]:
        """获取步骤摘要"""
        return {
            "id": self.step["id"],
            "name": self.step["name"],
            "success": self.success,
            "duration": self.get_duration(),
            "error": self.error,
            "output": str(self.step["output"]),
        }


# ============================================================================
# 流程控制器
# ============================================================================

class PipelineController:
    """
    ETF全流程控制器
    
    负责:
    - 创建所需目录
    - 按顺序执行各步骤
    - 处理异常
    - 输出统计
    """
    
    def __init__(self, force: bool = False):
        self.force = force
        self.step_results: list = []
        self.pipeline_start: datetime = datetime.now()
        self.pipeline_end: Optional[datetime] = None
        
        # 确保目录存在
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """确保所有目录存在"""
        dirs = [DATA_DIR, OUTPUT_DIR, LOGS_DIR, ARCHIVE_DIR]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ 目录就绪: {d}")

    def _backup_latest_before_run(self) -> Dict[str, Any]:
        """
        在流水线运行前，备份当前 latest 文件到 archive/backup/YYYYMMDD_HHMMSS/
        防止流水线中途失败导致 latest 被覆盖为不完整数据
        """
        backup_dir = ARCHIVE_DIR / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        files_to_backup = [
            (SPOT_JSON, "spot.json"),
            (VALUATION_JSON, "valuation.json"),
            (CANDIDATES_JSON, "candidates.json"),
            (CHANGE_JSON, "change_report.json"),
            (BRIEF_TXT, "daily_report.txt"),
            (REPORT_MD, "report.md"),
            (DAILY_MD, "daily_report_md.md"),
        ]

        backed_up = []
        skipped = []
        for src_path, archive_name in files_to_backup:
            if src_path.exists():
                dest_path = backup_dir / archive_name
                try:
                    import shutil
                    shutil.copy2(src_path, dest_path)
                    backed_up.append(archive_name)
                except Exception as e:
                    logger.warning(f"  ⚠️ 备份失败 {src_path.name}: {e}")
            else:
                skipped.append(src_path.name)

        logger.info(f"📦 运行前备份完成: {backup_dir.name}/")
        if backed_up:
            for name in backed_up:
                logger.info(f"  ✓ {name}")
        if skipped:
            logger.info(f"  - 跳过(不存在): {', '.join(skipped)}")

        return {"backup_dir": str(backup_dir), "count": len(backed_up)}

    def _archive_outputs(self) -> Dict[str, Any]:
        """
        归档当天关键输出文件到 archive/YYYY-MM-DD/ 目录
        归档文件:
        - data/etf_spot_latest.json
        - data/etf_valuation_latest.json
        - output/low_valuation_candidates_latest.json
        - output/change_report_latest.json
        - output/daily_report_latest.txt
        """
        today = datetime.now().strftime("%Y-%m-%d")
        archive_dir = ARCHIVE_DIR / today
        archive_dir.mkdir(parents=True, exist_ok=True)

        files_to_archive = [
            (SPOT_JSON, "spot.json"),
            (VALUATION_JSON, "valuation.json"),
            (CANDIDATES_JSON, "candidates.json"),
            (CHANGE_JSON, "change_report.json"),
            (BRIEF_TXT, "daily_report.txt"),
            (DAILY_MD, "daily_report_md.md"),
        ]

        archived = []
        errors = []

        for src_path, archive_name in files_to_archive:
            if src_path.exists():
                dest_path = archive_dir / archive_name
                try:
                    import shutil
                    shutil.copy2(src_path, dest_path)
                    archived.append({
                        "source": str(src_path.name),
                        "archived": str(dest_path),
                        "size": dest_path.stat().st_size
                    })
                except Exception as e:
                    errors.append({"file": str(src_path), "error": str(e)})
            else:
                errors.append({"file": str(src_path), "error": "文件不存在"})

        # 同时复制一份原始文件名（保留latest后缀便于识别）
        for src_path, _ in files_to_archive:
            if src_path.exists():
                dest_path = archive_dir / src_path.name
                try:
                    import shutil
                    shutil.copy2(src_path, dest_path)
                except Exception:
                    pass  # 忽略复制错误

        result = {
            "archive_dir": str(archive_dir),
            "date": today,
            "archived_count": len(archived),
            "error_count": len(errors),
            "files": archived,
            "errors": errors if errors else None
        }

        logger.info("")
        logger.info("=" * 60)
        logger.info("📦 归档完成")
        logger.info("=" * 60)
        logger.info(f"  归档目录: {archive_dir}")
        logger.info(f"  成功: {len(archived)} 个文件")
        if errors:
            logger.info(f"  失败: {len(errors)} 个文件")
        for item in archived:
            size_kb = item['size'] / 1024
            size_str = f"{size_kb:.1f}KB" if size_kb > 1 else f"{item['size']}B"
            logger.info(f"  ✓ {item['source']} → {size_str}")
        logger.info("=" * 60)

        return result
    
    def _load_result_meta(self, path: Path) -> Optional[Dict[str, Any]]:
        """加载结果文件的meta信息"""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("meta", {})
        except Exception:
            return None
    
    def run(self) -> Dict[str, Any]:
        """执行全流程"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("🚀 ETF全流程自动化启动")
        logger.info(f"  时间: {self.pipeline_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"  强制重跑: {'是' if self.force else '否'}")
        logger.info("=" * 60)
        
        # 运行前备份最新文件（防止中途失败导致数据丢失）
        backup_result = self._backup_latest_before_run()
        
        # 执行各步骤
        for step in STEPS:
            executor = StepExecutor(step, logger)
            success = executor.run(force=self.force)
            
            self.step_results.append(executor.get_summary())
            
            if not success and step["required"]:
                logger.error("")
                logger.error(f"✗ 必需步骤 {step['name']} 执行失败，流程终止")
                self._print_summary()
                sys.exit(1)
        
        self.pipeline_end = datetime.now()

        # 归档当天输出
        archive_result = self._archive_outputs()

        # 打印总结
        self._print_summary()

        # 输出最终简报内容
        self._print_final_brief()

        # 构建最终报告（包含归档信息）
        report = self._build_final_report()
        report["archive"] = archive_result

        return report
    
    def _print_summary(self):
        """打印流程总结"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 ETF全流程执行报告")
        logger.info("=" * 60)
        
        total_duration = (self.pipeline_end - self.pipeline_start).total_seconds() if self.pipeline_end else 0
        
        for r in self.step_results:
            status = "✅" if r["success"] else "❌"
            logger.info(f"  {status} [{r['id']}] {r['name']:12s} | {r['duration']:>8s} | {r.get('error', '')}")
        
        logger.info("-" * 60)
        
        # 统计
        success_count = sum(1 for r in self.step_results if r["success"])
        fail_count = len(self.step_results) - success_count
        logger.info(f"  总步骤数: {len(self.step_results)}")
        logger.info(f"  成功: {success_count} | 失败: {fail_count}")
        logger.info(f"  总耗时: {total_duration:.1f}秒")
        
        # 关键输出文件
        logger.info("")
        logger.info("📁 关键输出文件:")
        
        files_to_check = [
            (SPOT_JSON, "行情数据"),
            (VALUATION_JSON, "估值数据"),
            (CANDIDATES_JSON, "低估候选"),
            (CHANGE_JSON, "变化报告"),
            (BRIEF_TXT, "微信日报"),
        ]
        
        for path, name in files_to_check:
            if path.exists():
                size = path.stat().st_size
                size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
                logger.info(f"  ✅ {name}: {path.name} ({size_str})")
            else:
                logger.info(f"  ⚠️  {name}: {path.name} (未生成)")
        
        logger.info("=" * 60)
    
    def _print_final_brief(self):
        """打印最终简报"""
        if not BRIEF_TXT.exists():
            logger.warning("⚠️ 简报文件未生成")
            return
        
        try:
            with open(BRIEF_TXT, "r", encoding="utf-8") as f:
                content = f.read()
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("📋 最终简报内容 (daily_report_latest.txt):")
            logger.info("=" * 60)
            
            # 只显示前40行
            lines = content.split("\n")
            for line in lines[:40]:
                logger.info(line)
            if len(lines) > 40:
                logger.info("...（省略后续内容）...")
            
            logger.info("=" * 60)
            logger.info(f"完整内容已保存至: {BRIEF_TXT}")
            
        except Exception as e:
            logger.error(f"读取简报失败: {e}")
    
    def _build_final_report(self) -> Dict[str, Any]:
        """构建最终报告"""
        success_count = sum(1 for r in self.step_results if r["success"])
        fail_count = len(self.step_results) - success_count
        
        report = {
            "meta": {
                "pipeline": "ETF全流程自动化",
                "version": "1.0",
                "start_time": self.pipeline_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": self.pipeline_end.strftime("%Y-%m-%d %H:%M:%S") if self.pipeline_end else None,
                "duration_seconds": (self.pipeline_end - self.pipeline_start).total_seconds() if self.pipeline_end else 0,
                "success": fail_count == 0,
            },
            "steps": self.step_results,
            "summary": {
                "total_steps": len(self.step_results),
                "success_count": success_count,
                "fail_count": fail_count,
            },
            "outputs": {
                "spot_data": str(SPOT_JSON.name) if SPOT_JSON.exists() else None,
                "valuation_data": str(VALUATION_JSON.name) if VALUATION_JSON.exists() else None,
                "candidates": str(CANDIDATES_JSON.name) if CANDIDATES_JSON.exists() else None,
                "change_report": str(CHANGE_JSON.name) if CHANGE_JSON.exists() else None,
                "dialog_brief": str(BRIEF_TXT.name) if BRIEF_TXT.exists() else None,
            },
        }
        
        return report


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ETF全流程自动化脚本")
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重跑所有步骤（忽略已有输出）"
    )
    parser.add_argument(
        "--step",
        type=str,
        choices=["step0", "step0a", "step1", "step2", "step2a", "step3", "step4", "step5", "step6", "step7", "step8"],
        help="只运行指定步骤"
    )
    args = parser.parse_args()
    
    if args.step:
        # 单步执行
        step_def = next((s for s in STEPS if s["id"] == args.step), None)
        if not step_def:
            logger.error(f"未知步骤: {args.step}")
            sys.exit(1)
        
        executor = StepExecutor(step_def, logger)
        success = executor.run(force=True)
        
        if success:
            logger.info("✅ 步骤执行成功")
        else:
            logger.error("❌ 步骤执行失败")
            sys.exit(1)
    else:
        # 全流程执行
        controller = PipelineController(force=args.force)
        report = controller.run()
        
        # 输出JSON报告（用于后续处理）
        report_file = LOGS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info("")
        logger.info("✅ ETF全流程执行完成！")
        logger.info(f"   执行报告: {report_file}")
        
        # 返回退出码
        if report["summary"]["fail_count"] > 0:
            sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
