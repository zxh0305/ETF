#!/bin/bash
# =============================================================================
# ETF全流程自动化启动脚本
# =============================================================================
# 用途: 在 macOS/Linux 定时任务中调用
# 用法: ./run_etf_full_pipeline.sh
#       ./run_etf_full_pipeline.sh --force
#       ./run_etf_full_pipeline.sh --step step1
#
# 日志: 自动写入 logs/ 目录
# =============================================================================

# 获取脚本所在目录（支持软链接）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${PROJECT_DIR}/logs"

# 创建日志目录
mkdir -p "${LOG_DIR}"

# 日志文件
TIMESTAMP=$(date "+%Y%m%d_%H%M%S")
LOG_FILE="${LOG_DIR}/run_${TIMESTAMP}.log"

# 进入项目目录
cd "${PROJECT_DIR}"

# 输出启动信息
echo "=============================================="
echo "ETF全流程自动化启动"
echo "时间: $(date "+%Y-%m-%d %H:%M:%S")"
echo "项目: ${PROJECT_DIR}"
echo "日志: ${LOG_FILE}"
echo "=============================================="

# 调用Python脚本，传递所有参数
# STDERR和STDOUT都重定向到日志文件，同时显示在终端
python3 "${SCRIPT_DIR}/run_etf_full_pipeline.py" "$@" 2>&1 | tee -a "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}

# 写入执行结束标记
echo "" >> "${LOG_FILE}"
echo "==============================================" >> "${LOG_FILE}"
echo "执行结束: $(date "+%Y-%m-%d %H:%M:%S")" >> "${LOG_FILE}"
echo "退出码: ${EXIT_CODE}" >> "${LOG_FILE}"
echo "==============================================" >> "${LOG_FILE}"

# 根据退出码返回
if [ ${EXIT_CODE} -eq 0 ]; then
    echo ""
    echo "✅ 全流程执行完成（退出码: ${EXIT_CODE}）"
else
    echo ""
    echo "❌ 执行失败（退出码: ${EXIT_CODE}），请查看日志"
    echo "日志文件: ${LOG_FILE}"
fi

exit ${EXIT_CODE}
