import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND = os.path.join(ROOT, "frontend")

html_files = []
for root, dirs, files in os.walk(FRONTEND):
    for f in files:
        if f.endswith(".html"):
            html_files.append(os.path.join(root, f))

missing_assets = []
checked_links = 0

for hpath in html_files:
    dir_name = os.path.dirname(hpath)
    with open(hpath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Find script tags
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', content)
    for s in scripts:
        if not s.startswith("http") and not s.startswith("//"):
            checked_links += 1
            clean_s = s.split("?")[0].split("#")[0]
            asset_path = os.path.normpath(os.path.join(dir_name, clean_s))
            if not os.path.exists(asset_path):
                missing_assets.append((hpath, "script", s, asset_path))

    # Find CSS links
    css = re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', content)
    for c in css:
        if ("stylesheet" in content or c.endswith(".css")) and not c.startswith("http") and not c.startswith("//"):
            checked_links += 1
            clean_c = c.split("?")[0].split("#")[0]
            asset_path = os.path.normpath(os.path.join(dir_name, clean_c))
            if not os.path.exists(asset_path):
                missing_assets.append((hpath, "css", c, asset_path))

print(f"Checked {len(html_files)} HTML files and {checked_links} local asset links.")
if missing_assets:
    print(f"Found {len(missing_assets)} broken local asset references:")
    for h, kind, ref, p in missing_assets:
        print(f"  In {os.path.relpath(h, ROOT)}: [{kind}] {ref} -> NOT FOUND")
else:
    print("All local script and CSS references across all HTML files exist cleanly!")

