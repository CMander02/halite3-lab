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


# Engine defaults (game_engine/config/Constants.hpp). A mode's rules file overrides them.
ENGINE_DEFAULTS = {
    "FOG_ENABLED": False, "VISION_RADIUS": 4, "REEF_PERCENT": 0, "LIGHT_SHIP_COLLISIONS": False,
    "PILEUP_WRECK_SIZE": 0, "MIRROR_REEFS": False,
    "INITIAL_ENERGY": 5000, "NEW_ENTITY_ENERGY_COST": 1000, "DROPOFF_COST": 4000, "MAX_ENERGY": 1000,
    "MOVE_COST_RATIO": 10, "EXTRACT_RATIO": 4,
    "INSPIRATION_ENABLED": True, "INSPIRATION_RADIUS": 4, "INSPIRATION_SHIP_COUNT": 2,
    "INSPIRED_BONUS_MULTIPLIER": 2, "INSPIRED_EXTRACT_RATIO": 4, "INSPIRED_MOVE_COST_RATIO": 10,
}
TURN_SECONDS = 2  # NetworkingConfig::timeout
INIT_SECONDS = 30  # Networking::initialize_player


def constants(rules):
    return {**ENGINE_DEFAULTS, **rules}


def tiling(players):
    """(columns, rows) of player tiles: the fractal generator mirrors across the y axis, then the x axis, repeatedly."""
    cols = rows = tiles = 1
    while tiles < players:
        cols, tiles = cols * 2, tiles * 2
        if tiles == players:
            break
        rows, tiles = rows * 2, tiles * 2
    return cols, rows


def factories(players, width, height):
    """Factory of each seat, in seat order, as game_engine/mapgen/SymmetricalTile.cpp places them."""
    cols, rows = tiling(players)
    tw, th = width // cols, height // rows
    x, y = tw // 2, th // 2
    if 16 <= tw <= 40 and 16 <= th <= 40:
        x = int(8 + (tw - 16) / 24 * 20)
        if players > 2:
            y = int(8 + (th - 16) / 24 * 20)
    spots, w, h, n = [(x, y)], tw, th, 1
    while n < players:
        spots += [(2 * w - 1 - fx, fy) for fx, fy in spots]
        w, n = w * 2, n * 2
        if n == players:
            break
        spots += [(fx, 2 * h - 1 - fy) for fx, fy in spots]
        h, n = h * 2, n * 2
    return spots


def distance(a, b, width, height):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return min(dx, width - dx) + min(dy, height - dy)


def map_lines(mode, setup):
    w, h = setup["width"], setup["height"]
    cols, rows = tiling(mode)
    spots = factories(mode, w, h)
    seats = "、".join(f"P{i} ({x},{y})" for i, (x, y) in enumerate(spots))
    nearest = min(distance(spots[0], other, w, h) for other in spots[1:])
    layout = {2: "左右两块", 4: "2×2 四块", 8: "4 列 × 2 行八块"}.get(mode, f"{cols} 列 × {rows} 行")
    return [
        f"- **地图**：{w}×{h}，{setup['turns']} 回合，单场时限 {setup['seconds']} 秒。地图按玩家分成{layout}，每人一块 {w // cols}×{h // rows} 的分区，矿量和基地在分区之间镜像对称。",
        f"- **基地（factory）**：座位号就是玩家编号，P0 用第一个基地。{seats}。离最近的对手基地 {nearest} 格。",
    ]


