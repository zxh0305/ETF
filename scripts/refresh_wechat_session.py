#!/usr/bin/env python3
"""
微信Bot Session主动刷新脚本
每天凌晨03:00主动检查并刷新Session，避免白天推送时断连
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta

def find_token_file(account_id):
    """找到账号文件（支持.json和.sync.json）"""
    import glob
    accounts_dir = os.path.expanduser("~/.qclaw/openclaw-weixin/accounts")
    patterns = [
        os.path.join(accounts_dir, f"{account_id}.json"),
        os.path.join(accounts_dir, f"{account_id}.sync.json"),
        os.path.join(accounts_dir, "*-im-bot.json"),
        os.path.join(accounts_dir, "*-im-bot.sync.json"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            if os.path.exists(f) and not f.endswith(".bak"):
                return f
    return None

def check_session_age(token_file):
    """检查Session年龄（小时）"""
    if not os.path.exists(token_file):
        return None  # Token文件不存在
    
    # 获取文件修改时间
    mtime = os.path.getmtime(token_file)
    age_hours = (time.time() - mtime) / 3600
    
    return age_hours

def refresh_session(account_id):
    """刷新Session（删除旧Token，触发重新登录）"""
    try:
        # 1. 删除旧Token文件
        token_file = find_token_file(account_id)
        if os.path.exists(token_file):
            print(f"🗑️  删除旧Token文件：{token_file}")
            os.remove(token_file)
        
        # 2. 重启Gateway（触发重新登录）
        print("🔄 重启Gateway（触发重新登录）...")
        result = subprocess.run(
            ["openclaw", "gateway", "restart"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Gateway重启成功，请重新扫码登录")
            return True
        else:
            print(f"❌ Gateway重启失败：{result.stderr}")
            return False
        
    except Exception as e:
        print(f"❌ 刷新Session失败：{e}")
        return False

def send_notification(message):
    """发送通知到微信（如果Session有效）"""
    try:
        # 尝试发送通知（如果Session还有效）
        script_path = os.path.join(os.path.dirname(__file__), "send_wechat_message.py")
        if os.path.exists(script_path):
            cmd = ["python3", script_path, "--msg", message, "--target", "o9cq8043X0uLnMJHYliCj_dv7wUM@im.wechat"]
            subprocess.run(cmd, timeout=10, capture_output=True)
            print(f"📱 通知已发送：{message}")
    except Exception as e:
        print(f"⚠️  通知发送失败（可能Session已过期）：{e}")

def main():
    """主函数"""
    print("=" * 60)
    print("微信Bot Session主动刷新")
    print("=" * 60)
    
    account_id = "1727fabc8808-im-bot"
    token_file = find_token_file(account_id)
    
    # 1. 检查Session年龄
    age_hours = check_session_age(token_file)
    
    if age_hours is None:
        print("⚠️  Token文件不存在，Session可能已过期")
        print("🔄 执行刷新操作...")
        success = refresh_session(account_id)
    elif age_hours > 20:
        print(f"⚠️  Session已使用 {age_hours:.1f} 小时，即将过期（>20小时）")
        print("🔄 执行刷新操作...")
        success = refresh_session(account_id)
    else:
        print(f"✅ Session还很新（{age_hours:.1f} 小时），无需刷新")
        success = True
    
    # 2. 记录结果
    log_file = "/tmp/wechat_session_refresh.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a") as f:
        if success:
            f.write(f"[{timestamp}] ✅ Session刷新成功\n")
            print(f"\n✅ Session刷新成功！请重新扫码登录")
            print(f"📝 日志已写入：{log_file}")
        else:
            f.write(f"[{timestamp}] ❌ Session刷新失败\n")
            print(f"\n❌ Session刷新失败！")
            print(f"📝 日志已写入：{log_file}")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())