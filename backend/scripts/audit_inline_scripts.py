import os
import re
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND = os.path.join(ROOT, "frontend")

html_files = []
for root, dirs, files in os.walk(FRONTEND):
    for f in files:
        if f.endswith(".html"):
            html_files.append(os.path.join(root, f))

errors = []
tested = 0

for hpath in html_files:
    with open(hpath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Extract inline scripts
    scripts = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', content, re.DOTALL)
    for idx, s in enumerate(scripts):
        code = s.strip()
        if not code or "tailwind.config" in code:
            continue
        tested += 1

        # Check with node -c
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            res = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True)
            if res.returncode != 0:
                errors.append((hpath, idx, res.stderr))
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

print(f"Tested {tested} inline script blocks across {len(html_files)} HTML files.")
if errors:
    print(f"Found {len(errors)} inline JavaScript syntax errors:")
    for h, idx, err in errors:
        print(f"  In {os.path.relpath(h, ROOT)} script #{idx}: {err.strip()}")
else:
    print("All inline JavaScript blocks passed syntax checking with 0 errors!")