def mechanics(rules):
    """Game rules implied by one mode's rule flags."""
    c = constants(rules)
    lines = []
    if c["FOG_ENABLED"]:
        lines.append(f"- **迷雾**：只看得到己方船、基地和 dropoff 周围曼哈顿距离 {c['VISION_RADIUS']} 以内的格子。视野外的矿量是 `null`，敌方银行隐藏，只发送视野内的敌船和敌方 dropoff。")
    else:
        lines.append("- 无迷雾：全图可见。")
    if c["REEF_PERCENT"]:
        layout = "与矿量、基地一样镜像对称，每个出生点看到的地形完全相同" if c["MIRROR_REEFS"] else "按分区平移复制。矿量是镜像的，所以各座位周围的礁石不完全一样，靠座位轮换抵消"
        lines.append(f"- **礁石**：约 {c['REEF_PERCENT']}% 候选格是礁石（{layout}）。礁石不可通行、没有矿、不能建造；移动撞礁按原地停留处理，不扣移动费，照常采矿。所有海面保证连通。")
    if c["LIGHT_SHIP_COLLISIONS"]:
        lines.append(f"- **轻船撞沉重船**：同一格的碰撞按移动扣费后的载矿量比较，唯一最轻的船存活并抢走被撞沉船的全部货物（超出 {c['MAX_ENERGY']} 的部分落地）。最轻重量并列时该格全部沉没，货物变成地面矿。友军之间同样适用，出生点碰撞也一样。")
    else:
        lines.append("- 碰撞沿用原版 Halite III：相撞全部沉没。")
    k = c["PILEUP_WRECK_SIZE"]
    if k and k >= 2:
        lines.append(f"- **多船连撞**：同一格同时有 {k} 艘及以上的船时，不论重量和归属全部沉没，货物原地变成地面矿，包括基地格。")
    lines.append(f"- 其余沿用 Halite III：造船 {c['NEW_ENTITY_ENERGY_COST']}、dropoff {c['DROPOFF_COST']}、移动扣源格矿量的 1/{c['MOVE_COST_RATIO']}、inspiration {'开启' if c['INSPIRATION_ENABLED'] else '关闭'}，回合结束时银行矿量多者名次靠前。")
    return lines


