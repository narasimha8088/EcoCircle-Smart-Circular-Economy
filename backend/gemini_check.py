"""
gemini_check.py — find out in seconds WHY Gemini isn't answering.

Used in three places:
  * `python check_gemini.py`   (run by hand, plain Python — the clearest test)
  * at server start-up         (one line in the terminal: [OK] / [WARN] ...)
  * ai_routes.py               (turns raw SDK errors into a human sentence)
"""

from __future__ import annotations

import base64
import os
import re
import socket
import time

HOST = "generativelanguage.googleapis.com"

# 1x1 transparent PNG, used to test the "image + text" path the analyzer really uses
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def explain_error(err: BaseException) -> str:
    """One short, human sentence for the most common Gemini failures."""
    text = f"{type(err).__name__}: {err}"
    low = text.lower()
    if "recursion" in low:
        return ("A Python SSL/eventlet conflict broke the HTTPS call. Run the server with the latest app.py "
                "(threading mode) and make sure SOCKETIO_ASYNC_MODE is not set to eventlet.")
    if "504" in low or "deadline_exceeded" in low or "deadline expired" in low:
        return ("Google received the request but took too long to answer (504). This is Google being slow or busy, "
                "not your key or network. Try again; if it repeats, raise GEMINI_TIMEOUT_SECONDS in backend/.env.")
    if any(k in low for k in ("timed out", "timeout", "readtimeout", "connecttimeout", "deadline")):
        return ("No answer from Google in time. Your network (college/office Wi-Fi, firewall, VPN or proxy) "
                "is probably blocking or slowing generativelanguage.googleapis.com. Try a mobile hotspot.")
    if any(k in low for k in ("connecterror", "connection refused", "name or service not known",
                              "getaddrinfo", "temporary failure in name resolution", "network is unreachable",
                              "connection reset", "proxyerror", "unable to connect")):
        return ("Cannot reach Google from this computer (no internet, DNS, firewall or proxy). "
                "Open https://generativelanguage.googleapis.com in a browser to check, or try a mobile hotspot.")
    if "api key not valid" in low or "api_key_invalid" in low or ("invalid" in low and "api key" in low):
        return ("Google rejected this API key as invalid. Create a new key at aistudio.google.com/app/apikey, "
                "paste it into backend/.env, save, and restart.")
    if "permission_denied" in low or "403" in low:
        return ("Google refused the request (permission denied). The key may be restricted, or the Gemini API "
                "isn't enabled / allowed in your region for this key.")
    if "not_found" in low or "404" in low or "is not found" in low:
        return ("Google rejected every model name the app tried (see the technical detail). Your key may not have access to them, or your google-genai package is outdated: run  pip install -U google-genai  and restart. You can also set GEMINI_MODEL=gemini-2.0-flash in backend/.env.")
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return "Gemini free-tier limit reached (rate/quota). Wait a minute and try again, or use another key."
    if "ssl" in low or "certificate" in low:
        return "SSL/certificate problem talking to Google (often a proxy or antivirus intercepting HTTPS)."
    if "503" in low or "unavailable" in low or "overloaded" in low:
        return "Gemini is temporarily overloaded. Try again in a moment."
    return text[:220].rstrip(". ") + "."


def is_network_error(err: BaseException) -> bool:
    """True for timeouts / no-connection errors. Trying another model can't fix those."""
    low = f"{type(err).__name__}: {err}".lower()
    return any(k in low for k in ("timed out", "timeout", "connecterror", "connection refused", "getaddrinfo",
                                  "name or service not known", "network is unreachable", "proxyerror",
                                  "connection reset", "unable to connect", "ssl", "certificate"))


def preflight(timeout: float = 8.0) -> tuple[bool, str]:
    """DNS + TCP connect to Google. Tells apart 'no network' from 'bad key'."""
    t = time.time()
    try:
        ip = socket.gethostbyname(HOST)
    except Exception as e:
        return False, f"DNS lookup for {HOST} failed ({e}). No internet or DNS blocked."
    try:
        s = socket.create_connection((ip, 443), timeout=timeout)
        s.close()
    except Exception as e:
        return False, f"Cannot open a connection to {HOST} ({ip}:443): {e}. Firewall/proxy/Wi-Fi is blocking Google."
    return True, f"reached {HOST} in {time.time() - t:.1f}s"


def _client(api_key: str, timeout_s: float):
    import google.genai as genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))), types


def ping(api_key: str, model: str, timeout_s: float = 30.0, with_image: bool = False) -> tuple[bool, float, str]:
    """One tiny real call. Returns (ok, seconds, reply_or_friendly_error)."""
    t = time.time()
    try:
        client, types = _client(api_key, timeout_s)
        if with_image:
            contents = [types.Part.from_bytes(data=_TINY_PNG, mime_type="image/png"),
                        "What is in this image? Answer in 3 words."]
        else:
            contents = "Reply with the single word: ok"
        resp = client.models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(max_output_tokens=256))
        txt = (getattr(resp, "text", None) or "").strip()
        return True, time.time() - t, (txt[:60] or "(empty reply)")
    except BaseException as e:   # noqa: BLE001 - we want to report everything
        return False, time.time() - t, explain_error(e)


def clean_key(raw: str | None) -> str:
    return (raw or "").strip().strip("\"'")


