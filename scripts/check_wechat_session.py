#!/usr/bin/env python3
"""
微信Bot Session健康检查脚本
检查当前WeChat Bot token是否有效，如果session过期则输出告警信息。
用法: python3 check_wechat_session.py
返回码: 0=正常, 1=session过期, 2=其他错误
"""
import json
import glob
import os
import sys
import subprocess

ACCOUNTS_DIR = os.path.expanduser("~/.qclaw/openclaw-weixin/accounts")

def find_latest_account():
    """找到最新的微信Bot账号文件（优先.json，fallback .sync.json）"""
    # 优先使用 .json 文件（含完整token）
    json_files = [f for f in glob.glob(os.path.join(ACCOUNTS_DIR, "*-im-bot.json"))
                  if not f.endswith(".bak") and not f.endswith(".sync.json")]
    if json_files:
        json_files.sort(key=os.path.getmtime, reverse=True)
        return json_files[0]
    # fallback: .sync.json 文件
    sync_files = [f for f in glob.glob(os.path.join(ACCOUNTS_DIR, "*-im-bot.sync.json"))
                  if not f.endswith(".bak")]
    if sync_files:
        sync_files.sort(key=os.path.getmtime, reverse=True)
        return sync_files[0]
    return None

def check_session(account_file):
    """使用curl调用getconfig API检查session（快速，非长轮询）"""
    with open(account_file, 'r') as f:
        account = json.load(f)
    
    token = account.get('token', '')
    base_url = account.get('baseUrl', 'https://ilinkai.weixin.qq.com')
    user_id = account.get('userId', '')
    account_id = os.path.basename(account_file).replace('.sync.json', '').replace('.json', '')
    
    if not token:
        return {"status": "error", "message": f"账号 {account_id} 无token"}
    
    url = f"{base_url}/ilink/bot/getconfig"
    body = json.dumps({"ilink_user_id": user_id})
    
    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "10",
                "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-H", f"Authorization: Bearer {token}",
                "-H", "AuthorizationType: ilink_bot_token",
                "-d", body
            ],
            capture_output=True, text=True, timeout=15
        )
        
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"⚠️ curl执行失败 (exit {result.returncode})",
                "account_id": account_id
            }
        
        resp = json.loads(result.stdout)
        
        if resp.get('errcode') == -14:
            return {
                "status": "expired",
                "message": f"❌ Session已过期 (errcode:-14, {resp.get('errmsg','')})",
                "account_id": account_id
            }
        elif resp.get('ret') == -2:
            return {
                "status": "expired", 
                "message": f"❌ Session无效 (ret:-2, 需要重启gateway或重新登录)",
                "account_id": account_id
            }
        elif resp.get('errcode') is not None and resp.get('errcode') != 0:
            return {
                "status": "error",
                "message": f"⚠️ API错误: errcode={resp.get('errcode')} {resp.get('errmsg','')}",
                "account_id": account_id
            }
        elif resp.get('ret') is not None and resp.get('ret') != 0:
            if resp.get('ret') == -4:
                return {
                    "status": "ok",
                    "message": f"✅ Session正常 (ret=-4内部错误可忽略, account: {account_id})",
                    "account_id": account_id
                }
            return {
                "status": "error",
                "message": f"⚠️ API错误: ret={resp.get('ret')}",
                "account_id": account_id
            }
        else:
            return {
                "status": "ok",
                "message": f"✅ Session正常 (account: {account_id})",
                "account_id": account_id
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": f"⚠️ API请求超时",
            "account_id": account_id
        }
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": f"⚠️ API返回非JSON: {result.stdout[:200]}",
            "account_id": account_id
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"⚠️ 检查失败: {e}",
            "account_id": account_id
        }

def main():
    account_file = find_latest_account()
    if not account_file:
        print("❌ 未找到微信Bot账号文件")
        sys.exit(2)
    
    result = check_session(account_file)
    print(result["message"])
    
    if result["status"] == "expired":
        print("\n🔧 修复步骤:")
        print("1. 删除旧token: rm ~/.qclaw/openclaw-weixin/accounts/*-im-bot.json")
        print("2. 重新登录: openclaw channels login --channel openclaw-weixin")
        print("3. 扫码授权")
        print("4. 重启gateway加载新token")
        sys.exit(1)
    elif result["status"] == "error":
        sys.exit(2)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
