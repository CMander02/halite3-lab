// cma252 bot for halite3-lab-v1 (fog, reefs, light-ship collisions). C++17 + nlohmann/json.
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using nlohmann::json;
using namespace std;

int W, H, N, me, MAXT;
static int envi(const char* k, int d) { const char* v = getenv(k); return v ? atoi(v) : d; }
int P_SPAWN = envi("B_SPAWN", 95), P_MAXS = envi("B_MAXS", 20), P_DROP = envi("B_DROP", 0), P_RET = envi("B_RET", 920), P_QM = envi("B_QM", 0), P_K = envi("B_K", 7000), P_HUNT = envi("B_HUNT", 200);
int MOVE_RATIO = 10, EXTRACT = 4, MAXE = 1000, SHIPCOST = 1000, DROPCOST = 4000;
vector<int> terrain;
vector<double> mem;      // remembered halite
vector<int> seen;        // last seen turn (-1 never)
vector<int> initv;       // initial value seen (or -1)
const int DX[5] = {0, 0, 0, 1, -1}, DY[5] = {0, -1, 1, 0, 0};
const char DC[5] = {'o', 'n', 's', 'e', 'w'};

inline int idx(int x, int y) { return ((y % H + H) % H) * W + ((x % W + W) % W); }
inline int nb(int p, int d) { return idx(p % W + DX[d], p / W + DY[d]); }

vector<int> bfs(const vector<int>& srcs) {
  vector<int> d(N, 1 << 20);
  vector<int> q; q.reserve(N);
  for (int s : srcs) { d[s] = 0; q.push_back(s); }
  for (size_t i = 0; i < q.size(); i++) {
    int p = q[i];
    for (int k = 1; k < 5; k++) {
      int n = nb(p, k);
      if (terrain[n]) continue;
      if (d[n] > d[p] + 1) { d[n] = d[p] + 1; q.push_back(n); }
    }
  }
  return d;
}

struct Ship { int id, pos, cargo; };
struct Enemy { int pos, cargo, owner; };

