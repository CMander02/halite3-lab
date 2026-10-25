# Halite 3 Arena 网页与后端

网站与游戏引擎放在同一仓库。正式入口：<https://halite3.cmander02.com>。页面、API、数据库、上传和比赛执行均运行在本机；Cloudflare Tunnel 提供 HTTPS 入口，主域 `/halite3` 使用单独的重定向 Worker。

## 目录

- `src/`：React + Vite 页面、移动端布局、Canvas 回放播放器。
- `backend/`：FastAPI、Argon2id 账号、会话、API Token、SQLite 任务队列、编译缓存。
- `runner/sandbox.py`：原生 Python / C++ 进程的 Bubblewrap 与 systemd scope 启动器；不使用 Docker 执行 bot。
- `examples/cpp/main.cpp`：适配改版观测协议的 C++ 示例。
- `client.py`：标准库 CLI，直接上传到后端和提交测试。
- `redirect/`：仅负责主域 `/halite3` 跳转的 Worker。
- `tests/`：账号隔离、不可变版本、排队重试、真实 C++/Python 比赛等后端测试。

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

正式机使用 `/usr/local/lib/halite3/bwrap` 与 `/usr/bin/g++`。运行时只映射只读系统库和当前版本目录，不映射服务器 home、账号数据库或其他 bot 文件。独立 PID、网络、IPC 等命名空间，清空环境变量，禁止嵌套 userns。每个 bot 进程 scope 限制 192 MiB 内存、35% 单核 CPU、32 个任务和 105 秒；临时目录 16 MiB，编译阶段限制 512 MiB、75% 单核和 60 秒。单场比赛 100 秒。编译错误会保存并作为确定性失败处理，同一源码不重复编译重试。全局一次执行一场比赛，按用户轮转调度。

## Bot 文件与最新版本

支持 `.py`、`.cpp`、`.cc`、`.cxx` 或 ZIP，上传文件最多 5 MiB；ZIP 最多 64 个条目，解压后最多 20 MiB，拒绝路径穿越、符号链接、加密 ZIP。Python ZIP 根目录放 `bot.py`。C++ ZIP 可以包含头文件及最多 24 个 `.cpp/.cc/.cxx` 编译单元，后端统一使用 `g++ -std=c++17 -O2 -pipe` 编译；提供 `<nlohmann/json.hpp>`，不执行上传项目的 Makefile、CMake、安装脚本或依赖下载。Python 运行环境为本机 Python 3.12 标准库，可在 ZIP 中携带纯 Python 模块。

每个上传版本是不可覆盖的快照：

```text
users/<user-id>/bots/<bot-id>/
├── latest -> versions/<latest-version-id>
└── versions/<version-id>/
    ├── source.py / source.cpp / source.zip
    ├── build.json
    └── runtime/
        └── bot.py / bot / 其他源码文件
```

`latest` 便于本机定位。调度时以数据库中最新的已上传版本为准，并将其 id、版本号、源码 SHA-256 固定进比赛记录。测试进行中继续上传不会改变已提交的比赛。C++ 首次使用时编译，后续复用该版本的二进制和编译器记录。

网页可以一键选择各 Bot 的最新版本。API 提交可以传 `bot_ids` 自动解析最新版本，或传 `version_ids` 明确选择历史版本。

改版使用 `halite3-lab-v1` JSON Lines 观测协议，动作仍是 H3 的文本命令。历史 H3 SDK 的文本观测解析器需要适配；原版语言支持不代表原版 SDK 可以不修改就读取迷雾协议。协议详见 [../lab/RULES.md](../lab/RULES.md)。下载示例：`/sample-python.zip`、`/sample-cpp.zip`，由 `npm run build` 自动生成。

## 直接调用后端

先在网页注册账号，再在仓库根目录执行：

```bash
python3 web/client.py login
python3 web/client.py upload MyBot.cpp --name my-cpp --version 1.0
python3 web/client.py upload MyBot.zip --name my-python --version 1.1
python3 web/client.py bots
python3 web/client.py test --bots <my-bot-id>,builtin-baseline --modes 2 --seeds 11,29,47 --rotate
python3 web/client.py status <job-id>
python3 web/client.py rank <version-id>
```

CLI 将 Token 保存在 `~/.config/halite3/credentials.json`，权限 0600。也可设置 `HALITE_TOKEN`；Token 不接受 URL 查询参数，30 天到期，可在账号页面撤销。网页会话有效 7 天，使用 HttpOnly、Secure、SameSite=Lax Cookie。密码为带独立盐的 Argon2id 哈希。写操作校验 Origin，CLI Bearer 请求按账号授权。

主要接口：`POST /api/auth/register`、`POST /api/auth/login`、`GET/POST /api/bots`、`POST /api/bots/{id}/versions`、`POST /api/tests`、`GET /api/tests/{id}`、`GET /api/matches`、`GET /api/matches/{id}/replay`、`GET /api/leaderboard`。接口结构见 `/api/openapi.json`。

## 比赛、回放与排名

单任务最多 300 场、每用户滚动 24 小时最多 500 场、同时最多 3 个未完成任务。每用户最多 30 个 bot、200 个版本，上传源码合计 256 MiB。全盘空闲低于 8 GiB 时暂停新上传、新测试和执行。配额在 `backend/settings.py` 配置。

任务断点恢复以整场比赛为单位。SQLite WAL 保存队列和逐场结果；执行器定期续租，异常退出后过期租约会重跑，完成的比赛不会重复。每场默认最多 3 次尝试；用户可重试失败场次。等待场次可取消，已运行比赛会完成并保存结果。

回放保存 gzip JSON `.hlt` 数据，包括每回合船只、矿量、动作和事件。播放器将 H3 的下一帧船状态与本帧末尾银行和矿场对齐，避免回合偏移。提供逐帧、播放、1×/2×/4×、棋盘视角、下载、移动端触摸进度。源码始终私有；私人测试及日志按账号隔离。

公开排行榜由用户主动提交，每个版本固定对阵 baseline / raider，种子 11、29、47，交换座位，共 12 场。全部完成后根据胜率分为 S≥75%、A≥50%、B≥25%、C<25%。私人自选测试不计入排行榜。参评会公开版本名称、作者、成绩和对应比赛回放，源码保持私有。

私人回放默认保留 30 天；公开评测和示例回放保留，受到磁盘总量保护。源码、编译缓存和数据库不自动过期。当前没有邮箱找回密码功能。

## 验证与运维

```bash
cd web
npm run build
.venv/bin/python -m unittest discover -s tests -v
```

正式服务：`halite3-web.service`、`halite3-runner.service`、`halite3-tunnel.service`，均为 cmander 的 systemd 用户服务。配置在 `/home/cmander/Services/halite3/`，数据目录不在 Git checkout 中。完整运维说明会记录到 `~/Server/runbooks/halite3-arena.md`。

元数据每天通过 SQLite backup API 生成一致性副本，保留最近 7 个日期，位于数据目录 backups/。这份定时备份不复制源码与回放；完整恢复还需要保留同一数据目录中的 users/、blobs/、builtin/、replays/ 与 logs/。尚未配置异地副本。
