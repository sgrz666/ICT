import subprocess
import re
import pathlib

cmd = ["git", "ls-files", "*README.md"]
files = subprocess.check_output(cmd, text=True).splitlines()
readmes = [pathlib.Path(f) for f in files if "upstream" not in pathlib.Path(f).parts]
bad = []
for r in readmes:
    for m in re.finditer(r"\]\(([^)]+)\)", r.read_text(encoding="utf-8")):
        t = m.group(1).strip().split("#")[0]
        if t and not t.startswith(("http", "mailto:")) and not (r.parent / t).resolve().exists():
            bad.append((str(r), t))
print("READMEs:", len(readmes), "| broken links:", len(bad))
for b in bad:
    print("BROKEN:", b)