int main() {
  ios::sync_with_stdio(false);
  string line;
  if (!getline(cin, line)) return 0;
  json init = json::parse(line);
  me = init["player_id"]; W = init["width"]; H = init["height"]; N = W * H;
  auto C = init["constants"];
  MAXT = C.value("MAX_TURNS", 200);
  MOVE_RATIO = C.value("MOVE_COST_RATIO", 10);
  EXTRACT = C.value("EXTRACT_RATIO", 4);
  MAXE = C.value("MAX_ENERGY", 1000);
  SHIPCOST = C.value("NEW_ENTITY_ENERGY_COST", 1000);
  DROPCOST = C.value("DROPOFF_COST", 4000);
  terrain.assign(N, 0);
  for (int i = 0; i < N; i++) terrain[i] = init["terrain"][i].get<int>();
  mem.assign(N, -1); seen.assign(N, -1); initv.assign(N, -1);
  int myFx = 0, myFy = 0, enFx = 0;
  for (auto& p : init["players"]) {
    if (p["id"] == me) { myFx = p["factory"][0]; myFy = p["factory"][1]; }
    else enFx = p["factory"][0];
  }
  bool mirrorX = true;  // 2-player maps mirror across the vertical axis
  (void)enFx; (void)myFy;
  cout << "cma252-cpp" << endl;
  set<int> returning;
  map<int, int> stuck;
  int dropTarget = -1;      // planned dropoff cell
  int dropShip = -1;
  auto process = [&](json& obs) {
    int turn = obs["turn"];
    int left = MAXT - turn;
    // memory update
    double sumSeen = 0; int cntSeen = 0;
    for (int i = 0; i < N; i++) {
      auto& v = obs["halite"][i];
      if (!v.is_null()) {
        mem[i] = v.get<int>(); seen[i] = turn;
        if (initv[i] < 0) {
          initv[i] = (int)mem[i];
          // mirror: initial value of the mirrored cell (only valid if unseen there yet)
          if (mirrorX) {
            int x = i % W, y = i / W, m = idx(W - 1 - x, y);
            if (seen[m] < 0 && mem[m] < 0) mem[m] = mem[i] * 0.6;  // enemy side likely mined
          }
        }
      }
    }
    for (int i = 0; i < N; i++) if (!terrain[i] && mem[i] >= 0) { sumSeen += mem[i]; cntSeen++; }
    double avg = cntSeen ? sumSeen / cntSeen : 80;
    json own;
    vector<Enemy> enemies;
    vector<int> enemyBases;
    for (auto& p : obs["players"]) {
      if (p["id"] == me) own = p;
      else {
        enemyBases.push_back(idx(p["factory"][0], p["factory"][1]));
        for (auto& d : p["dropoffs"]) enemyBases.push_back(idx(d[0], d[1]));
        for (auto& s : p["ships"]) enemies.push_back({idx(s["x"], s["y"]), s["cargo"].get<int>(), p["id"].get<int>()});
      }
    }
    int bank = own["bank"];
    int home = idx(own["factory"][0], own["factory"][1]);
    vector<int> bases = {home};
    for (auto& d : own["dropoffs"]) bases.push_back(idx(d[0], d[1]));
    vector<Ship> ships;
    for (auto& s : own["ships"]) ships.push_back({s["id"].get<int>(), idx(s["x"], s["y"]), s["cargo"].get<int>()});
    vector<int> hd = bfs(bases);
    vector<int> ehd = enemyBases.empty() ? vector<int>(N, 99) : bfs(enemyBases);
    auto hal = [&](int p) -> double { return mem[p] >= 0 ? mem[p] : avg * 0.8; };
    auto cell = [&](int p) -> int { auto& v = obs["halite"][p]; return v.is_null() ? (int)max(0.0, mem[p]) : v.get<int>(); };

    // enemy reach: min weight of enemy that can be at cell t after moving
    vector<int> minEW(N, 1 << 20);   // lightest enemy weight possibly arriving at t (incl staying)
    vector<int> eAt(N, -1);          // enemy cargo at current cell
    vector<int> enemyNear(N, 0);     // for inspiration estimate
    for (auto& e : enemies) {
      eAt[e.pos] = e.cargo;
      minEW[e.pos] = min(minEW[e.pos], e.cargo);
      int mw = e.cargo - cell(e.pos) / MOVE_RATIO;
      if (mw >= 0)
        for (int k = 1; k < 5; k++) { int n = nb(e.pos, k); if (!terrain[n]) minEW[n] = min(minEW[n], mw); }
    }
    for (auto& e : enemies)
      for (int dy = -4; dy <= 4; dy++) for (int dx = -4 + abs(dy); dx <= 4 - abs(dy); dx++) enemyNear[idx(e.pos % W + dx, e.pos / W + dy)]++;
    // predicted next cell of heavy enemies (returning toward their base)
    map<int, int> huntBonus;  // cell -> value
    for (auto& e : enemies) {
      if (e.cargo < 300) continue;
      int mw = e.cargo - cell(e.pos) / MOVE_RATIO;
      bool canMove = mw >= 0;
      if (e.cargo >= 600 && canMove) {
        int best = e.pos, bd = ehd[e.pos];
        for (int k = 1; k < 5; k++) { int n = nb(e.pos, k); if (!terrain[n] && ehd[n] < bd) { bd = ehd[n]; best = n; } }
        huntBonus[best] = max(huntBonus[best], (int)(e.cargo * 0.6));
        huntBonus[e.pos] = max(huntBonus[e.pos], (int)(e.cargo * 0.25));
      } else {
        huntBonus[e.pos] = max(huntBonus[e.pos], (int)(e.cargo * (canMove ? 0.5 : 0.9)));
      }
    }

    int nships = ships.size();
    double estTotal = 0;
    for (int p = 0; p < N; p++) if (!terrain[p]) estTotal += hal(p);
    if (turn % 20 == 1) cerr << "turn " << turn << " est " << estTotal << " ships " << nships << endl;
    double shipValue = left > 60 ? 700 : (left > 25 ? 300 : 50);
    // returning state
    int queueMargin = P_QM + nships / (4 * (int)bases.size());
    for (auto& s : ships) {
      if (s.cargo == 0) returning.erase(s.id);
      if (s.cargo >= P_RET || (s.cargo >= 700 && hal(s.pos) < 60)) returning.insert(s.id);
      if (left <= hd[s.pos] + queueMargin && s.cargo > 0) returning.insert(s.id);
    }
    bool endgame = false;
    // dropoff planning
    if (P_DROP && dropTarget < 0 && bases.size() < 2 && turn >= 40 && turn <= 120 && nships >= 10) {
      double best = 0; int bc = -1;
      for (int p = 0; p < N; p++) {
        if (terrain[p] || hd[p] < 8 || hd[p] > 14 || ehd[p] < 7) continue;
        double s = 0;
        for (int dy = -4; dy <= 4; dy++) for (int dx = -4 + abs(dy); dx <= 4 - abs(dy); dx++) {
          int q = idx(p % W + dx, p / W + dy);
          if (!terrain[q]) s += hal(q);
        }
        if (s > best) { best = s; bc = p; }
      }
      if (bc >= 0 && best > 6000) dropTarget = bc;
    }
    if (dropTarget >= 0 && (bases.size() >= 2 || turn > 140)) { dropTarget = -1; dropShip = -1; }

    // target assignment
    sort(ships.begin(), ships.end(), [](const Ship& a, const Ship& b) { return a.cargo > b.cargo; });
    map<int, int> target;
    vector<vector<int>> sd(nships);
    for (int i = 0; i < nships; i++) sd[i] = bfs({ships[i].pos});
    set<int> claimed;
    string extra;
    bool reservedBank = false;
    // dropoff ship
    if (dropTarget >= 0) {
      int bi = -1, bd = 1 << 20;
      for (int i = 0; i < nships; i++) {
        if (returning.count(ships[i].id) && ships[i].id != dropShip) continue;
        if (sd[i][dropTarget] < bd) { bd = sd[i][dropTarget]; bi = i; }
      }
      if (bi >= 0) {
        dropShip = ships[bi].id;
        target[dropShip] = dropTarget;
        claimed.insert(dropTarget);
        if (bd < 4) reservedBank = true;
      }
    }
    struct Cand { double sc; int si, c; };
    vector<Cand> cands;
    for (int i = 0; i < nships; i++) {
      auto& s = ships[i];
      if (returning.count(s.id) || s.id == dropShip) continue;
      vector<Cand> mine;
      for (int c = 0; c < N; c++) {
        if (terrain[c]) continue;
        int d = sd[i][c];
        if (d > 40) continue;
        double hv = hal(c);
        if (enemyNear[c] >= 2) hv *= 1.6;  // inspiration
        double gain = min(hv * 0.6, (double)(MAXE - s.cargo));
        if (hv < 20) continue;
        // danger: lighter enemies around target
        if (minEW[c] <= s.cargo + 100 && d <= 2) gain *= 0.5;
        double sc = gain / (d + 1.5 + 0.25 * hd[c]);
        if (c == s.pos) sc *= 1.15;
        mine.push_back({sc, i, c});
      }
      // hunting targets for light ships
      if (s.cargo < 150) {
        for (auto& e : enemies) {
          if (e.cargo < s.cargo + 300) continue;
          int d = sd[i][e.pos];
          if (d > 5) continue;
          double sc = e.cargo * 0.35 * P_HUNT / 100.0 / (d + 1.0);
          mine.push_back({sc, i, -1 - e.pos});
        }
      }
      sort(mine.begin(), mine.end(), [](const Cand& a, const Cand& b) { return a.sc > b.sc; });
      if (mine.size() > 40) mine.resize(40);
      for (auto& m : mine) cands.push_back(m);
    }
    sort(cands.begin(), cands.end(), [](const Cand& a, const Cand& b) { return a.sc > b.sc; });
    map<int, int> huntersOn;
    for (auto& c : cands) {
      int sid = ships[c.si].id;
      if (target.count(sid)) continue;
      if (c.c < 0) {
        int ep = -1 - c.c;
        if (huntersOn[ep] >= 2) continue;
        huntersOn[ep]++;
        target[sid] = ep;
        continue;
      }
      if (claimed.count(c.c)) continue;
      claimed.insert(c.c);
      target[sid] = c.c;
    }

    // build preferences
    vector<vector<pair<double, int>>> prefs(nships);  // (score, dir)
    vector<int> prio(nships);
    for (int i = 0; i < nships; i++) {
      auto& s = ships[i];
      int here = cell(s.pos);
      int cost = here / MOVE_RATIO;
      bool canMove = s.cargo >= cost;
      bool ret = returning.count(s.id);
      vector<int> td;
      int tgt = -1;
      if (ret) td = hd;
      else if (target.count(s.id)) { tgt = target[s.id]; td = bfs({tgt}); }
      for (int k = 0; k < 5; k++) {
        if (k > 0 && !canMove) break;
        int n = nb(s.pos, k);
        if (terrain[n]) continue;  // reef: treat as not an option ('o' covers it)
        int wgt = k == 0 ? s.cargo : s.cargo - cost;
        double sc = 0;
        if (ret) {
          sc = -td[n] * 100.0;
          if (k == 0) sc -= 30;
        } else if (tgt >= 0) {
          sc = -td[n] * 40.0;
          if (k == 0 && n == tgt) sc += 10;
          if (k == 0 && n != tgt) sc -= 5;
          if (k > 0) sc += hal(n) * 0.01;  // tie-break toward richer path
        } else {
          sc = k == 0 ? hal(n) * 0.25 : -1;
        }
        if (s.id == dropShip && n == dropTarget) sc += 50;
        // collision risk
        if (minEW[n] <= wgt) {
          double p = (eAt[n] >= 0) ? 0.6 : 0.4;
          if (minEW[n] < wgt) p += 0.1;
          sc -= p * (wgt + shipValue);
        }
        // light-ship attack opportunities
        if (eAt[n] > wgt + 50 && minEW[n] >= wgt + 1) sc += 0.0;  // covered by huntBonus
        auto hb = huntBonus.find(n);
        if (hb != huntBonus.end() && wgt < 200 && !ret) {
          // only if no lighter-or-equal enemy can reach n
          if (minEW[n] > wgt) sc += hb->second * P_HUNT / 100.0;
        }
        // endgame: never stay on base when cargo is 0 near end, to free space
        if (left < 30 && s.cargo == 0 && n == home && k == 0 && nships > 1) sc -= 40;
        prefs[i].push_back({sc, k});
      }
      if (prefs[i].empty()) prefs[i].push_back({0, 0});
      bool hasStay = false;
      for (auto& p : prefs[i]) if (p.second == 0) hasStay = true;
      if (!hasStay) prefs[i].push_back({-1e9, 0});
      sort(prefs[i].begin(), prefs[i].end(), [](auto& a, auto& b) { return a.first > b.first; });
      prio[i] = (!canMove ? 3000000 : 0) + (ret ? 1000000 : 0) + s.cargo;
    }
    // final-turn crash into base allowed
    vector<int> order(nships);
    for (int i = 0; i < nships; i++) order[i] = i;
    sort(order.begin(), order.end(), [&](int a, int b) { return prio[a] > prio[b]; });
    map<int, int> occ;  // cell -> ship index
    vector<int> chosen(nships, -1);
    vector<int> dest(nships, -1);
    function<bool(int, set<int>&)> place = [&](int i, set<int>& vis) -> bool {
      for (auto& pr : prefs[i]) {
        int n = nb(ships[i].pos, pr.second);
        if (pr.second == 0) n = ships[i].pos;
        if (vis.count(n)) continue;
        vis.insert(n);
        auto it = occ.find(n);
        if (it == occ.end() || place(it->second, vis)) {
          occ[n] = i; chosen[i] = pr.second; dest[i] = n;
          return true;
        }
      }
      return false;
    };
    // Endgame crash: in last turns ships adjacent to a base may all move in (lightest steals all).
    set<int> crashers;
    if (left <= 2) {
      for (int i = 0; i < nships; i++) {
        auto& s = ships[i];
        if (s.cargo == 0) continue;
        int cost = cell(s.pos) / MOVE_RATIO;
        if (s.cargo < cost) continue;
        for (int k = 1; k < 5; k++) {
          int n = nb(s.pos, k);
          if (find(bases.begin(), bases.end(), n) != bases.end() && hd[s.pos] == 1) { crashers.insert(i); chosen[i] = k; dest[i] = n; break; }
        }
      }
    }
    for (int i : order) {
      if (crashers.count(i)) continue;
      set<int> vis;
      for (int c : crashers) vis.insert(dest[c]);
      if (!place(i, vis)) { chosen[i] = 0; dest[i] = ships[i].pos; }
    }
    // dropoff conversion
    int convertShip = -1;
    for (int i = 0; i < nships; i++) {
      auto& s = ships[i];
      if (s.id == dropShip && s.pos == dropTarget) {
        int costNeeded = DROPCOST - s.cargo - cell(s.pos);
        if (bank >= costNeeded && find(bases.begin(), bases.end(), s.pos) == bases.end()) {
          convertShip = i; bank -= max(0, costNeeded);
        }
      }
    }
    ostringstream out;
    for (int i = 0; i < nships; i++) {
      if (i == convertShip) { out << "c " << ships[i].id << " "; continue; }
      out << "m " << ships[i].id << " " << DC[chosen[i]] << " ";
    }
    if (convertShip >= 0) { dropTarget = -1; dropShip = -1; }
    // spawn
    bool homeBusy = false;
    for (int i = 0; i < nships; i++) if (dest[i] == home && i != convertShip) homeBusy = true;
    // enemy sitting on / next to factory with weight 0 -> tie sink risk
    bool enemyThreat = minEW[home] <= 0;
    int spawnUntil = P_SPAWN;
    int reserve = reservedBank ? DROPCOST : 0;
    if (dropTarget >= 0 && turn > 50) reserve = DROPCOST / 2;
    if (bank - reserve >= SHIPCOST && !homeBusy && !enemyThreat && turn <= spawnUntil && nships < P_MAXS && estTotal / (nships + 1) > P_K) out << "g";
    (void)endgame; (void)extra;
    cout << out.str() << endl;
  };
  while (getline(cin, line)) {
    if (line.empty()) continue;
    json obs = json::parse(line);
    process(obs);
  }
  return 0;
}
