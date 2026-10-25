"""Model / effort / harness catalog and the ELO correction that each entry carries.

Adjusted ELO = raw ELO - (model offset + effort offset + harness offset): a
stronger model, a higher reasoning effort or a more capable agent harness costs
points so that bots written with weaker setups stay competitive. Entries are
seeded with INSERT OR IGNORE; the admin edits them afterwards in the database.
`patterns` are case-insensitive regular expressions used by `detect.py`.
"""
import json
import re

KINDS = ("model", "effort", "harness")
UNKNOWN = "unknown"

# (id, name, vendor, region, icon, offset, patterns)
MODELS = [
    ("claude-fable-5-1", "Claude Fable 5.1", "Anthropic", "us", "claude-color", 150, [r"claude-fable-5-1", r"fable[ -]?5\.1"]),
    ("claude-opus-5-5", "Claude Opus 5.5", "Anthropic", "us", "claude-color", 140, [r"claude-opus-5-5", r"opus[ -]?5\.5"]),
    ("claude-opus-5", "Claude Opus 5", "Anthropic", "us", "claude-color", 120, [r"claude-opus-5(?![-.]\d)", r"opus[ -]?5(?![.\d])"]),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Anthropic", "us", "claude-color", 100, [r"claude-sonnet-5-5", r"sonnet[ -]?5\.5"]),
    ("claude-haiku-5-5", "Claude Haiku 5.5", "Anthropic", "us", "claude-color", 40, [r"claude-haiku-5-5", r"haiku[ -]?5\.5"]),
    ("gpt-6.1-sol", "GPT-6.1 Sol", "OpenAI", "us", "openai", 140, [r"gpt-6\.1-sol"]),
    ("gpt-6-sol", "GPT-6 Sol", "OpenAI", "us", "openai", 130, [r"gpt-6-sol"]),
    ("gpt-6-astra", "GPT-6 Astra", "OpenAI", "us", "openai", 120, [r"gpt-6-astra"]),
    ("gpt-6-luna", "GPT-6 Luna", "OpenAI", "us", "openai", 70, [r"gpt-6-luna"]),
    ("gpt-5.6-sol", "GPT-5.6 Sol", "OpenAI", "us", "openai", 110, [r"gpt-5\.6-sol"]),
    ("gpt-5.6-terra", "GPT-5.6 Terra", "OpenAI", "us", "openai", 90, [r"gpt-5\.6-terra"]),
    ("gpt-5.6-luna", "GPT-5.6 Luna", "OpenAI", "us", "openai", 50, [r"gpt-5\.6-luna"]),
    ("gemini-3.1-pro", "Gemini 3.1 Pro", "Google", "us", "gemini-color", 100, [r"gemini-3\.1-pro"]),
    ("gemini-3.5-flash", "Gemini 3.5 Flash", "Google", "us", "gemini-color", 90, [r"gemini-3\.5-flash"]),
    ("grok-4.7", "Grok 4.7", "xAI", "us", "grok", 100, [r"grok-4\.7"]),
    ("grok-4.5", "Grok 4.5", "xAI", "us", "grok", 90, [r"grok-4\.5"]),
    ("composer-2.5", "Cursor Composer 2.5", "Cursor", "us", "cursor", 70, [r"composer-2\.5"]),
    ("kimi-k3", "Kimi K3", "月之暗面 Moonshot", "cn", "kimi-color", 110, [r"kimi-k3"]),
    ("qwen3.8-max", "Qwen3.8 Max", "阿里 通义千问", "cn", "qwen-color", 110, [r"qwen-?3\.8-max"]),
    ("qwen3.8", "Qwen3.8 开源版", "阿里 通义千问", "cn", "qwen-color", 80, [r"qwen-?3\.8(?!-max)"]),
    ("glm-5.3", "GLM-5.3", "智谱 Z.ai", "cn", "zhipu-color", 100, [r"glm-5\.3"]),
    ("deepseek-v4", "DeepSeek V4", "深度求索 DeepSeek", "cn", "deepseek-color", 100, [r"deepseek-v4(?!\.1-flash)", r"deepseek-(chat|reasoner)"]),
    ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "深度求索 DeepSeek", "cn", "deepseek-color", 70, [r"deepseek-v4\.1-flash"]),
    ("minimax-m3", "MiniMax M3", "MiniMax", "cn", "minimax-color", 80, [r"minimax-m3"]),
    ("mimo-v2.6-pro", "MiMo-V2.6-Pro", "小米 Xiaomi", "cn", "xiaomimimo", 100, [r"mimo-v2\.6-pro"]),
    ("doubao-seed", "豆包 Seed", "字节跳动 ByteDance", "cn", "doubao-color", 70, [r"doubao-seed"]),
    ("hunyuan", "混元 Hunyuan", "腾讯 Tencent", "cn", "hunyuan-color", 50, [r"hunyuan"]),
    ("ernie", "文心 ERNIE", "百度 Baidu", "cn", "wenxin-color", 50, [r"ernie-"]),
    ("step", "阶跃 Step", "阶跃星辰 StepFun", "cn", "stepfun-color", 50, [r"\bstep-\d"]),
    (UNKNOWN, "未知 / 其他模型", "", "", "", 120, []),
]

