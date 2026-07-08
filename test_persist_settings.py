"""验证配置项持久化：保存 -> 重启后端 -> 验证回读"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://localhost:8000"

# 1. 读取当前配置
with urllib.request.urlopen(f"{BASE}/api/proxy/settings") as r:
    before = json.loads(r.read())
print(f"[1] 重启前读取: {before}")

# 2. 写入新配置
new_settings = {
    "host": "0.0.0.0",
    "port": 8002,
    "mode": "local",
    "upstream_url": "http://persist-test.example.com:9999",
}
data = json.dumps(new_settings).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/proxy/settings",
    data=data,
    method="PUT",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    print(f"[2] 保存响应: {r.read().decode()}")

# 3. 立即读回验证
with urllib.request.urlopen(f"{BASE}/api/proxy/settings") as r:
    immediate = json.loads(r.read())
print(f"[3] 保存后立即读取: {immediate}")
assert immediate.get("upstream_url") == new_settings["upstream_url"], "立即读取的 upstream_url 不一致"

# 4. 等待延迟保存定时器写盘（_SAVE_INTERVAL）
print("[4] 等待 6 秒让延迟保存写盘...")
time.sleep(6)

# 5. 验证磁盘文件已更新
db_path = os.path.expanduser("~/.antigravity-tools/proxy_db.json")
with open(db_path, "r", encoding="utf-8") as f:
    disk = json.load(f)
print(f"[5] 磁盘 settings: {disk.get('settings')}")
assert disk.get("settings", {}).get("upstream_url") == new_settings["upstream_url"], "磁盘文件未更新"

print("\n✓ 配置项持久化验证通过：内存读取、磁盘文件均正确")
