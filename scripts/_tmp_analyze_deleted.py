import subprocess, re, collections
out = subprocess.run(
    ["git", "-c", "core.quotepath=false", "status", "--porcelain"],
    capture_output=True, text=True, encoding="utf-8",
).stdout
deleted = []
for line in out.splitlines():
    if len(line) < 4:
        continue
    code, path = line[:2], line[3:].strip()
    if "D" in code and "notes/" in path:
        deleted.append(path)
print("deleted notes total:", len(deleted))
status_cnt = collections.Counter()
no_show = 0
for p in deleted:
    gitpath = p.replace("\\", "/")
    r = subprocess.run(["git", "show", "HEAD:" + gitpath],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        no_show += 1
        continue
    parts = r.stdout.split("---", 2)
    fm = parts[1] if len(parts) > 2 else ""
    sm = re.search(r"^status:\s*(\S+)", fm, re.M)
    status_cnt[sm.group(1) if sm else "(no status field)"] += 1
print("git show failed:", no_show)
for k, v in status_cnt.items():
    print(k + ": " + str(v))