EFFORTS = [
    ("none", "关闭推理", -60, [r"none", r"off", r"disabled?"]),
    ("minimal", "Minimal", -40, [r"minimal"]),
    ("low", "Low", -25, [r"low"]),
    ("medium", "Medium", 0, [r"medium", r"med"]),
    ("high", "High", 25, [r"high"]),
    ("xhigh", "X-High", 45, [r"x-?high", r"extra[-_ ]?high"]),
    ("max", "Max", 60, [r"max"]),
    ("ultra", "Ultra", 75, [r"ultra"]),
    (UNKNOWN, "未知", 25, []),
]

# (id, name, vendor, region, icon, offset, patterns) — patterns are only a weak
# text fallback; structured signatures in detect.py are checked first.
HARNESSES = [
    ("claude-code", "Claude Code", "Anthropic", "us", "claudecode-color", 30, [r"claude[- ]code"]),
    ("codex", "Codex", "OpenAI", "us", "codex-color", 30, [r"codex[-_ ](cli|tui|exec|desktop)", r"codex_cli_rs"]),
    ("antigravity", "Antigravity", "Google", "us", "antigravity-color", 25, [r"antigravity"]),
    ("gemini-cli", "Gemini CLI", "Google", "us", "geminicli-color", 25, [r"gemini[- ]cli"]),
    ("cursor", "Cursor", "Cursor", "us", "cursor", 20, [r"from cursor", r"cursor agent"]),
    ("github-copilot", "GitHub Copilot", "GitHub", "us", "githubcopilot", 15, [r"github copilot", r"copilot-chat"]),
    ("cline", "Cline", "Cline", "us", "cline", 20, [r"\bcline\b"]),
    ("roo-code", "Roo Code", "Roo", "us", "roocode", 20, [r"roo[- ]?code"]),
    ("kilo-code", "Kilo Code", "Kilo", "us", "kilocode", 20, [r"kilo[- ]?code"]),
    ("opencode", "OpenCode", "SST", "us", "opencode", 25, [r"\bopencode\b"]),
    ("windsurf", "Windsurf", "Cognition", "us", "windsurf", 20, [r"windsurf", r"\bcascade\b"]),
    ("trae", "Trae", "字节跳动 ByteDance", "cn", "trae-color", 20, [r"\btrae\b"]),
    ("qoder", "Qoder", "阿里巴巴 Alibaba", "cn", "qoder-color", 20, [r"\bqoder\b"]),
    ("codebuddy", "CodeBuddy", "腾讯 Tencent", "cn", "codebuddy-color", 20, [r"codebuddy"]),
    ("kimi-cli", "Kimi CLI", "月之暗面 Moonshot", "cn", "kimi-color", 25, [r"kimi[-_ ]cli"]),
    ("qwen-code", "Qwen Code", "阿里 通义千问", "cn", "qwen-color", 25, [r"qwen[-_ ]code"]),
    ("iflow-cli", "iFlow CLI", "阿里巴巴 Alibaba", "cn", "alibaba-color", 25, [r"iflow"]),
    ("lingma", "通义灵码 Lingma", "阿里云 Alibaba Cloud", "cn", "qwen-color", 15, [r"lingma", r"通义灵码"]),
    ("comate", "文心快码 Comate", "百度 Baidu", "cn", "baidu-color", 15, [r"comate", r"文心快码"]),
    ("chat-web", "网页 / App 对话", "", "", "", 0, []),
    ("api", "直接调用 API / 自建脚本", "", "", "openrouter-color", 10, []),
    (UNKNOWN, "未知 / 其他平台", "", "", "", 30, []),
]

SCHEMA = """CREATE TABLE IF NOT EXISTS catalog(
    kind TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, vendor TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '', elo_offset REAL NOT NULL DEFAULT 0,
    patterns TEXT NOT NULL DEFAULT '[]', sort INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(kind,id))"""


def seed(db):
    db.execute(SCHEMA)
    rows = []
    for index, (key, name, vendor, region, icon, offset, patterns) in enumerate(MODELS):
        rows.append(("model", key, name, vendor, region, icon, offset, patterns, index))
    for index, (key, name, offset, patterns) in enumerate(EFFORTS):
        rows.append(("effort", key, name, "", "", "", offset, patterns, index))
    for index, (key, name, vendor, region, icon, offset, patterns) in enumerate(HARNESSES):
        rows.append(("harness", key, name, vendor, region, icon, offset, patterns, index))
    db.executemany(
        "INSERT OR IGNORE INTO catalog(kind,id,name,vendor,region,icon,elo_offset,patterns,sort) VALUES(?,?,?,?,?,?,?,?,?)",
        [(*row[:7], json.dumps(row[7]), row[8]) for row in rows],
    )


def load(db, enabled_only=False):
    """{kind: {id: entry}} in display order."""
    result = {kind: {} for kind in KINDS}
    where = " WHERE enabled=1" if enabled_only else ""
    for row in db.execute(f"SELECT * FROM catalog{where} ORDER BY kind,sort,name"):
        item = dict(row)
        item["patterns"] = json.loads(item["patterns"])
        item["enabled"] = bool(item["enabled"])
        result[item["kind"]][item["id"]] = item
    return result


def valid_patterns(patterns):
    if not isinstance(patterns, list) or len(patterns) > 12:
        return False
    try:
        for pattern in patterns:
            if not isinstance(pattern, str) or len(pattern) > 120:
                return False
            re.compile(pattern, re.I)
    except re.error:
        return False
    return True


def offset(catalog, kind, key):
    entries = catalog[kind]
    entry = entries.get(key or UNKNOWN) or entries.get(UNKNOWN)
    return float(entry["elo_offset"]) if entry else 0.0
