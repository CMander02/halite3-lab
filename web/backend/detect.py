"""Guess the model, reasoning effort and harness behind an uploaded conversation trace.

Supported first-class formats are Claude Code session JSONL (`~/.claude/projects/...`)
and Codex rollout JSONL (`~/.codex/sessions/...`); any other JSON / JSONL / text
export falls back to scanning `model`-like fields and finally plain text. Structured
fields are trusted far more than prose because traces routinely *mention* other
models and tools. The result is advisory: the declared choice, the detection and
an optional admin override are combined in `attribution.py`.
"""
from collections import Counter
from datetime import datetime
import gzip
import io
import json
import re
import zipfile
from .catalog import UNKNOWN

MAX_TEXT = 64 * 1024 * 1024
MODEL_KEYS = {"model", "model_name", "modelid", "model_id", "requestedmodel", "model_slug", "modelname"}
EFFORT_KEYS = {"effort", "reasoning_effort", "model_reasoning_effort", "reasoningeffort", "thinking_level", "thinkinglevel"}
CONFIDENCE = ["none", "low", "medium", "high"]


def unpack(data, filename=""):
    """Raw upload -> text (gzip and zip are expanded, capped against bombs)."""
    if data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_TEXT + 1)
    elif data[:4] == b"PK\x03\x04":
        parts, total = [], 0
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist()[:64]:
                if item.is_dir() or item.flag_bits & 1:
                    continue
                with archive.open(item) as stream:
                    chunk = stream.read(MAX_TEXT - total + 1)
                total += len(chunk)
                parts.append(chunk)
                if total > MAX_TEXT:
                    break
        data = b"\n".join(parts)
    if len(data) > MAX_TEXT:
        raise ValueError("对话轨迹解压后不能超过 64 MiB。")
    return data.decode("utf-8", errors="replace")


def _records(text):
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            value = json.loads(stripped)
            if isinstance(value, list):
                return [v for v in value if isinstance(v, dict)], True
            if isinstance(value, dict):
                for key in ("messages", "history", "conversation", "items"):
                    if isinstance(value.get(key), list):
                        return [value] + [v for v in value[key] if isinstance(v, dict)], True
                return [value], True
        except ValueError:
            pass
    records = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records, bool(records)


def _walk(value, depth=0):
    """Yield (lowercase key, value) pairs for every nested scalar."""
    if depth > 12:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from _walk(item, depth + 1)
            else:
                yield str(key).lower(), item
    elif isinstance(value, list):
        for item in value[:500]:
            yield from _walk(item, depth + 1)


def _match(catalog, kind, value):
    value = str(value).strip().lower()
    for key, entry in catalog[kind].items():
        for pattern in entry["patterns"]:
            if re.search(pattern, value, re.I):
                return key
    return None


