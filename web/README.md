# Halite 3 Arena 网页与后端

网站与游戏引擎放在同一仓库。正式入口：<https://halite3.cmander02.com>。页面、API、数据库、上传和比赛执行均运行在本机；Cloudflare Tunnel 提供 HTTPS 入口，主域 `/halite3` 使用单独的重定向 Worker。

## 目录

- `src/`：React + Vite + Tailwind v4 页面。设计语言为“Pixel Odyssey 日间版”：米白底 + 蓝色像素、Fusion Pixel 等宽像素字、零圆角、阶梯切角按钮、Bayer 抖动。组件用 shadcn/ui（Radix），图标用 pixelarticons（`@nsmr/pixelart-react`），图表用 Recharts（shadcn chart 封装）。
  - `src/components/ShipLaunch.tsx`：首页 / 登录页轮换的像素发射动画（6 种船型，月相随轮次推进）。
  - `src/replay/`：回放页与 Canvas 棋盘（抖动矿量、按移动方向旋转的船、迷雾视角、沉船标记）。桌面端 100% 缩放不滚动即可看完整战况和进度条；手机端首屏为棋盘 + 全部玩家 + 控制条，下滑查看数据与近期对战。
- `backend/profiles.py`：头像（注册即分配全站唯一的 8×8 对角对称像素头像，可上传 PNG 替换 / 恢复默认）、显示名称、`/api/leaderboard/stats` 子榜、`/api/summary`。
- `backend/analytics.py`：从回放计算每局每座位的击沉 / 被击沉 / 同归、抢劫与损失货物、搬运、采矿、视野（`match_players` 表），新比赛完成时写入，启动时回填旧比赛。
- `CAPACITY.md`：42 个版本规模下的赛程、耗时与回放存储（含 D1）估算。
- `backend/`：FastAPI、Argon2id 账号、会话、API Token、SQLite 任务队列、编译缓存。
- `runner/sandbox.py`：C++ 参赛进程与平台固定基准的 Bubblewrap 与 systemd scope 启动器；不使用 Docker 执行 bot。
- `examples/cpp/main.cpp`：适配改版观测协议的 C++ 示例。
- `client.py`：标准库 CLI，直接上传到后端和提交测试。
- `redirect/`：仅负责主域 `/halite3` 跳转的 Worker。
- `tests/`：账号隔离、不可变版本、排队重试、C++ 上传限制和真实 C++ 对战平台基准等后端测试。

运行数据默认 `web/data/`；正式服务通过 `HALITE_DATA_DIR` 使用 `/home/cmander/Services/halite3/data/`。数据、Token、密码、上传源码、回放及编译产物不进入 Git。

## 本地开发

```bash
cd web
uv venv
uv pip install --python .venv/bin/python -r requirements.lock
npm ci
npm run build
HALITE_APP_ORIGIN=http://127.0.0.1:18383 .venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 18383
# 另一个终端
.venv/bin/python -m backend.runner
# 或仅前端热更新
npm run dev
```

引擎沿用项目根目录 `build/halite`，编译方法见上层 README。原生 bot 执行需要 Ubuntu/Linux、systemd 用户管理器、g++、nlohmann-json3-dev、Bubblewrap。Ubuntu 24.04 需要为实际使用的 Bubblewrap 二进制添加精确的 AppArmor userns 规则，参考 `deploy/halite3-bwrap.apparmor`；不要全局关闭用户命名空间的 AppArmor 限制。

正式机使用 `/usr/local/lib/halite3/bwrap` 与 `/usr/bin/g++`。运行时只映射只读系统库和当前版本目录，不映射服务器 home、账号数据库或其他 bot 文件。独立 PID、网络、IPC 等命名空间，清空环境变量，禁止嵌套 userns。每个 bot 进程 scope 限制 192 MiB 内存、35% 单核 CPU、32 个任务和整场时限 +5 秒；临时目录 16 MiB，编译阶段限制 512 MiB、75% 单核和 60 秒。单场比赛 2 / 8 人 100 秒，4 人（48×48、300 回合）240 秒。地图、回合、规则与时限按人数写在 `backend/settings.py::MODE_SETUPS`，提交时冻结进任务配置的 `setups`，之后修改不影响已排队的任务。编译错误会保存并作为确定性失败处理，同一源码不重复编译重试。全局一次执行一场比赛，按用户轮转调度。

