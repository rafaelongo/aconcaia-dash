#!/usr/bin/env python3
"""
Hook PostToolUse: antes de commitar _contexto/, reunioes/ ou memoria.md,
verifica se há versão mais recente no GitHub e puxa primeiro.
Recebe JSON do Claude Code via stdin.
"""
import sys, json, subprocess, os, re

data = json.loads(sys.stdin.read())
fp = data.get("tool_input", {}).get("file_path", "")

if not re.search(r"(_contexto[/\\]|reunioes[/\\]|memoria\.md$)", fp, re.IGNORECASE):
    sys.exit(0)

git = next(
    (p for p in [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
    ] if os.path.exists(p)),
    "git",
)

file_dir = os.path.dirname(fp)
result = subprocess.run([git, "-C", file_dir, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
if result.returncode != 0:
    sys.exit(0)
repo = result.stdout.strip()

# Verifica se há versão mais recente no GitHub e puxa antes de commitar
has_remote = subprocess.run(
    [git, "-C", repo, "remote", "get-url", "origin"],
    capture_output=True
).returncode == 0

if has_remote:
    subprocess.run([git, "-C", repo, "fetch", "--quiet"], capture_output=True)
    status = subprocess.run(
        [git, "-C", repo, "status", "-sb"],
        capture_output=True, text=True
    ).stdout
    if "behind" in status:
        subprocess.run([git, "-C", repo, "pull", "--rebase", "--quiet"], capture_output=True)

try:
    rel = os.path.relpath(fp, repo)
except Exception:
    rel = os.path.basename(fp)

subprocess.run([git, "-C", repo, "add", fp], capture_output=True)
diff = subprocess.run([git, "-C", repo, "diff", "--cached", "--quiet"], capture_output=True)
if diff.returncode != 0:
    subprocess.run([git, "-C", repo, "commit", "-m", f"auto: {rel}"], capture_output=True)
    if has_remote:
        subprocess.run([git, "-C", repo, "push", "--quiet"], capture_output=True)
