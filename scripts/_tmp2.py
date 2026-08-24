import pathlib, re, subprocess
out = subprocess.run(["git","-c","core.quotepath=false","status","--porcelain"], capture_output=True, text=True, encoding="utf-8").stdout
deleted = [l[3:].strip() for l in out.splitlines() if len(l)>3 and "D" in l[:2] and "notes/" in l]
arc_names = {p.name for p in pathlib.Path(".trash/notes-archive").glob("*.md")}
missing = []
for p in deleted:
    name = pathlib.Path(p).name
    if name not in arc_names:
        missing.append(p)
print("deleted total:", len(deleted))
print("not in archive (truly deleted):", len(missing))
for m in missing:
    print("  -", m)
