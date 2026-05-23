#!/usr/bin/env python3
"""
东方财富登录态获取工具
需要用户手动登录后，从浏览器提取Cookie

使用方法：
1. 在浏览器打开 https://passport.eastmoney.com/ 登录
2. 登录成功后，按F12打开开发者工具
3. 切换到 Network 标签
4. 刷新页面，找到任意请求
5. 在请求头中找到 Cookie 字段，复制完整值
6. 运行此脚本粘贴Cookie
"""

import os
import json
import time

COOKIE_FILE = os.path.expanduser("~/.qclaw/workspace/etf-agent/config/em_cookie.json")

def save_cookie(cookie_string: str):
    """保存Cookie到文件"""
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    
    cookie_data = {
        "cookie": cookie_string,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 86400 * 7))  # 7天有效期
    }
    
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cookie_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Cookie已保存到: {COOKIE_FILE}")
    print(f"   更新时间: {cookie_data['updated_at']}")
    print(f"   过期时间: {cookie_data['expires_at']}")

def load_cookie() -> str:
    """加载Cookie"""
    if not os.path.exists(COOKIE_FILE):
        return None
    
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 检查是否过期
    expires_at = time.mktime(time.strptime(data['expires_at'], "%Y-%m-%d %H:%M:%S"))
    if time.time() > expires_at:
        print("⚠️ Cookie已过期，请重新登录")
        return None
    
    return data['cookie']

def test_cookie(cookie_string: str):
    """测试Cookie是否有效"""
    import ssl
    import urllib.request
    
    ctx = ssl._create_unverified_context()
    
    # 测试访问指数PE/PB数据
    url = 'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_INDEX_TMP_PE&columns=ALL&filter=(INDEX_CODE="000300")&pageSize=5'
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://data.eastmoney.com',
        'Cookie': cookie_string,
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            raw = r.read().decode('utf-8')
        data = json.loads(raw)
        
        if data.get('success'):
            print("✅ Cookie有效！成功获取指数PE数据")
            if data.get('result'):
                result = data['result']
                if isinstance(result, dict) and 'data' in result:
                    records = result['data']
                    print(f"   返回 {len(records)} 条记录")
                    if records:
                        print(f"   示例: {records[0]}")
            return True
        else:
            print(f"❌ Cookie无效或权限不足: {data.get('message')}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 从命令行参数获取Cookie
        cookie = sys.argv[1]
    else:
        print(__doc__)
        print("\n请粘贴Cookie（粘贴后按回车）:")
        cookie = input().strip()
    
    if not cookie:
        print("❌ Cookie不能为空")
        sys.exit(1)
    
    # 测试Cookie
    print("\n正在测试Cookie...")
    if test_cookie(cookie):
        # 保存Cookie
        save_cookie(cookie)
    else:
        print("\n❌ Cookie无效，请确保已正确登录东方财富")
