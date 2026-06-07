#!/usr/bin/env python3
"""
微信消息推送脚本 - 直接调用微信 API
绕过 openclaw-weixin channel，直接使用 token 发送消息
"""
import base64
import json
import os
import random
import struct
import sys
import urllib.request
import urllib.error
import ssl

# 配置
ACCOUNTS_DIR = os.path.expanduser("~/.qclaw/openclaw-weixin/accounts")
DEFAULT_ACCOUNT_ID = "1727fabc8808-im-bot"

def load_token(account_id: str = None) -> dict:
    """加载账号 token"""
    if account_id is None:
        account_id = DEFAULT_ACCOUNT_ID
    
    token_file = os.path.join(ACCOUNTS_DIR, f"{account_id}.json")
    if not os.path.exists(token_file):
        raise FileNotFoundError(f"Token file not found: {token_file}")
    
    with open(token_file) as f:
        return json.load(f)

def get_context_token(token: str, base_url: str) -> str:
    """获取最新的 context_token"""
    uin = random.randint(0, 2**32-1)
    uin_b64 = base64.b64encode(struct.pack('<I', uin)).decode()
    version_num = (2 << 16) | (4 << 8) | 3
    
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": uin_b64,
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str(version_num),
    }
    
    body = {
        "bot_type": 3,
        "timeout": 1,
        "get_updates_buf": "",
        "base_info": {
            "channel_version": "2.4.3",
            "bot_agent": "OpenClaw"
        }
    }
    
    url = f"{base_url}/ilink/bot/getupdates"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method="POST"
    )
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        # 从最新消息中获取 context_token
        if data.get("msgs") and len(data["msgs"]) > 0:
            return data["msgs"][0].get("context_token", "")
        return ""
    except:
        return ""

def send_message(text: str, target: str = None, account_id: str = None) -> dict:
    """
    发送微信消息
    
    Args:
        text: 消息内容
        target: 目标用户 ID (默认使用 token 文件中的 userId)
        account_id: 账号 ID (默认使用 DEFAULT_ACCOUNT_ID)
    
    Returns:
        {"success": bool, "message": str}
    """
    # 加载 token
    account = load_token(account_id)
    token = account["token"]
    base_url = account.get("baseUrl", "https://ilinkai.weixin.qq.com")
    user_id = target or account["userId"]
    
    # 先获取 context_token
    context_token = get_context_token(token, base_url)
    
    # 生成 client_id
    client_id = f"openclaw-weixin-push-{random.randint(100000, 999999)}"
    
    # X-WECHAT-UIN: random uint32 -> base64
    uin = random.randint(0, 2**32-1)
    uin_b64 = base64.b64encode(struct.pack('<I', uin)).decode()
    
    # iLink-App-ClientVersion: 2.4.3 -> (2<<16)|(4<<8)|3 = 132099
    version_num = (2 << 16) | (4 << 8) | 3
    
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": uin_b64,
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str(version_num),
    }
    
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": user_id,
            "client_id": client_id,
            "message_type": 2,  # BOT
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
            "context_token": context_token or None,
        },
        "base_info": {
            "channel_version": "2.4.3",
            "bot_agent": "OpenClaw"
        }
    }
    
    url = f"{base_url}/ilink/bot/sendmessage"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method="POST"
    )
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        resp_body = resp.read().decode('utf-8')
        return {"success": True, "message": f"HTTP {resp.status}", "response": resp_body}
    except urllib.error.HTTPError as e:
        return {"success": False, "message": f"HTTP {e.code}", "response": e.read().decode('utf-8')}
    except Exception as e:
        return {"success": False, "message": str(e)}

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 send_wechat_message.py <message> [target_user_id] [account_id]")
        print("\nExample:")
        print("  python3 send_wechat_message.py 'Hello World'")
        print("  python3 send_wechat_message.py 'Hello' o9cq8043X0uLnMJHYliCj_dv7wUM@im.wechat")
        sys.exit(1)
    
    text = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else None
    account_id = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = send_message(text, target, account_id)
    
    if result["success"]:
        print(f"✅ {result['message']}")
    else:
        print(f"❌ {result['message']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
