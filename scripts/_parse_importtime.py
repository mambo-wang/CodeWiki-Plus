"""解析 importtime 输出，排名最慢模块。跑完即删。"""
import re

text = open("d:/repos/CodeWiki-CN/scripts/_importtime.txt", encoding="utf-16").read()
lines = text.splitlines()

# 先验证 re 基本能力
s = "import time:       561 |        561 |   _io"
print("basic re test:", bool(re.match(r"import time:", s)))

# 用 split 解析
items = []
for ln in lines:
    ln = ln.strip()
    if not ln.startswith("import time:"):
        continue
    body = ln[len("import time:"):].strip()
    parts = [p.strip() for p in body.split("|")]
    if len(parts) != 3:
        continue
    try:
        ms = float(parts[1])
    except ValueError:
        continue
    items.append((ms, parts[2]))

print("parsed:", len(items))
items.sort(reverse=True)
print("--- TOP 30 by cumulative ---")
for ms, mod in items[:30]:
    print(f"{ms:9.1f} ms  {mod}")
