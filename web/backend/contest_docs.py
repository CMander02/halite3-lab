"""Written rules, the problem prompt and the downloadable problem kit of a contest.

The rules are generated from the frozen contest configuration (so the text can
never disagree with what the runner plays), followed by the admin's own extra
rules. The kit is one ZIP an agent can work from: PROMPT.md, RULES.md, the
public maps (seed, size, rules file and the rendered terrain / halite), the
downloadable reference bots, a C++ starter and the CLI for submitting.
"""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
from . import settings as S

BEIJING = timezone(timedelta(hours=8))
MODE_NAMES = {2: "1v1", 4: "4 人混战", 8: "8 人混战"}
STAMP = (2026, 1, 1, 0, 0, 0)


def when(t):
    return datetime.fromtimestamp(t, BEIJING).strftime("%Y-%m-%d %H:%M") + "（北京时间）"


def mechanics(rules):
    """Game rules implied by one mode's rule flags."""
    lines = []
    if rules.get("FOG_ENABLED"):
        lines.append(f"- **迷雾**：只看得到己方船、基地和 dropoff 周围曼哈顿距离 {rules.get('VISION_RADIUS', 4)} 以内的格子。视野外的矿量是 `null`，敌方银行隐藏，只发送视野内的敌船。")
    else:
        lines.append("- 无迷雾：全图可见。")
    if rules.get("REEF_PERCENT"):
        layout = "与矿量、基地一样镜像对称，每个出生点看到的地形完全相同" if rules.get("MIRROR_REEFS") else "按玩家分区复制"
        lines.append(f"- **礁石**：约 {rules['REEF_PERCENT']}% 候选格是礁石（{layout}）。礁石不可通行、没有矿、不能建造；移动撞礁按原地停留处理，不扣移动费，照常采矿。所有海面保证连通。")
    if rules.get("LIGHT_SHIP_COLLISIONS"):
        lines.append("- **轻船撞沉重船**：同一格的碰撞按移动扣费后的载矿量比较，唯一最轻的船存活并抢走被撞沉船的全部货物（超出 1000 的部分落地）。最轻重量并列时该格全部沉没，货物变成地面矿。友军之间同样适用，出生点碰撞也一样。")
    else:
        lines.append("- 碰撞沿用原版 Halite III：相撞全部沉没。")
    k = rules.get("PILEUP_WRECK_SIZE", 0)
    if k and k >= 2:
        lines.append(f"- **多船连撞**：同一格同时有 {k} 艘及以上的船时，不论重量和归属全部沉没，货物原地变成地面矿，包括基地格。")
    lines.append("- 其余沿用 Halite III：造船 1000、dropoff 4000、移动扣源格矿量的 1/10、inspiration 开启，回合结束时银行矿量多者名次靠前。")
    return lines


