# Halite 3 Lab

基于 [HaliteChallenge/Halite-III](https://github.com/HaliteChallenge/Halite-III) 的规则实验 fork。保留原版 C++ 引擎，在 `game_engine/` 内扩展规则。上游版本为 `e1050ee924292997b3a446b4be4c821848944fd8`。原始说明见 [README.upstream.md](README.upstream.md)，许可证保留 MIT。

已提供迷雾、礁石、轻船击坠重船、两个示例 bot，以及支持 2 / 4 / 8 人组合循环赛和整场重试的测试器。

## 运行

需要 Docker。Python 测试器只使用标准库，也可以在兼容 Linux 主机上直接运行 `python3 lab/arena.py ...`。

```bash
./lab/dev.sh build
./lab/dev.sh test

# 3 个地图种子，各交换一次座位，共 6 场，每场 200 回合
./lab/dev.sh arena run lab/config/duel.json --out lab/runs/duel --jobs 2
./lab/dev.sh arena status lab/runs/duel

# 相同命令恢复：跳过完成比赛，重试未完成比赛
./lab/dev.sh arena run lab/config/duel.json --out lab/runs/duel --jobs 2

# 检查 10 bot 的 2/4/8 人赛程，不启动比赛
./lab/dev.sh arena plan lab/config/league10.json

# 300 场、每场 8 回合的流程验证
./lab/dev.sh arena run lab/config/smoke10.json --out lab/runs/smoke10 --jobs 4

# 单场 4 / 8 人、200 回合验证
./lab/dev.sh arena run lab/config/ffa4.json --out lab/runs/ffa4 --jobs 1
./lab/dev.sh arena run lab/config/ffa8.json --out lab/runs/ffa8 --jobs 1

# 300 场、每场 200 回合
./lab/dev.sh arena run lab/config/league10.json --out lab/runs/league10 --jobs 4
```

`league10.json` 中的十个参赛者是 baseline / raider 的不同参数组合，供测试注册和调度流程。可以替换为独立实现的十个 bot。完整的联赛强度评估应使用多个地图种子及座位轮换。

## 规则

默认实验规则见 [lab/config/rules.json](lab/config/rules.json)，详细顺序与协议见 [lab/RULES.md](lab/RULES.md)。

| 配置 | 当前值 | 行为 |
|---|---:|---|
| `LAB_PROTOCOL` | true | JSON Lines 观测，动作沿用 H3 命令 |
| `FOG_ENABLED` | true | 仅发送己方视野内的当前动态信息 |
| `VISION_RADIUS` | 4 | 环形地图上的曼哈顿距离；己方船、基地与 dropoff 共享视野 |
| `REEF_PERCENT` | 12 | 礁石候选概率，生成时保持对称、连通与出生点缓冲区 |
| `LIGHT_SHIP_COLLISIONS` | true | 唯一最轻者存活并抢矿；最轻者并列则该格全灭、矿落地 |

重量按移动扣费后的船载矿量比较。友军同样适用。载货容量保留 H3 的 1000，抢矿超出容量的部分落地。静态地形与初始基地位置公开，敌方银行和视野外的敌船、矿量不可见。礁石不遮挡视线。

移动扣费、采矿、dropoff、inspiration 与交易阶段顺序沿用 H3。没有增加 H4 的资源再生、敌方基地摧毁规则。所有新增开关默认关闭，直接运行引擎而不加载实验配置时仍用原版协议与规则。

## 测试器

赛程以不同 bot 的组合为单位，每个组合中的每种 bot 出场一次。无座位轮换、每种子：

| 注册数量 | 每局人数 | 场数 |
|---:|---:|---:|
| 10 | 2 | 45 |
| 10 | 4 | 210 |
| 10 | 8 | 45 |
| | 合计 | 300 |

`rotate_seats: true` 为每个组合生成 k 次循环座位轮换。十个 bot 的三种模式合计每种子 1290 场。这能平衡各 bot 的出生座位，未穷举所有相对座位排列。`seeds` 增加地图重复次数。2、4、8 人结果分别汇总，采用 H3 原生排名，输出胜率、平均名次和平均分。原生排名先比较存活回合，再比较各回合银行矿量，完全相同则使用种子生成的随机数决胜。

每个 run 目录保存：

- `arena.sqlite3`：赛程、状态、各次尝试及结果，SQLite WAL 事务提交。
- `manifest.json`：完整配置，引擎、规则、测试器与声明的 bot 源文件 SHA-256。
- `artifacts/<sha256>`：对应引擎二进制、规则与源码的原始内容。
- `summary.json`：各模式、各 bot 的统计。
- `matches/<match-id>/attempt-N/`：启动参数、stdout、stderr、引擎错误日志与完整 JSON `.hlt` 回放。

回放包含初始资源、公开地形、每回合动作、船的位置和载矿、地面矿量变化、碰撞事件和银行矿量。回放记录全局状态；bot 在对局中收到的观测仍经过视野过滤。旧版可视化器对礁石和抢矿扩展的显示尚未适配。

进程中断后用原命令恢复，完成的比赛不会重复执行。失败或中断比赛按原种子、原座位从头重跑；每次尝试的文件保留。默认 `--max-attempts 2` 是每场累计尝试次数上限，可在恢复时调大。`--limit N` 限制本次最多启动 N 次尝试；存在未完成任务时 CLI 返回 1。`--jobs N` 控制并发。同一个 run 只能启动一个调度进程。

配置、引擎或声明的 bot 源文件变化时拒绝混用已有 run，需换输出目录。开发新 bot 时务必在 `sources` 中列出其代码和依赖的本地模块。随机 bot 还需要自行固定内部随机源；相同地图种子不保证任意第三方 bot 的确定性。

恢复粒度为整场。暂不支持从任意回合恢复进程内 bot 的内部状态；原版 snapshot 也不作为这种 checkpoint 使用。测试器面向 Linux，支持本机多进程并发，尚无多机器任务队列。

## Bot

`lab/bots/baseline.py` 是本项目的局部贪心采矿基准，支持避礁、返航、造船和友军位置预留。`lab/bots/raider.py` 使用目的格匹配处理基地拥堵，并增加地图记忆、基于可达距离的矿点选择、可见敌船的碰撞风险估计和轻船攻击。两者均只使用过滤后的观测。这里的 baseline 不代表历史竞赛中的强 bot。

新增 bot 的接口及注册方式见 [lab/RULES.md](lab/RULES.md)。

已执行的测试、对照赛及其限制见 [lab/VALIDATION.md](lab/VALIDATION.md)。

网页平台已扩展到 [web/](web/README.md)，支持账号隔离、Python/C++ 版本上传、原生进程测试、回放和固定基准 Tier List。
