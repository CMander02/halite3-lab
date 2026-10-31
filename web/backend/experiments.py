"""Frozen contest #1 transfer tests. Bot versions are never adapted or re-uploaded."""
import copy
import hashlib
import json
import uuid
from fastapi import APIRouter, HTTPException, Request
from . import settings as S, contests
from .db import connect, now
from .rating import board
from .scheduler import snapshot
from .security import user_for

router = APIRouter()
SLUG = 'test-1'
REMOTE_PENDING = ('remote_queued', 'remote_running')


def scenarios():
    reference = {}
    for mode, width in [(2, 32), (4, 48), (8, 64)]:
        reference[str(mode)] = dict(width=width, height=width, turns=400, seconds=900,
            rules=dict(S.RULES, RULES_VERSION=2, SYMMETRIC_MAP=True, MAP_STYLE=0,
                       ORE_PER_PLAYER=60000, PILEUP_WRECK_SIZE=3))
    result = []

    def add(key, label, rules=None, turns=None, eight_width=None, legacy=False):
        setups = copy.deepcopy({str(m): S.MODE_SETUPS[m] for m in (2, 4, 8)} if legacy else reference)
        for mode, setup in setups.items():
            setup['rules'].update(rules or {})
            if turns is not None:
                setup['turns'] = turns
            if mode == '8' and eight_width:
                setup['width'] = setup['height'] = eight_width
        result.append(dict(key=key, label=label, setups=setups))

    economy = dict(MAX_CELL_PRODUCTION=15, MIN_CELL_PRODUCTION=15, MAX_ENERGY=15,
                   FIXED_MINING=1, FREE_MOVEMENT=True, INSPIRATION_ENABLED=False,
                   NEW_ENTITY_ENERGY_COST=15, INITIAL_ENERGY=75, DROPOFF_COST=60,
                   ORE_PER_PLAYER=900, SCOUT_CAPACITY=7)
    add('combined', '综合新规则：整数经济、矿脉、有界、双船型、生产限制',
        dict(economy, MAP_STYLE=5, BOUNDED_MAP=True, VISION_RADIUS=5, MAX_SHIPS=24,
             SPAWN_INTERVAL=2, RESPAWN_COOLDOWN=2, SAFE_FRIENDLY_SPAWN=True,
             PILEUP_ENEMIES_ONLY=True, SCOUT_EVERY=2, SCOUT_VISION_RADIUS=7))
    add('control', '#0 原规则对照', legacy=True)
    add('reference', '对称矿图与长局参考配置')
    for key, label, style, reef in [('open', '开放海域', 1, 0), ('sparse', '少礁石', 2, 4),
                                   ('ring', '环岛与对称通道', 3, 0), ('central', '中央富矿', 4, 12),
                                   ('veins', '多尺度矿脉', 5, 12)]:
        add(key, label, dict(MAP_STYLE=style, REEF_PERCENT=reef))
    add('bounded', '有界地图', dict(BOUNDED_MAP=True))
    add('eight32', '8 人 32×32', eight_width=32)
    add('eight48', '8 人 48×48', eight_width=48)
    add('turns200', '200 步', turns=200)
    add('turns300', '300 步', turns=300)
    add('vision3', '视野半径 3', dict(VISION_RADIUS=3))
    add('vision5', '视野半径 5', dict(VISION_RADIUS=5))
    add('fullvision', '全图视野', dict(FOG_ENABLED=False))
    add('ships12', '现存船上限 12', dict(MAX_SHIPS=12))
    add('ships24', '现存船上限 24', dict(MAX_SHIPS=24))
    add('spawn2', '每 2 回合允许生产', dict(SPAWN_INTERVAL=2))
    add('spawn3', '每 3 回合允许生产', dict(SPAWN_INTERVAL=3))
    add('respawn2', '损船后冷却 2 回合', dict(RESPAWN_COOLDOWN=2))
    add('respawn4', '损船后冷却 4 回合', dict(RESPAWN_COOLDOWN=4))
    add('safe_spawn', '己方占基地时拒绝出生并退款', dict(SAFE_FRIENDLY_SPAWN=True))
    add('enemy_pileup', '三船全灭仅限含敌方的碰撞', dict(PILEUP_ENEMIES_ONLY=True))
    add('fixed_mining', '每次采矿固定为 1，保留千单位经济', dict(FIXED_MINING=1))
    add('no_inspiration', '关闭灵感奖励', dict(INSPIRATION_ENABLED=False))
    add('scouts', '交替出生运输船与低容量侦察船', dict(SCOUT_EVERY=2, SCOUT_CAPACITY=500, SCOUT_VISION_RADIUS=6))
    add('economy15', '0～15 整数经济与固定采矿', economy)
    # Match seeds identify a case, while map_seed keeps terrain seeds paired.
    for index, case in enumerate(result):
        seed = 1000000 + index * 100 + 11
        case.update(match_seeds=[seed], map_seeds=[11])
    return result