def rules_markdown(row, config):
    practice = config.get("practice")
    targets = len(config["targets"])
    out = [f"# #{row['number']} {row['title']} · 比赛规则", ""]
    out += ["## 时间", ""]
    if practice:
        out += ["- 常驻测试赛：随时可以提交，没有截止时间、隐藏地图和正式评测。", ""]
    else:
        if row["visible_at"]:
            out.append(f"- 开放浏览：{when(row['visible_at'])}")
        out += [f"- 开放提交：{when(row['open_at'])}", f"- 提交截止：{when(row['close_at'])}",
                "- 截止后自动进行正式评测，全部完成后公布结果。", ""]
    names = " / ".join({"cpp": "C++17", "python": "Python 3.12"}[x] for x in config["languages"])
    out += ["## 提交", "",
            f"- 只接受单文件 `bot.cpp`（{names}，文件名必须是 `bot.cpp`）。服务器用 `g++ -std=c++17 -O2` 编译，只提供标准库和 `<nlohmann/json.hpp>`。" if config["languages"] == ["cpp"]
            else f"- 只接受单文件 `bot.cpp` 或 `bot.py`（{names}），文件名必须规范。",
            "- 可以同时上传生成这个 bot 的 Agent 对话轨迹（Claude Code / Codex 会话 JSONL 等，可选）。轨迹只用来确定模型和推理强度，只有作者和管理员能看；不上传时按你声明的模型 / 推理强度 / 平台计算修正。",
            f"- 每人最多提交 {config['max_submissions']} 次，每次提交是一个不可覆盖的新版本。网页上传、或让 Agent 用 API Token 提交都可以；用同一个 Bot 名字提交就是在同一个 Bot 上迭代。",
            ]
    if not practice:
        out.append("- 最后一次提交默认参加正式评测；提交窗口内可以改选任意一次历史提交。")
    out.append("")
    out += ["## 评测与排名", ""]
    rotate = config.get("bench_rotate", True)
    out.append(f"- **{'每次提交' if practice else '提交期'}**：你的 bot 只和 {targets} 个靶子在公开地图上对战" + ("（1v1 交换座位；多人局轮换座位）。" if rotate else "。")
               + ("成绩立即公开并计入全局 ELO。" if practice else "得到临时 ELO，选手之间此时不对战。"))
    if not practice:
        out.append(f"- **正式评测**：每人参加评测的版本 + 靶子，在公开地图和隐藏地图上对战。1v1 是双循环、交换座位；多人局每张地图随机分组 {config.get('final_rounds', 4)} 轮。")
        out.append("- **结果**：正式评测完成后排名冻结，隐藏地图揭晓，所有比赛对局与回放公开，并计入全局 ELO。")
    out.append("- **ELO**：对每局按名次两两比较，做 Bradley–Terry 拟合（多人局每对权重 1/(n−1)，锚点 1500）。修正后 ELO = 原始 ELO − 模型修正 − 推理强度修正 − 平台修正，按修正后 ELO 排名。靶子不参与排名。")
    out.append("")
    for mode in config["modes"]:
        setup = config["setups"][str(mode)]
        out += [f"## {MODE_NAMES[mode]}", "",
                f"- 地图 {setup['width']}×{setup['height']}，{setup['turns']} 回合，单场时限 {setup['seconds']} 秒；公开地图种子 {', '.join(map(str, config['public_maps'][str(mode)]))}"
                + (f"，另有 {len(config['hidden_maps'].get(str(mode), []))} 张隐藏地图" if config["hidden_maps"].get(str(mode)) else "") + "。",
                *mechanics(setup["rules"]), ""]
    out += ["## 协议与运行环境", "",
            "- 每回合从 stdin 读一行 JSON（`halite3-lab-v1` 协议），向 stdout 回一行 Halite III 动作（`m <id> <n|s|e|w|o>`、`c <id>`、`g`），每行都要 flush。首行 init 后先回一行 bot 名字。日志写 stderr。",
            "- 完整协议见题目包里的 `PROTOCOL.md`。",
            "- 每个 bot 进程：192 MiB 内存、单核 35% CPU、无网络、只读自己的文件。超时、崩溃或输出非法动作的 bot 会被引擎终止，这一局按 Halite III 规则排名（通常垫底）。",
            ""]
    if row["rules"].strip():
        out += ["## 补充规则", "", row["rules"].strip(), ""]
    return "\n".join(out)


DEFAULT_PROMPT = """你要为一个魔改版 Halite III 写一个 bot，参加比赛「{title}」。

- 魔改点：迷雾（只看得到附近）、礁石地形、轻船撞沉重船并抢走货物{pileup}。规则以 RULES.md 为准，协议见 PROTOCOL.md。
- 交付物：一个单文件 `bot.cpp`（C++17，只能用标准库和 nlohmann/json）。从 `starter/bot.cpp` 开始。
- 本地测试：用 `maps/` 里的公开地图（种子 + 规则文件）和 `bots/` 里的参考 bot 对战，见 README.md。
- 目标：在全部人数模式（{modes}）里尽量拿第一，修正后 ELO 越高越好。正式评测还有隐藏地图，不要只针对公开地图调参。
"""


