"""Minimal LLM gateway client (OpenAI-chat and Anthropic-native protocols, text + images).

Keys are read from ~/.config/modelproxy/keys/<name>.env (MP_KEY / MODELPROXY_API_KEY) and never printed.
"""
import base64
import json
import mimetypes
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

MP_DIR = Path(os.environ.get("CCG_CONFIG_DIR", str(Path.home() / ".config/modelproxy")))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _read_env(path, names):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].strip()
            for n in names:
                if line.startswith(n + "="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return None


def key_and_base(name="main"):
    p = MP_DIR / "keys" / f"{name}.env"
    k = _read_env(p, ["MP_KEY", "MODELPROXY_API_KEY", "ANTHROPIC_API_KEY"])
    b = _read_env(p, ["MP_BASE"]) or "https://mp.z01.normandyfunc.com"
    if not k:
        raise RuntimeError(f"no key in {p}")
    return k, b.rstrip("/")


def _img_b64(path, max_side=None):
    data = Path(path).read_bytes()
    mt = mimetypes.guess_type(str(path))[0] or "image/png"
    return mt, base64.b64encode(data).decode()


def _sse(resp):
    buf = []
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
        if line.startswith("data:"):
            buf.append(line[5:].strip())
        elif line == "" and buf:
            yield "\n".join(buf)
            buf = []
    if buf:
        yield "\n".join(buf)


def is_claude(model):
    return model.startswith("claude") or "opus" in model or "fable" in model or "sonnet" in model


def call(model, prompt, images=(), system=None, max_tokens=8000, effort=None, key="main",
         timeout=900, retries=4, temperature=None):
    """Return (text, meta). images: list of file paths (sent in order before the prompt text)."""
    k, base = key_and_base(key)
    last = None
    for attempt in range(retries):
        try:
            if is_claude(model):
                return _claude(base, k, model, prompt, images, system, max_tokens, effort, timeout, temperature)
            return _openai(base, k, model, prompt, images, system, max_tokens, effort, timeout, temperature)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {e.code}: {body}"
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(min(90, 4 * 2 ** attempt + random.random() * 3))
    raise RuntimeError(f"{model} failed: {last}")


def _claude(base, k, model, prompt, images, system, max_tokens, effort, timeout, temperature):
    content = []
    for p in images:
        mt, b64 = _img_b64(p)
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}})
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system
    if effort:
        body["thinking"] = {"type": "adaptive"}
        body["output_config"] = {"effort": effort}
    elif temperature is not None:
        body["temperature"] = temperature
    req = urllib.request.Request(f"{base}/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "x-api-key": k,
                                          "anthropic-version": "2023-06-01", "accept": "text/event-stream",
                                          "x-fr-strict": "1"})
    chunks, stop, usage, seen = [], None, {}, None
    with OPENER.open(req, timeout=timeout) as r:
        for p in _sse(r):
            if not p or p == "[DONE]":
                continue
            ev = json.loads(p)
            t = ev.get("type")
            if t == "message_start":
                seen = (ev.get("message") or {}).get("model")
                usage.update((ev.get("message") or {}).get("usage") or {})
            elif t == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                chunks.append(ev["delta"]["text"])
            elif t == "message_delta":
                stop = (ev.get("delta") or {}).get("stop_reason") or stop
                usage.update(ev.get("usage") or {})
            elif t == "error":
                raise RuntimeError(f"stream error: {ev.get('error')}")
    text = "".join(chunks)
    if not text.strip():
        raise RuntimeError(f"empty response stop={stop}")
    return text, {"model": seen or model, "stop": stop, "usage": usage}


def _openai(base, k, model, prompt, images, system, max_tokens, effort, timeout, temperature):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    if images:
        content = []
        for p in images:
            mt, b64 = _img_b64(p)
            content.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
        content.append({"type": "text", "text": prompt})
        msgs.append({"role": "user", "content": content})
    else:
        msgs.append({"role": "user", "content": prompt})
    body = {"model": model, "max_tokens": max_tokens, "stream": True, "messages": msgs}
    if effort:
        body["reasoning_effort"] = effort
    if temperature is not None and "astra" not in model and "sol" not in model:
        body["temperature"] = temperature
    req = urllib.request.Request(f"{base}/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "authorization": f"Bearer {k}",
                                          "accept": "text/event-stream", "x-fr-strict": "1"})
    chunks, stop, usage, seen = [], None, {}, None
    with OPENER.open(req, timeout=timeout) as r:
        for p in _sse(r):
            if p == "[DONE]" or not p:
                continue
            ev = json.loads(p)
            if ev.get("error"):
                raise RuntimeError(f"stream error: {ev['error']}")
            seen = ev.get("model") or seen
            usage.update(ev.get("usage") or {})
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    chunks.append(d["content"])
                stop = ch.get("finish_reason") or stop
    text = "".join(chunks)
    if not text.strip():
        raise RuntimeError(f"empty response stop={stop}")
    return text, {"model": seen or model, "stop": stop, "usage": usage}


def _fix_escapes(s):
    r"""Repair LaTeX backslashes inside JSON string literals.

    Models often emit "\\frac" correctly but sometimes "\frac" (parsed as form-feed + "rac") or "\(".
    Inside string literals: keep valid escapes; treat \\b \\f \\n \\r \\t followed by a letter as a LaTeX
    command (\\beta, \\frac, \\nabla, \\rho, \\theta) and escape the backslash; escape any other invalid one.
    """
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        c = s[i]
        if not in_str:
            if c == '"':
                in_str = True
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_str = False
            out.append(c)
            i += 1
            continue
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nx = s[i + 1] if i + 1 < n else ""
        if nx in ('"', "\\", "/"):
            out.append(c + nx)
            i += 2
        elif nx == "u" and all(ch in "0123456789abcdefABCDEF" for ch in s[i + 2:i + 6]) and len(s[i + 2:i + 6]) == 4:
            out.append(s[i:i + 6])
            i += 6
        elif nx in "bfnrt" and nx:
            after = s[i + 2] if i + 2 < n else ""
            if after.isalpha():
                out.append("\\\\" + nx)
            else:
                out.append(c + nx)
            i += 2
        else:
            out.append("\\\\")
            i += 1
    return "".join(out)


def _loads_lenient(s):
    return json.loads(_fix_escapes(s), strict=False)


def extract_json(text):
    """Extract the first JSON object/array from a model response (tolerates ```json fences)."""
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        for part in parts[1::2]:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return _loads_lenient(part)
            except Exception:  # noqa: BLE001
                continue
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i = s.find(open_c)
        j = s.rfind(close_c)
        if i != -1 and j > i:
            try:
                return _loads_lenient(s[i:j + 1])
            except Exception:  # noqa: BLE001
                continue
    raise ValueError("no JSON found in response")