def game_rules(config):
    """The full game rules, worded from the rules files of the contest's modes."""
    if config.get('experimental'):
        lines = ['## 规则实验与固定 Bot', '', '本比赛由 txcloud 执行，使用现有版本，不修改 Bot 源码。各规则变体分别统计，综合新规则为主排行，不计入 #0 或全局 ELO。',
                 '', '初始格矿上限在整数经济变体中为 15；碰撞回流矿可超过 15，不丢弃资源。运输船与侦察船交替自动出生，旧 Bot 仍使用原有 g 指令；侦察船具有独立容量与视野。',
                 '', '不同变体沿用对应的结算顺序：建落点、移动、碰撞、自动卸货、出生、采矿。生产限制拒绝出生时不收费。',
                 '', '## 全部实验配置', '']
        if config.get('execution_batches'):
            lines += ['## 执行批次与限时', '']
            for batch in config['execution_batches']:
                lines += [f"- {batch['label']}：每个 Bot 每回合回复限时 {batch['turn_timeout_ms']} 毫秒；单 Bot CPU 配额 {batch['bot_cpu_percent']}%。各批次分别统计，已完成的旧结果保留。"]
            lines += ['']
        for case in config['scenarios']:
            lines += [f"### {case['label']} (`{case['key']}`)", '']
            for mode, setup in case['setups'].items():
                lines += [f"- {mode} 人：{setup['width']}×{setup['height']}，{setup['turns']} 步；地形种子 {case['map_seeds']}。"]
            lines += ['', '```json', json.dumps(case['setups']['8']['rules'], ensure_ascii=False, indent=2), '```', '']
        return lines
    setups = [config["setups"][str(m)] for m in config["modes"]]
    cs = [constants(s["rules"]) for s in setups]
    c = cs[0]
    names = [MODE_NAMES[m] for m in config["modes"]]

    def where(flag, test=bool):
        """'' when every mode agrees on a flag, else which modes have it."""
        on = [n for n, x in zip(names, cs) if test(x[flag])]
        return "" if len(on) == len(cs) else "（仅 " + " / ".join(on) + "）"

    cap, ship, dropoff = c["MAX_ENERGY"], c["NEW_ENTITY_ENERGY_COST"], c["DROPOFF_COST"]
    move, extract, radius = c["MOVE_COST_RATIO"], c["EXTRACT_RATIO"], c["INSPIRATION_RADIUS"]
    bonus = c["INSPIRED_BONUS_MULTIPLIER"]
    fog = [x for x in cs if x["FOG_ENABLED"]]
    reef = [x for x in cs if x["REEF_PERCENT"]]
    light = [x for x in cs if x["LIGHT_SHIP_COLLISIONS"]]
    pileup = sorted({x["PILEUP_WRECK_SIZE"] for x in cs if x["PILEUP_WRECK_SIZE"] >= 2})
    smallest_pileup = min(pileup) if pileup else None
    out = ["## 游戏目标", "",
           f"- 每个玩家有一个基地（factory），开局银行 {c['INITIAL_ENERGY']} 矿。用银行里的矿造船，船到海面上采矿，再运回自己的基地或 dropoff 卸货，卸下的矿进入银行。",
           "- **最后一回合结束时银行矿量最多的玩家第一。** 船上没卸的货、dropoff 都不计分。",
           "- 所有玩家同时行动：每回合每个 bot 读一帧观测、回一行指令，引擎统一结算。",
           "",
           "## 地图",
           "",
           "- 坐标原点在左上角，x 向东增大，y 向南增大：north 是 y−1，south 是 y+1，east 是 x+1，west 是 x−1。地图上下、左右都环绕，距离指环绕后的曼哈顿距离。",
           "- 矿量由地图种子用分形噪声生成：先生成一块分区，再镜像复制给其他玩家，所以每家分区的初始矿量分布完全对称。基地格初始为 0。矿不会再生，只会被采走，或因沉船增加。",
           "- 各人数模式的地图大小和基地坐标见下文对应小节。"]
    if reef:
        out.append(f"- **礁石**{where('REEF_PERCENT')}：生成器按分区逐格抽签，命中的格子连同它在其他分区的对应格一起变成礁石；基地曼哈顿距离 2 以内不放；放下后若海面不再连通就撤掉这一组。礁石没有矿，不可通行，不能建造。地形在开局时全部告诉 bot。")
    out += ["",
            "## 经济",
            "",
            f"- **造船** `g`：花 {ship}，在自己的基地格生成一艘空船。每回合最多一次。",
            f"- **船**：载货上限 {cap}。船本身不会因为时间或移动消失，只会在碰撞中沉没、或被改建成 dropoff。",
            f"- **建 dropoff** `c <船 id>`：这艘船原地变成你的 dropoff，船消失。价格是 {dropoff} 减去（这艘船的货 + 该格地面矿），最低为 0。实际结算是货和地面矿全部入银行、再扣 {dropoff}，所以两者合计超过 {dropoff} 时多出来的部分也归你。不能建在已有基地或 dropoff 的格子上，不论是谁的（会被判负）。dropoff 永久存在、不能被摧毁，任何人的船都可以停在上面。",
            f"- **预算**：一回合里造船和所有 dropoff 的花费合计不能超过回合开始时的银行余额，超了直接判负。本回合卸下的矿要下一回合才能花。",
            "",
            "## 每回合的结算顺序",
            "",
            f"- **1. 观测**：引擎把回合开始时的局面发给每个 bot，等它回指令（每回合 {TURN_SECONDS} 秒）。inspiration 也在这时按回合开始时的位置判定。",
            "- **2. 建 dropoff**。",
            "- **3. 移动**：所有移动同时进行，并扣除移动费。",
            "- **4. 碰撞**：结束时落在同一格的船结算碰撞。",
            "- **5. 卸货**：停在自己基地或 dropoff 上的船，全部货物自动进入银行。",
            "- **6. 造船**：新船出现在基地格，结算出生点碰撞。",
            "- **7. 采矿**：本回合没有移动成功、没有卸货、不是新船、没有卷入碰撞的船，在原地采矿。",
            "- **8. 判断是否结束**。",
            "",
            "## 移动",
            "",
            "- `m <船 id> <n|s|e|w|o>`：向北、南、东、西移动一格，`o` 是停留。没收到指令的船也停留。每艘船每回合最多一条指令。",
            f"- **移动费**：离开的那一格（源格）地面矿量 ÷ {move}，向下取整，从船的货里扣。进入自己的基地或 dropoff 没有额外费用。",
            "- 船的货不够付移动费时，这条移动被忽略，船留在原地（照常采矿），不算违规。",
    ]
    if reef:
        out.append(f"- 目标是礁石{where('REEF_PERCENT')}：按停留处理，不扣移动费，照常采矿。")
    out += ["- 碰撞只看移动后的位置：两船互换位置不会相撞；一艘船进入另一艘船同回合刚离开的格子也不会相撞。原地不动的船如果有别的船移入，同样卷入碰撞。",
            "",
            "## 采矿",
            "",
            f"- 停在原地的船采走该格地面矿的 1/{extract}（向上取整），不超过船的剩余容量。货满 {cap} 的船不采矿。",
            "- 移动成功的船、新船、卷入碰撞的船本回合不采矿。停在自己基地或 dropoff 上的船每回合都在卸货，所以也不采矿。"]
    if c["INSPIRATION_ENABLED"]:
        out += [f"- **inspiration**：回合开始时，如果一艘船曼哈顿距离 {radius} 以内（含）共有至少 {c['INSPIRATION_SHIP_COUNT']} 艘敌船（不分属于哪个对手），这艘船本回合 inspired：采矿时格子照常只减少采走的量，船额外得到 {bonus:g} 倍奖励，也就是总共拿到 {1 + bonus:g} 倍，不超过容量。移动费不变。",
                "- 观测里不直接标出 inspired，需要 bot 自己算。"
                + (f"半径 {radius} 以内的敌船总在你的视野里。" if fog and all(x["VISION_RADIUS"] >= radius for x in fog) else "")]
    out += ["", "## 碰撞", ""]
    if light:
        out += [f"- 结算移动后，落在同一格的所有船互相碰撞，不论归属，友军之间也一样{where('LIGHT_SHIP_COLLISIONS')}。",
                f"- **轻船存活**：比较移动扣费后的载货量，唯一最轻的船存活，留在该格，抢走其余船的全部货物；超出容量 {cap} 的部分变成该格地面矿。",
                "- **最轻并列**：该格的船全部沉没，所有货物变成该格地面矿。只有最轻的并列才算：两船载 0 和 500 → 载 0 的存活并拿走 500；两船都载 300 → 都沉，600 落地。"]
        if any(not 2 <= x["PILEUP_WRECK_SIZE"] <= 3 for x in light):
            only = "（未开启多船连撞时）" if smallest_pileup and smallest_pileup <= 3 else ""
            out.append(f"- 三艘船的例子{only}：载 100、300、300 → 载 100 的存活（并列的是两艘重船，不影响）；载 100、100、300 → 全部沉没。")
        if smallest_pileup:
            out.append(f"- **多船连撞**{where('PILEUP_WRECK_SIZE', lambda k: k >= 2)}：同一格同时有 {smallest_pileup} 艘及以上的船时，不比重量，全部沉没，所有货物原地变成地面矿，没有人抢到。这条优先于轻船规则。")
        out += ["- 地面矿落在基地或 dropoff 格时仍然只是地面矿，不会自动进任何人的银行。你自己的船停在自家建筑上总在卸货、不采矿，所以只有对手的船能采走它。在自家建筑格撞赢的己方船，会在接下来的卸货步骤把抢到的货一起存进银行。",
                "- **出生点碰撞**：造船在卸货之后。如果你的基地上已经停着一艘自己的船，它刚卸完货、载货 0，和新船并列，两艘都沉，造船费照扣。如果停着的是敌船：它有货时新船更轻，新船存活并抢走它的货；它空载时两艘都沉。",
                "- 沉没的船的货物不会消失：要么被存活者抢走，要么变成地面矿，可以再采。"]
    if len(light) < len(cs):
        out.append("- 未开启轻船规则的模式沿用原版：同一格的船全部沉没，货物落在该格；该格是某人的基地或 dropoff 时，货物直接进那个人的银行。")
    out += ["",
            "## 卸货",
            "",
            "- 卸货步骤时停在**自己**基地或 dropoff 上的船，全部货物自动进入银行，不需要指令。之后船可以继续出发。",
            "- 停在别人的基地或 dropoff 上不会卸货，也不会给对方。",
            ""]
    if fog:
        vision = sorted({x["VISION_RADIUS"] for x in fog})
        out += [f"## 迷雾与观测{where('FOG_ENABLED')}", "",
                f"- 你的视野是己方每艘船、基地和每个 dropoff 周围曼哈顿距离 {' / '.join(map(str, vision))} 以内（含）的格子的并集。",
                "- 每回合都会告诉你：完整地形、所有玩家的编号和基地坐标、自己的银行、自己全部的船（id、坐标、载货）和 dropoff、视野内的地面矿量。",
                "- 只在视野内才告诉你：敌船（含载货）、敌方 dropoff。视野外的矿量是 `null`，离开视野的格子会重新变成 `null`，需要的话自己记忆。",
                "- 不告诉你：敌方银行（`null`）、敌方船的总数、地图种子。",
                ""]
    out += ["## 违规与判负", "",
            "- 下列情况会被引擎**立即淘汰**：指挥不存在或不属于自己的船；同一艘船一回合收到多条指令；一回合多于一次 `g`；花费超过银行余额；在已有基地或 dropoff 的格子上 `c`；无法解析的指令；"
            f"一回合内没有回复（{TURN_SECONDS} 秒；开局回复名字限 {INIT_SECONDS} 秒）；崩溃或退出。",
            "- 被淘汰的玩家：所有船立刻消失（货物也消失，不落地），银行清零，之后不再行动；名次排在所有坚持到更晚回合的玩家之后。",
            "- 只忽略、不判负：货不够付移动费（船原地停留）；自己的船互撞（照常按碰撞规则结算）。",
            "",
            "## 结束与名次", "",
            "- 游戏在以下任一情况结束：打满回合上限；地图上已没有矿且所有船都空载；还能继续行动的玩家不超过 1 人。",
            f"- 「还能行动」指有船，或银行至少 {ship} 能造船。失去行动能力或被淘汰的玩家，在那一回合「出局」。",
            "- **名次**：先比出局回合，坚持到越晚越靠前（打满全程的玩家都算坚持到最后）；同一回合出局的，比那一回合结束时的银行矿量，多者靠前；仍然相同就往前逐回合比银行，全部相同时随机。",
            "- **得分**就是结束时的银行矿量。",
            ""]
    return out