def prompt_markdown(row, config, origin):
    pileup = "；4 人局三船以上同格全部沉没" if any(config["setups"][str(m)]["rules"].get("PILEUP_WRECK_SIZE") for m in config["modes"]) else ""
    task = row["prompt"].strip() or DEFAULT_PROMPT.format(
        title=row["title"], pileup=pileup, modes=" / ".join(MODE_NAMES[m] for m in config["modes"]))
    submit = f"""## 提交

网页：比赛页 {origin}/contests/{row['slug']} →「我的提交」上传 `bot.cpp`（轨迹可选）。

让 Agent 自己提交（需要 API Token，在网站「账号与头像」创建，30 天有效）：

```bash
export HALITE_TOKEN=h3_...            # 不要写进代码或提交记录
python3 tools/client.py --origin {origin} contest-submit {row['slug']} bot.cpp --bot my-bot \\
    --model <模型 id> --effort <推理强度> --harness <平台> [--trace 会话.jsonl] [--note "这次改了什么"]
python3 tools/client.py --origin {origin} contest-status {row['slug']}   # 看评测进度和临时 ELO
python3 tools/client.py --origin {origin} catalog                        # 模型 / 推理强度 / 平台的 id
```

每次用同一个 `--bot` 名字提交，就是在同一个 Bot 上迭代出新版本；每人最多提交 {config['max_submissions']} 次。
"""
    return f"# #{row['number']} {row['title']} · 题目\n\n{task.strip()}\n\n{submit}"


def render_map(mode, seed, setup):
    """Terrain, halite and factories of one map, by running the engine for one turn
    with idle local players (our own trivial script, not uploaded code). None if the
    engine is unavailable."""
    if not S.ENGINE.is_file():
        return None
    with tempfile.TemporaryDirectory() as work:
        idle = f"{work}/idle.py"
        with open(idle, "w") as f:
            f.write("import sys\nsys.stdin.readline()\nprint('idle',flush=True)\nfor _ in sys.stdin: print('',flush=True)\n")
        with open(f"{work}/rules.json", "w") as f:
            json.dump(setup["rules"], f)
        argv = [str(S.ENGINE), "--results-as-json", "--no-compression", "--width", str(setup["width"]), "--height", str(setup["height"]),
                "--turn-limit", "1", "--seed", str(seed), "-c", f"{work}/rules.json", "-i", work,
                *[f"python3 -B {idle}" for _ in range(mode)]]
        try:
            subprocess.run(argv, cwd=work, capture_output=True, timeout=60, check=True)
            replay = next(Path(work).glob("*.hlt"))
            data = json.loads(replay.read_bytes())
        except (subprocess.SubprocessError, StopIteration, ValueError, OSError):
            return None
    grid = data["production_map"]["grid"]
    return {
        "mode": mode, "seed": seed, "width": setup["width"], "height": setup["height"], "turns": setup["turns"],
        "factories": [[p["factory_location"]["x"], p["factory_location"]["y"]] for p in data["players"]],
        "note": "行优先：index = y * width + x；reef 为 1 的格子是礁石。",
        "halite": [cell["energy"] for row in grid for cell in row],
        "reef": [int(bool(cell.get("reef"))) for row in grid for cell in row],
    }


def cached_map(contest_id, mode, seed, setup):
    directory = S.DATA / "contest-maps" / contest_id
    path = directory / f"{mode}-{seed}.json"
    if path.is_file():
        return json.loads(path.read_text())
    data = render_map(mode, seed, setup)
    if data:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(data, separators=(",", ":")))
    return data