## Bot 文件与最新版本

提交和参赛仅支持 C++17：`.cpp`、`.cc`、`.cxx` 或包含 C++ 源码的 ZIP，上传文件最多 5 MiB。ZIP 最多 64 个条目，解压后最多 20 MiB，拒绝路径穿越、符号链接、加密 ZIP 和 Python 源码/字节码（包括 C++ 与 Python 混合包）。C++ ZIP 可以包含头文件及最多 24 个 `.cpp/.cc/.cxx` 编译单元，后端统一使用 `g++ -std=c++17 -O2 -pipe` 编译；提供 `<nlohmann/json.hpp>`，不执行上传项目的 Makefile、CMake、安装脚本或依赖下载。

历史用户 Python 版本的源码、轨迹和比赛记录保持可读，但不能提交私人测试、公开评测、重试历史任务或设为默认版本，也不再显示在公开排行榜中。已排队的旧 Python 任务会以不可重试的语言限制错误结束。`baseline` / `raider` 是两个不可变的平台内部 Python 基准，继续使用原有源码和哈希，保持当前赛季的评测口径；用户不能提交或覆盖它们。`lab/` 的本地规则测试工具仍可使用 Python 测试脚本。

每个上传版本是不可覆盖的快照：

```text
users/<user-id>/bots/<bot-id>/
├── latest -> versions/<latest-version-id>
└── versions/<version-id>/
    ├── source.cpp / source.zip
    ├── build.json
    └── runtime/
        └── bot / C++ 源码和头文件
```

`latest` 便于本机定位。调度时以数据库中最新的已上传版本为准，并将其 id、版本号、源码 SHA-256 固定进比赛记录。测试进行中继续上传不会改变已提交的比赛。C++ 首次使用时编译，后续复用该版本的二进制和编译器记录。

网页可以一键选择各 Bot 最新的可参赛未归档版本。API 提交可以传 `bot_ids` 使用可参赛的未归档默认版本，否则自动解析最新可参赛未归档版本；或传 `version_ids` 明确选择 C++ 历史版本。平台固定基准同样可以作为对手。

改版使用 `halite3-lab-v1` JSON Lines 观测协议，动作仍是 H3 的文本命令。历史 H3 SDK 的文本观测解析器需要适配。协议详见 [../lab/RULES.md](../lab/RULES.md)。C++ 示例下载：`/sample-cpp.zip`，由 `npm run build` 自动生成。旧的 Python 示例下载返回 404。

## 直接调用后端

先在网页注册账号，再在仓库根目录执行：

```bash
python3 web/client.py login
python3 web/client.py upload MyBot.cpp --name my-cpp --version 1.0 --trace session.jsonl --model claude-opus-5-5 --effort high --harness claude-code
python3 web/client.py upload MyBot.zip --name my-cpp --version 1.1 --trace session.jsonl.gz
python3 web/client.py bots
python3 web/client.py test --bots <my-bot-id>,builtin-baseline --modes 2 --seeds 11,29,47 --rotate
python3 web/client.py status <job-id>
python3 web/client.py rank <version-id>
```

CLI 将 Token 保存在 `~/.config/halite3/credentials.json`，权限 0600。也可设置 `HALITE_TOKEN`；Token 不接受 URL 查询参数，30 天到期，可在账号页面撤销。网页会话有效 7 天，使用 HttpOnly、Secure、SameSite=Lax Cookie。密码为带独立盐的 Argon2id 哈希。写操作校验 Origin，CLI Bearer 请求按账号授权。