def normalize_effort(catalog, value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # thinking budget in tokens
        return "none" if value <= 0 else "low" if value < 4096 else "medium" if value < 16384 else "high" if value < 32768 else "xhigh"
    value = str(value).strip().lower()
    for key, entry in catalog["effort"].items():
        if any(re.fullmatch(p, value, re.I) for p in entry["patterns"]):
            return key
    return None


def _timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value / 1000 if value > 1e11 else value
    if isinstance(value, str) and len(value) >= 19 and value[4] == "-":
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def detect(catalog, text):
    records, structured = _records(text)
    models, efforts, harness_votes = Counter(), Counter(), Counter()
    evidence, raw_models = [], Counter()
    times, messages, output_tokens = [], 0, 0

    def vote_model(raw, weight):
        key = _match(catalog, "model", raw)
        raw_models[str(raw)[:60]] += weight
        if key:
            models[key] += weight

    for record in records:
        kind = record.get("type")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        stamp = _timestamp(record.get("timestamp"))
        if stamp:
            times.append(stamp)
        # Claude Code session JSONL
        if "sessionId" in record and ("userType" in record or "entrypoint" in record or kind in ("api-request", "queue-operation")):
            harness_votes["claude-code"] += 3
        message = record.get("message") if isinstance(record.get("message"), dict) else None
        if kind == "assistant" and message:
            messages += 1
            if isinstance(message.get("model"), str) and message["model"] != "<synthetic>":
                vote_model(message["model"], 5)
            usage = message.get("usage") or {}
            if isinstance(usage.get("output_tokens"), int):
                output_tokens += usage["output_tokens"]
        elif kind == "user" and message:
            messages += 1
        if kind == "api-request" and isinstance(record.get("params"), dict):
            params = record["params"]
            if isinstance(params.get("model"), str):
                vote_model(params["model"], 5)
            config = params.get("output_config") or {}
            if isinstance(config, dict) and config.get("effort"):
                effort = normalize_effort(catalog, config["effort"])
                if effort:
                    efforts[effort] += 5
            thinking = params.get("thinking") or {}
            if isinstance(thinking, dict) and thinking.get("type") == "disabled":
                efforts["none"] += 5
            elif isinstance(thinking, dict) and isinstance(thinking.get("budget_tokens"), int):
                efforts[normalize_effort(catalog, thinking["budget_tokens"])] += 3
        # Codex rollout JSONL
        if kind == "session_meta":
            originator = str(payload.get("originator", "")).lower()
            if "codex" in originator:
                harness_votes["codex"] += 20
                evidence.append(f"Codex originator={originator}")
            elif originator:
                harness_votes[_match(catalog, "harness", originator) or UNKNOWN] += 5
        if kind == "turn_context":
            if isinstance(payload.get("model"), str):
                vote_model(payload["model"], 5)
            settings = (payload.get("collaboration_mode") or {}).get("settings") or {}
            for value in (payload.get("effort"), settings.get("reasoning_effort")):
                effort = normalize_effort(catalog, value) if value else None
                if effort:
                    efforts[effort] += 5
        if kind == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") or {}
            total = (info.get("total_token_usage") or {}).get("output_tokens")
            if isinstance(total, int):
                output_tokens = max(output_tokens, total)
        if kind == "response_item" and payload.get("type") == "message":
            messages += 1
        # Generic exports: any model / effort field anywhere in the record
        if kind not in ("assistant", "api-request", "api-request-shape", "turn_context"):
            for key, value in _walk(record):
                if key in MODEL_KEYS and isinstance(value, str) and 2 < len(value) < 80:
                    vote_model(value, 1)
                elif key in EFFORT_KEYS and isinstance(value, (str, int)):
                    effort = normalize_effort(catalog, value)
                    if effort:
                        efforts[effort] += 1
                elif key in ("originator", "client", "source", "app", "harness", "agent") and isinstance(value, str):
                    found = _match(catalog, "harness", value)
                    if found:
                        harness_votes[found] += 2
        if kind in ("assistant", "user") and message is None and record.get("role"):
            messages += 1

    sample = text[:2_000_000]
    if not models:
        for key, entry in catalog["model"].items():
            hits = sum(len(re.findall(p, sample, re.I)) for p in entry["patterns"])
            if hits:
                models[key] += hits * 0.2
    if not harness_votes:
        if re.search(r"exported on .* from cursor", sample[:4000], re.I):
            harness_votes["cursor"] += 10
        for key, entry in catalog["harness"].items():
            hits = sum(len(re.findall(p, sample, re.I)) for p in entry["patterns"])
            if hits:
                harness_votes[key] += hits * 0.2

    def pick(counter, strong):
        if not counter:
            return UNKNOWN, "none", 0
        (key, top), total = counter.most_common(1)[0], sum(counter.values())
        share = top / total
        level = "high" if top >= strong and share >= 0.8 else "medium" if top >= 2 and share >= 0.6 else "low"
        return key, level, round(share, 3)

    model, model_conf, model_share = pick(models, 5)
    effort, effort_conf, _ = pick(efforts, 5)
    harness, harness_conf, _ = pick(harness_votes, 3)
    for key, count in raw_models.most_common(5):
        evidence.append(f"model 字段 {key} ×{count:g}")
    for key, count in efforts.most_common(3):
        evidence.append(f"effort {key} ×{count:g}")
    if not structured:
        evidence.append("非 JSON 轨迹，仅做文本匹配")
    times.sort()
    return {
        "model": model,
        "model_confidence": model_conf,
        "model_share": model_share,
        "models": dict(models.most_common(6)),
        "effort": effort,
        "effort_confidence": effort_conf,
        "harness": harness,
        "harness_confidence": harness_conf,
        "format": "jsonl" if structured and len(records) > 1 else "json" if structured else "text",
        "records": len(records),
        "messages": messages,
        "output_tokens": output_tokens,
        "started_at": int(times[0]) if times else None,
        "ended_at": int(times[-1]) if times else None,
        "duration_seconds": int(times[-1] - times[0]) if len(times) > 1 else None,
        "evidence": evidence[:10],
    }