def readme(row, config, origin, bots, maps_rendered):
    slug = row["slug"]
    lines = [f"# #{row['number']} {row['title']} · 题目包", "",
             f"比赛页：{origin}/contests/{slug}", "",
             "## 内容", "",
             "- `PROMPT.md`：题目（可以直接交给 Agent）",
             "- `RULES.md`：比赛规则",
             "- `PROTOCOL.md`：bot 输入输出协议",
             "- `starter/bot.cpp`：C++ 起点（贪心采矿）",
             "- `maps/manifest.json`：公开地图（种子、尺寸、回合、时限、规则文件）"
             + ("；`maps/<人数>-<种子>.json` 是渲染好的地形和矿量" if maps_rendered else ""),
             "- `maps/rules-<人数>.json`：对应人数模式的引擎规则文件",
             "- `bots/`：参考 bot 源码" + ("（" + "、".join(bots) + "）" if bots else "（本场没有开放下载）"),
             "- `tools/client.py`：上传和提交用的命令行工具", "",
             "## 本地对战", "",
             "引擎在 https://github.com/CMander02/halite3-lab （`game_engine/`），按仓库 README 编译出 `build/halite`。", "",
             "```bash"]
    for mode in config["modes"]:
        setup = config["setups"][str(mode)]
        seed = config["public_maps"][str(mode)][0]
        players = ['"./bot"'] + [f'"python3 bots/<参考 bot>/bot.py"'] * (mode - 1)
        lines.append(f"# {MODE_NAMES[mode]}")
        lines.append(f"./build/halite --width {setup['width']} --height {setup['height']} --turn-limit {setup['turns']} --seed {seed} -c maps/rules-{mode}.json -i replays/ {' '.join(players)}")
    lines += ["```", "", "先 `g++ -std=c++17 -O2 -o bot bot.cpp` 编译（需要 nlohmann/json）。回放写在 `replays/`，可以在网站回放页之外用任意 H3 回放工具查看。", ""]
    return "\n".join(lines)


def kit(db, row, config, origin, version_rows):
    """The problem kit ZIP as bytes."""
    buffer = io.BytesIO()

    def put(name, data):
        info = zipfile.ZipInfo(f"{row['slug']}/{name}", date_time=STAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, data)

    offered = list(dict.fromkeys(([config["base_version_id"]] if config["base_version_id"] else []) + config["downloads"]))
    rows = version_rows(db, offered)
    with zipfile.ZipFile(buffer, "w") as archive:
        bots = []
        for vid in offered:
            v = rows.get(vid)
            if not v or not v["object_key"] or not (S.DATA / v["object_key"]).is_file():
                continue
            folder = f"bots/{v['name']}-v{v['version']}"
            bots.append(f"{v['name']} v{v['version']}")
            source = (S.DATA / v["object_key"]).read_bytes()
            if v["filename"].lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(source)) as inner:
                    for item in inner.infolist():
                        if not item.is_dir():
                            put(f"{folder}/{item.filename}", inner.read(item))
            else:
                put(f"{folder}/{v['filename']}", source)
        manifest, rendered = [], False
        for mode in config["modes"]:
            setup = config["setups"][str(mode)]
            put(f"maps/rules-{mode}.json", json.dumps(setup["rules"], indent=2))
            for seed in config["public_maps"][str(mode)]:
                item = {"mode": mode, "seed": seed, "width": setup["width"], "height": setup["height"], "turns": setup["turns"],
                        "seconds": setup["seconds"], "rules": f"rules-{mode}.json"}
                data = cached_map(row["id"], mode, seed, setup)
                if data:
                    rendered = True
                    item["map"] = f"{mode}-{seed}.json"
                    put(f"maps/{mode}-{seed}.json", json.dumps(data, separators=(",", ":")))
                manifest.append(item)
        put("maps/manifest.json", json.dumps({"public_maps": manifest, "hidden_maps": {
            str(m): len(config["hidden_maps"].get(str(m), [])) for m in config["modes"]}}, indent=2, ensure_ascii=False))
        put("README.md", readme(row, config, origin, bots, rendered))
        put("PROMPT.md", prompt_markdown(row, config, origin))
        put("RULES.md", rules_markdown(row, config))
        put("PROTOCOL.md", (S.PROJECT / "lab/RULES.md").read_text())
        put("starter/bot.cpp", (S.ROOT / "examples/cpp/main.cpp").read_text())
        put("tools/client.py", (S.ROOT / "client.py").read_text())
    return buffer.getvalue()