_STATIC_FALLBACKS = ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-1.5-flash")
_discovered: dict = {"key": None, "models": None, "at": 0.0}

def discover_models(api_key: str | None = None, ttl: float = 600.0) -> list[str]:
    """Ask Google which models THIS key can actually call (generateContent). Cached for 10 min.
    Model names get retired / renamed and differ per key, so a hard-coded list is never reliable."""
    key = clean_key(api_key or os.getenv("GEMINI_API_KEY"))
    if not key:
        return []
    now = time.time()
    if _discovered["key"] == key and _discovered["models"] is not None and now - _discovered["at"] < ttl:
        return list(_discovered["models"])
    found: list[str] = []
    try:
        client, _ = _client(key, 6)
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            if actions and "generateContent" not in actions:
                continue
            low = name.lower()
            if not low.startswith("gemini"):
                continue
            if any(bad in low for bad in ("image", "tts", "live", "embedding", "audio", "robotics",
                                          "computer-use", "native", "preview-0", "exp", "thinking", "learnlm")):
                continue
            # Skip gemini-3.x models — they require allowlisting and cause 503/504 for most keys
            if re.match(r"gemini-3\.", low):
                continue
            found.append(name)
    except BaseException:    # noqa: BLE001 - discovery is best-effort
        found = []
    def rank(n: str):
        low = n.lower()
        # stable "-latest" aliases first, then plain flash, then newest version numbers, lite last
        fam = 0 if low.endswith("-latest") and "flash" in low and "lite" not in low else \
              1 if "flash" in low and "lite" not in low else 2 if "flash" in low else 3
        nums = re.findall(r"(\d+(?:\.\d+)?)", low)
        ver = -float(nums[0]) if nums else 0.0
        preview = 1 if "preview" in low else 0
        return (fam, preview, ver, low)
    found = sorted(set(found), key=rank)
    _discovered.update(key=key, models=found, at=now)
    return list(found)


def candidate_models(api_key: str | None = None) -> list[str]:
    """Configured model first (if Google really offers it), then models discovered for this key,
    then static fallbacks."""
    configured = (os.getenv("GEMINI_MODEL") or "").strip()
    discovered = discover_models(api_key)
    out: list[str] = []
    def add(m):
        if m and m not in out:
            out.append(m)
    if configured and (not discovered or configured in discovered or configured.endswith("-latest")):
        add(configured)
    for m in discovered[:4]:
        add(m)
    for m in _STATIC_FALLBACKS:
        add(m)
    if configured:
        add(configured)       # last resort: try it anyway
    return out


def startup_selfcheck(log=print) -> None:
    """Non-blocking one-liner for the terminal at server start (run in a background thread)."""
    key = clean_key(os.getenv("GEMINI_API_KEY"))
    if not key or key == "your_gemini_api_key_here":
        return
    ok, msg = preflight(8)
    if not ok:
        log(f"[WARN] Gemini self-check: {msg}")
        log("       The AI Analyzer will fall back to rule-based answers until Google is reachable.")
        return
    model = candidate_models()[0]
    good, secs, info = ping(key, model, timeout_s=25)
    if good:
        log(f"[OK] Gemini self-check passed: {model} answered in {secs:.1f}s")
    else:
        log(f"[WARN] Gemini self-check failed after {secs:.0f}s with {model}: {info}")
        log("       For a full report run:  python check_gemini.py")


def run_cli() -> int:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path, override=True)
    print("=" * 64)
    print(" Gemini connection check")
    print("=" * 64)
    print(f" .env file : {env_path}  ({'found' if os.path.exists(env_path) else 'MISSING'})")
    key = clean_key(os.getenv("GEMINI_API_KEY"))
    if not key or key == "your_gemini_api_key_here":
        print(" API key   : MISSING or placeholder -> put GEMINI_API_KEY=... in that file, save, re-run.")
        return 1
    print(f" API key   : found ({len(key)} chars, ends ...{key[-4:]})")
    try:
        import google.genai as g
        print(f" SDK       : google-genai {g.__version__}")
    except ImportError:
        print(" SDK       : NOT INSTALLED -> pip install google-genai")
        return 1
    print("\n 1) Can this computer reach Google?")
    ok, msg = preflight(10)
    print(("    OK  " if ok else "    FAIL ") + msg)
    if not ok:
        print("\n >> Fix the network first (try a mobile hotspot), then run this again.")
        return 2
    print("\n 2) Does your key + model work?  (30s limit per call)")
    working = None
    for m in candidate_models():
        good, secs, info = ping(key, m, 30)
        print(f"    {'OK  ' if good else 'FAIL'} {m}: {secs:.1f}s  ->  {info}")
        if good:
            working = m
            break
    if not working:
        print("\n >> Gemini did not answer. The line above says why.")
        return 3
    print("\n 3) Does an IMAGE + text request work? (what the analyzer sends)")
    good, secs, info = ping(key, working, 45, with_image=True)
    print(f"    {'OK  ' if good else 'FAIL'} {working}: {secs:.1f}s  ->  {info}")
    print("\n" + ("All good. If the web page still fails, send me the terminal lines it prints." if good
                  else " >> Text works but image requests fail; send me the line above."))
    return 0 if good else 4