def rules_markdown(row, config):
    if config.get('experimental'):
        return f"# #{row['number']} {row['title']} · 比赛规则\n\n" + '\n'.join(game_rules(config))
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
    if practice:
        out.append("- **排名**：每个 Bot 取最新一次提交的版本参加排名，同一个人的多个 Bot 分别排名。")
    else:
        out.append(f"- **正式评测**：每人参加评测的版本 + 靶子，在公开地图和隐藏地图上对战。1v1 是双循环、交换座位；多人局每张地图随机分组 {config.get('final_rounds', 4)} 轮。")
        out.append("- **结果**：正式评测完成后排名冻结，隐藏地图揭晓，所有比赛对局与回放公开，并计入全局 ELO。")
    out.append("- **ELO**：对每局按名次两两比较（名次相同算半胜），做 Bradley–Terry 拟合（多人局每对权重 1/(n−1)，锚点 1500）。每个版本另外对 1500 分的锚点各记一场虚拟胜负，所以全胜或全负的版本分数也是有限的。修正后 ELO = 原始 ELO − 模型修正 − 推理强度修正 − 平台修正，按修正后 ELO 排名。靶子不参与排名。")
    out.append("")
    out += game_rules(config)
    for mode in config["modes"]:
        setup = config["setups"][str(mode)]
        out += [f"## {MODE_NAMES[mode]}", "",
                *map_lines(mode, setup),
                f"- 公开地图种子 {', '.join(map(str, config['public_maps'][str(mode)]))}"
                + (f"，另有 {len(config['hidden_maps'].get(str(mode), []))} 张隐藏地图" if config["hidden_maps"].get(str(mode)) else "") + "。",
                *mechanics(setup["rules"]), ""]
    out += ["## 协议与运行环境", "",
            "- 每回合从 stdin 读一行 JSON（`halite3-lab-v1` 协议），向 stdout 回一行 Halite III 动作（`m <id> <n|s|e|w|o>`、`c <id>`、`g`，用空格分隔，空行表示全部停留），每行都要 flush。首行 init 后先回一行 bot 名字。日志写 stderr。",
            "- 完整协议见题目包里的 `PROTOCOL.md`。",
            f"- 每个 bot 进程：192 MiB 内存、单核 35% CPU、无网络、只读自己的文件。每回合 {TURN_SECONDS} 秒是墙钟时间，在 35% CPU 下实际可用的计算量约 {TURN_SECONDS * 0.35:.1f} 秒单核。超时、崩溃或输出非法动作的 bot 会被引擎终止，这一局按上面的名次规则排名（通常垫底）。",
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
    if config.get('experimental'):
        return f"# #{row['number']} 固定 Bot 规则迁移实验\n\n本批使用八个已冻结版本及两个平台基准，不改写 Bot、不重新提交。各变体的实际地形种子均为 11，完整配置见 RULES.md。原 Bot 的迁移表现与经过新规则适配后的策略能力分别评估。\n"
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
    engine = S.EXPERIMENT_ENGINE if setup['rules'].get('RULES_VERSION',1)>=2 else S.ENGINE
    if not engine.is_file():
        return None
    with tempfile.TemporaryDirectory() as work:
        idle = f"{work}/idle.py"
        with open(idle, "w") as f:
            f.write("import sys\nsys.stdin.readline()\nprint('idle',flush=True)\nfor _ in sys.stdin: print('',flush=True)\n")
        with open(f"{work}/rules.json", "w") as f:
            json.dump(setup["rules"], f)
        argv = [str(engine), "--results-as-json", "--no-compression", "--width", str(setup["width"]), "--height", str(setup["height"]),
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
        if config.get('experimental'):
            put('EXPERIMENTS.json', json.dumps({'scenarios':config['scenarios'],'roster':config['roster'],'execution_batches':config.get('execution_batches',[])},ensure_ascii=False,indent=2))
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