def tables(players, baselines):
    """80 games/case: both baselines, every selected bot, every seat in all modes."""
    games = []
    for bot in players:
        for target in baselines:
            games += [[bot, target], [target, bot]]
    for start in range(0, 8, 2):
        group = players[start:start+2] + baselines
        games += [group[r:] + group[:r] for r in range(4)]
    for omit in range(0, 8, 2):
        group = [bot for i, bot in enumerate(players) if i not in (omit, omit+1)] + baselines
        games += [group[r:] + group[:r] for r in range(8)]
    return games


def create(db):
    existing = db.execute('SELECT * FROM contests WHERE number=1 OR slug=?', (SLUG,)).fetchone()
    if existing:
        if not json.loads(existing['config_json']).get('experimental'):
            raise RuntimeError('Contest #1 is already in use')
        return existing['id']
    strong, seen = [], set()
    for entry in sorted(board(db), key=lambda e: (-e['elo'], e['version_id'])):
        if entry['builtin'] or entry['games'] < 12 or entry['bot_id'] in seen:
            continue
        strong.append(entry); seen.add(entry['bot_id'])
        if len(strong) == 8:
            break
    if len(strong) != 8:
        raise RuntimeError('Eight eligible rated bots are required')
    ids = [e['version_id'] for e in strong]
    targets = ['builtin-baseline-v1', 'builtin-raider-v1']
    rows = contests.version_rows(db, ids + targets)
    selected = [snapshot(dict(rows[vid])) for vid in ids]
    baselines = [snapshot(dict(rows[vid])) for vid in targets]
    for seat in selected + baselines:
        source = S.DATA / seat['object_key']
        if hashlib.sha256(source.read_bytes()).hexdigest() != seat['sha256']:
            raise RuntimeError('Frozen bot source hash mismatch')
    cases = scenarios()
    cid, jid, timestamp = str(uuid.uuid4()), str(uuid.uuid4()), now()
    manifest = [dict(version_id=e['version_id'], bot_id=e['bot_id'], bot_name=e['bot_name'], version=e['version'],
                     elo=e['elo'], sha256=rows[e['version_id']]['sha256']) for e in strong]
    config = dict(experimental=True, execution_host='txcloud', primary_scenario='combined', scenarios=cases,
                  roster=manifest, modes=[2,4,8], targets=targets, base_version_id=targets[0], downloads=targets,
                  languages=['cpp'], max_submissions=200, bench_rotate=True, final_rounds=1,
                  auto_final=False, public_maps={str(m):[11] for m in (2,4,8)},
                  hidden_maps={str(m):[] for m in (2,4,8)}, setups=cases[0]['setups'])
    description = ('8 个按原始 ELO 选取的不同 Bot，固定现有版本和源码哈希，与 baseline、raider 测试。\n'
                   '实验由 txcloud 的独立原生沙箱执行，结果回传。各变体单独统计；不计入 #0 或全局 ELO。\n'
                   '每项变体 80 局：1v1 32 局、4 人 16 局、8 人 32 局，全部轮换座位。\n'
                   '旧 Bot 不作适配；新经济下不造船或不返航属于迁移结果，不能单凭此判断规则平衡。\n'
                   '综合规则：32/48/64 方格、400 步、有界对称矿脉、容量 15、每次采 1、移动免费、'
                   '初始银行 75、造船 15、落点 60、灵感关闭、现存船上限 24、生产间隔 2、损船冷却 2、'
                   '己方基地占用时拒绝出生、敌对三船碰撞全灭、交替出生容量 7/视野 7 的侦察船。'
                   '初始格矿 0～15；沉船回流允许格矿超过 15，保留资源。')
    db.execute('''INSERT INTO contests(id,number,slug,title,summary,description,open_at,close_at,published,config_json,
                  final_job_id,final_started_at,created_at,updated_at,rules) VALUES(?,1,?,?,?,?,?,?,1,?,?,?,?,?,?)''',
               (cid, SLUG, '规则实验', '固定 8 个强 Bot 与两个平台基准；28 组规则实验，txcloud 执行。', description,
                timestamp-2, timestamp-1, json.dumps(config), jid, timestamp, timestamp, timestamp, description))
    seqs = {}
    for seat in selected:
        owner = seat['owner_id']; seqs[owner] = seqs.get(owner,0)+1
        db.execute('INSERT INTO contest_entries(id,contest_id,user_id,version_id,seq,note,created_at) VALUES(?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), cid, owner, seat['id'], seqs[owner], 'Frozen transfer-test version; source unchanged', timestamp))
    setups = {}
    for case in cases:
        for mode, setup in case['setups'].items():
            setups[f"{mode}:{case['match_seeds'][0]}"] = dict(setup, map_seed=11, scenario=case['key'])
    job_config = dict(contest_id=cid, contest=SLUG, stage='final', execution_host='txcloud', setups=config['setups'],
                      setups_by_seed=setups, rules=S.RULES, width=32, height=32, turns=400, seconds=900,
                      modes=[2,4,8], seeds=[c['match_seeds'][0] for c in cases])
    db.execute('INSERT INTO jobs(id,owner_id,name,kind,config_json,created_at,contest_id,rating_scope) VALUES(?,?,?,?,?,?,?,?)',
               (jid, contests.admin_id(db), '#1 txcloud · 28 组规则实验', 'contest-final', json.dumps(job_config), timestamp, cid, 'contest'))
    base_tables = tables(selected, baselines)
    by_mode = {mode:[table for table in base_tables if len(table)==mode] for mode in (2,4,8)}
    # Interleave rules and modes so no mode waits for the entire duel schedule.
    for index in range(max(map(len,by_mode.values()))):
        for case in cases:
            for mode in (2,4,8):
                if index >= len(by_mode[mode]):
                    continue
                seats = by_mode[mode][index]
                db.execute('INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,status,public,created_at) VALUES(?,?,?,?,?,?,?,1,?)',
                           (str(uuid.uuid4()), jid, contests.admin_id(db), len(seats), case['match_seeds'][0],
                            json.dumps(seats), 'remote_queued', timestamp))
    return cid


@router.get('/api/contests/{key}/experiments')
def experiment_results(key: str, request: Request, scenario: str = 'combined'):
    user = user_for(request, False)
    with connect() as db:
        contest = contests.load(db, key, user)
        config = json.loads(contest['config_json'])
        if not config.get('experimental'):
            raise HTTPException(404, '此比赛没有规则实验。')
        cases = []
        for case in config['scenarios']:
            counts = dict(db.execute('SELECT status,COUNT(*) FROM matches WHERE job_id=? AND seed=? GROUP BY status',
                                     (contest['final_job_id'], case['match_seeds'][0])))
            cases.append(dict(case, counts=counts, total=sum(counts.values())))
        if scenario not in {c['key'] for c in cases}:
            raise HTTPException(422, '未知规则实验。')
        case = next(c for c in cases if c['key']==scenario)
        diagnostics = [dict(r) for r in db.execute('''SELECT m.mode,COUNT(*) seats,SUM(p.ships_built=0) no_spawn_seats,
            SUM(p.ships_built) ships_built,SUM(p.mined) mined,SUM(p.delivered) delivered,SUM(p.deaths) deaths
            FROM match_players p JOIN matches m ON m.id=p.match_id WHERE m.job_id=? AND m.seed=? AND m.status='complete' GROUP BY m.mode''',
            (contest['final_job_id'],case['match_seeds'][0]))]
        return dict(roster=config['roster'], execution_host=config['execution_host'], primary=config['primary_scenario'], diagnostics=diagnostics,
                    scenarios=cases, selected=scenario, standings=contests.compute(db, contest, 'final', scenario),
                    progress=contests.stage_progress(db, contest, 'final'))