主要接口：`POST /api/auth/register`、`POST /api/auth/login`、`GET/POST /api/bots`、`POST /api/bots/{id}/versions`、`POST /api/tests`、`GET /api/tests/{id}`、`GET /api/matches`、`GET /api/matches/{id}/replay`、`GET /api/leaderboard`。接口结构见 `/api/openapi.json`。

## 管理员、对话轨迹与 ELO 修正

- **唯一管理员**：`HALITE_ADMIN`（默认 `cmander`）对应的账号在启动迁移时设为管理员，其他账号的管理员标记会被清除；`users_single_admin` 部分唯一索引保证全站最多一个管理员。`/admin` 页面与 `/api/admin/*` 接口提供：用户列表、停用/启用（同时撤销会话与 Token、取消排队中的私人对局）、重置临时密码、强制下线；提交审核（人工确认模型 / 推理 / 平台、重新检测、下载轨迹）；以及模型、推理强度、平台三张目录的 ELO 修正和识别规则。
- **上传必须附带对话轨迹**：`POST /api/bots/{id}/versions` 需要 `file`（bot 源码）和 `trace`（生成它的对话），可选 `model` / `effort` / `harness`（`GET /api/catalog` 中的 id）和 `rank=true`（上传后直接参加 12 场基准评测和多人评测）。轨迹最多 16 MiB，支持 gzip / zip，gzip 后保存在版本目录的 `trace.gz`，只有作者和管理员能下载（`GET /api/versions/{id}/trace`）。设置 `HALITE_REQUIRE_TRACE=0` 可关闭强制要求。
- **检测**（`backend/detect.py`）：优先读取结构化字段——Claude Code 会话 JSONL 的 `message.model`、`api-request.params.output_config.effort` 与会话签名；Codex rollout 的 `session_meta.originator`、`turn_context.model/effort`；其他 JSON 导出里的 `model` / `effort` 类字段；最后才退回到全文正则（置信度最低）。同时统计消息数、输出 token 和首末时间戳（用时）。
- **计分采用的配置**（`backend/rating.py::attribution`）：管理员确认优先；否则使用用户声明，但若检测置信度为中/高且检测到的配置修正更大，则改用检测结果——少报不能换来加分。
- **ELO**：对全部公开且完成的对局做 Bradley–Terry 极大似然拟合，每局按名次两两比较，n 人局每对权重 1/(n−1)，每个版本另有对 1500 锚点的一胜一负先验，结果与对局顺序无关并附近似标准差。**修正后 ELO = 原始 ELO − 模型修正 − 推理修正 − 平台修正**；平台基准不修正、不参与排名。`GET /api/leaderboard/elo` 返回总榜，`GET /api/me/submissions` 返回自己每个版本的声明、检测、计分配置、评测进度、ELO 与名次。
- **版本管理**：`PATCH /api/versions/{id}`（说明、是否在榜单显示、归档）、`PATCH /api/bots/{id}`（默认版本）。`bot_ids` 提交测试时使用默认版本，未设置时使用最新的未归档版本。
- 图标来自 [LobeHub Icons](https://lobehub.com/icons/)（MIT），放在 `public/model-icons/`。

CLI 上传示例：

```bash
python3 web/client.py catalog
python3 web/client.py upload bot.cpp --name my-bot --version 1.0 \
  --trace ~/.claude/projects/<项目>/<会话>.jsonl --model claude-opus-5-5 --effort high --harness claude-code --rank
```

## 比赛（赛季）

管理员在 `/contests/new` 创建比赛（`backend/contests.py`）。每场比赛有自己的说明、靶子 bot、基础 bot、开放下载的版本、人数模式、公开地图和隐藏地图（地图 = 种子 + 该模式的尺寸 / 回合 / 规则，创建时冻结进比赛配置）、每人提交次数上限，以及三个时间：开放浏览、开放提交、提交截止。状态由时间推出：草稿 → 即将开始 → 提交中 → 正式评测中 → 已结束。

- **提交期**：选手把自己的某个版本提交到比赛（`POST /api/contests/{slug}/entries`），每次提交按序号记录，同一版本只能提交一次。每次提交只和靶子在公开地图上对战（1v1 换座；4 人场候选 + 3 个靶子座位轮换 4 次；8 人场 2 个座位偏移），新提交会取消自己上一次提交还在排队的对局。选手之间此时不对战。所有提交面对同一组靶子，因此用 Bradley–Terry 拟合出可比的**临时 ELO**，排行页按模式和总榜展示，同时列出对每个靶子的得分率。提交开始后，人数模式、公开地图、靶子、语言和座位轮换不能再改。
- **正式评测**：截止后执行器（`contests.tick()`，每 15 秒）自动排正式赛程：每人选定的提交（默认最后一次，可在提交期内改选）+ 靶子，在公开 + 隐藏地图上对战；1v1 双循环换座，4 / 8 人局每张地图按 `final_rounds` 轮随机分组（人数不够时用靶子补位，选手不会占两个座位）。管理员也可以手动开始、重新开始、重试失败对局、手动公布。
- **公布结果**：正式评测全部完成后自动冻结排名（`standings_json`），隐藏地图种子公开，比赛的全部对局设为公开。**比赛对局在公布前不进入全局 ELO**，公布后和固定评测一样计入 `/api/leaderboard/elo`。
- **本地测试**：概览页提供靶子 / 基础 bot 下载（`/api/contests/{slug}/downloads/{version_id}`）、每个模式的规则文件（`/api/contests/{slug}/setup/{mode}?rules_only=true`）和引擎命令。提交期的云端评测和本地测的是同一件事；只有云端能做的是正式评测：对手是其他选手的最终版本、隐藏地图、统一沙箱与时限、模型 / 推理强度修正。
- 靶子、基础 bot 和下载只能选平台基准或管理员自己的版本。提交评测的对局属于选手（按用户轮转调度），正式评测属于管理员；比赛对局的回放不受 30 天私人回放清理影响。

- **题目包与规则**：比赛页（不是首页）提供“下载题目包”（`GET /api/contests/{slug}/kit.zip`）：`PROMPT.md` 题目（管理员写的题目 prompt，留空用默认模板，自动附上提交方式）、`RULES.md` 文字规则、`PROTOCOL.md` 协议、`maps/`（公开地图的种子、规则文件，以及用引擎跑一回合渲染出的地形 / 矿量 / 出生点，缓存在数据目录 `contest-maps/`）、`bots/` 参考 bot 源码、`starter/bot.cpp` 和 `tools/client.py`。`GET /api/contests/{slug}/prompt.md` 是题目 + 规则的纯文本。文字规则由冻结的比赛配置生成（时间、提交要求、评测与 ELO、每个模式的地图和规则开关、运行限制），管理员的“补充规则”接在末尾，显示在比赛概览页最下面。
- **提交 bot.cpp**：比赛只接受规范命名的单文件 `bot.cpp`（允许 Python 的比赛为 `bot.py`）。`POST /api/contests/{slug}/submit`（multipart：`file`、可选 `trace`、`bot`、`version`、`note`、`model` / `effort` / `harness`）一步完成上传和提交：`bot` 同名就是在同一个 Bot 上迭代，首次使用自动创建，版本号自动递增。网页手动上传不需要 API Token；要让 Agent 在会话里自己提交或反复迭代，给它一个 API Token，用 `client.py contest-submit / contest-status / kit`。Agent 轨迹现在是可选的（`HALITE_REQUIRE_TRACE=1` 可恢复强制）。
- **#0 测试比赛**（`test-0`）：常驻、不截止、没有正式评测。它就是原来的 12 场固定评测：启动迁移把所有历史“参评”任务按时间收为 #0 的提交，之后每次参评（Bots 页的按钮、上传时勾选、或在 #0 提交 bot.cpp）都会自动记入 #0，对局立即公开并计入全局 ELO 和 Tier。

主要接口：`GET /api/contests`、`GET /api/contests/{slug}`、`GET /api/contests/{slug}/standings?stage=bench|final`、`GET/POST /api/contests/{slug}/entries`、`PUT /api/contests/{slug}/pick`；管理：`POST/PUT/DELETE /api/admin/contests[/{id}]`、`POST /api/admin/contests/{id}/final|finalize|retry`、`GET /api/admin/contest-options`。

**Bot 页面**（`/bots/{id}`，`GET /api/bots/{id}/profile`）：Bot 的全部版本按时间排列，显示全局原始 / 修正后 ELO、总榜名次、Tier、每个版本参加过的比赛（临时 ELO 或正式名次），以及版本迭代的 ELO 折线。作者和管理员看到全部版本；其他人只看到已上榜或参加过比赛的版本。

## 比赛、回放与排名

单任务最多 300 场、每用户滚动 24 小时最多 500 场、同时最多 3 个未完成任务。每用户最多 30 个 bot、200 个版本，上传源码合计 256 MiB。全盘空闲低于 8 GiB 时暂停新上传、新测试和执行。配额在 `backend/settings.py` 配置。管理员账号不受这些配额限制：不限任务场数（只保留单任务 20000 场的防误操作上限）、每日场数、未完成任务数、bot / 版本数、源码总量、每小时上传 / 提交 / 建测试的频率、单任务版本数和种子数，也不受比赛的每人提交次数限制；单文件大小、沙箱资源限制、登录和改密码的频率限制对管理员照常生效。

任务断点恢复以整场比赛为单位。SQLite WAL 保存队列和逐场结果；执行器定期续租，异常退出后过期租约会重跑，完成的比赛不会重复。每场默认最多 3 次尝试；用户可重试失败场次。等待场次可取消，已运行比赛会完成并保存结果。

回放保存 gzip JSON `.hlt` 数据，包括每回合船只、矿量、动作和事件。播放器将 H3 的下一帧船状态与本帧末尾银行和矿场对齐，避免回合偏移。提供逐帧、播放、1×/2×/4×、棋盘视角、下载、移动端触摸进度。源码始终私有；私人测试及日志按账号隔离。

公开排行榜由用户主动提交，每个版本固定对阵 baseline / raider，种子 11、29、47，交换座位，共 12 场。全部完成后根据胜率分为 S≥75%、A≥50%、B≥25%、C<25%。

每次参评同时自动建一个公开的“多人评测”任务（`kind=ranked-multi`，`backend/scheduler.py::multiplayer_games`），对手池为 baseline、raider 加上 #0 中其他 Bot 最新提交里全局 ELO 最高的 7 个（`MULTI_POOL`）。4 人局：对手池按顺序和交错各切一遍三人组，每组与候选同桌、打三张地图中的两张、轮换全部座位，对手池满 9 个时 48 场；8 人局：每张地图一桌、每桌少掉不同的两个对手、轮换全部座位，共 24 场。对手不足 3 个时不跑 4 人，不足 7 个时不跑 8 人。这些对局计入全局 ELO 和 4 / 8 人子榜，不影响 #0 名次和 Tier；场数计入每日配额，但不占“同时 3 个未完成任务”的名额。私人自选测试不计入排行榜。参评会公开版本名称、作者、成绩和对应比赛回放，源码保持私有。

私人回放默认保留 30 天；公开评测和示例回放保留，受到磁盘总量保护。源码、编译缓存和数据库不自动过期。当前没有邮箱找回密码功能。

## 验证与运维

```bash
cd web
npm run build
.venv/bin/python -m unittest discover -s tests -v
```

正式服务：`halite3-web.service`、`halite3-runner.service`、`halite3-tunnel.service`，均为 cmander 的 systemd 用户服务。配置在 `/home/cmander/Services/halite3/`，数据目录不在 Git checkout 中。完整运维说明会记录到 `~/Server/runbooks/halite3-arena.md`。

元数据每天通过 SQLite backup API 生成一致性副本，保留最近 7 个日期，位于数据目录 backups/。这份定时备份不复制源码与回放；完整恢复还需要保留同一数据目录中的 users/、blobs/、builtin/、replays/ 与 logs/。尚未配置异地副本。
