#include "ExperimentGenerator.hpp"
#include <algorithm>
#include <cmath>
#include <queue>
#include <set>
#include <unordered_set>

namespace hlt { namespace mapgen {
namespace {
std::vector<Location> orbit(Location p, int n, unsigned long players) {
    std::set<std::pair<int,int>> points;
    if (players == 2) {
        points.emplace(p.x, p.y); points.emplace(n - 1 - p.x, n - 1 - p.y);
    } else {
        for (int reflect = 0; reflect < (players == 8 ? 2 : 1); ++reflect) {
            int x = reflect ? p.y : p.x, y = reflect ? p.x : p.y;
            for (int i = 0; i < 4; ++i) {
                points.emplace(x, y);
                const int next = n - 1 - y; y = x; x = next;
            }
        }
    }
    std::vector<Location> result;
    for (auto [x,y] : points) result.emplace_back(x,y);
    return result;
}
double noise(int x, int y, unsigned int seed) {
    uint32_t v = seed ^ (uint32_t(x) * 374761393U) ^ (uint32_t(y) * 668265263U);
    v = (v ^ (v >> 13)) * 1274126177U;
    return double(v ^ (v >> 16)) / double(UINT32_MAX);
}
double smooth(int x, int y, int scale, unsigned int seed) {
    const int a = x / scale, b = y / scale;
    const double u = double(x % scale) / scale, v = double(y % scale) / scale;
    return (1-u)*(1-v)*noise(a,b,seed)+u*(1-v)*noise(a+1,b,seed)+(1-u)*v*noise(a,b+1,seed)+u*v*noise(a+1,b+1,seed);
}
bool connected(const Map &map) {
    std::unordered_set<Location> seen;
    std::queue<Location> todo;
    todo.push(map.factories.front()); seen.insert(todo.front());
    while (!todo.empty()) {
        auto p = todo.front(); todo.pop();
        for (const auto &q : map.get_neighbors(p)) if (!map.at(q).reef && seen.insert(q).second) todo.push(q);
    }
    size_t water = 0;
    for (const auto &row : map.grid) for (const auto &c : row) water += !c.reef;
    return water == seen.size();
}
}

void generate_experiment(Map &map, const MapParameters &parameters) {
    const auto &c = Constants::get();
    const int n = map.width;
    if (n != map.height || n < 16 || n > 64 || (parameters.num_players != 2 && parameters.num_players != 4 && parameters.num_players != 8))
        throw std::runtime_error("Symmetric experimental maps require square 16..64, 2/4/8 players");
    Location first = parameters.num_players == 8 ? Location(3*n/16,6*n/16) : Location(n/4,n/4);
    map.factories = orbit(first,n,parameters.num_players);
    if (map.factories.size() != parameters.num_players) throw std::runtime_error("Degenerate factory orbit");
    std::vector<std::vector<Location>> groups;
    std::unordered_set<Location> visited;
    for (int y=0;y<n;++y) for (int x=0;x<n;++x) {
        if (visited.count({x,y})) continue;
        auto group = orbit({x,y},n,parameters.num_players);
        for (auto p : group) visited.insert(p);
        groups.push_back(std::move(group));
    }
    std::mt19937 rng(parameters.seed ^ 0x71b5a92U);
    std::shuffle(groups.begin(),groups.end(),rng);
    for (const auto &group : groups) {
        auto p = group.front();
        bool protect = false;
        for (const auto &q : group) for (const auto &base : map.factories) protect |= map.distance(q,base) <= 2;
        const double dx = p.x-(n-1)/2.0, dy=p.y-(n-1)/2.0;
        const double radius = std::sqrt(dx*dx+dy*dy)/n;
        bool reef = c.MAP_STYLE != 1 && (rng()%100 < c.REEF_PERCENT);
        if (c.MAP_STYLE == 3) reef = radius > .17 && radius < .26 && std::abs(dx)>2.0 && std::abs(dy)>2.0;
        if (protect || !reef) continue;
        for (auto q : group) map.at(q).reef = true;
        if (!connected(map)) for (auto q : group) map.at(q).reef = false;
    }
    std::vector<double> weights;
    double total = 0;
    for (const auto &group : groups) {
        double weight=0;
        for (auto p : group) {
            double value=.55*smooth(p.x,p.y,8,parameters.seed)+.3*smooth(p.x,p.y,4,parameters.seed+1)+.15*noise(p.x,p.y,parameters.seed+2);
            value=std::pow(value,3);
            if (c.MAP_STYLE==4) {
                const double dx=p.x-(n-1)/2.0,dy=p.y-(n-1)/2.0;
                value *= .25+3*std::exp(-(dx*dx+dy*dy)/(n*n*.06));
            }
            if (c.MAP_STYLE==5) value *= .25+std::pow(.5+.5*std::sin((p.x+2*p.y)*.45+parameters.seed),4)*4;
            weight+=value;
        }
        weight/=group.size();
        bool base=std::find(map.factories.begin(),map.factories.end(),group.front())!=map.factories.end();
        if (map.at(group.front()).reef || base) weight=0;
        weights.push_back(weight); total+=weight*group.size();
    }
    const long long budget = c.ORE_PER_PLAYER > 0 ? c.ORE_PER_PLAYER*parameters.num_players : 60000LL*parameters.num_players;
    long long assigned=0,capacity=0;
    for (size_t i=0;i<groups.size();++i) {
        const auto amount=weights[i] > 0 ? std::min<long long>(c.MAX_CELL_PRODUCTION,std::floor(weights[i]*budget/total)) : 0;
        for (auto p : groups[i]) map.at(p).energy=amount;
        assigned+=amount*groups[i].size();
        if (weights[i]>0) capacity+=c.MAX_CELL_PRODUCTION*groups[i].size();
    }
    if (budget>capacity) throw std::runtime_error("Ore budget exceeds navigable cell capacity");
    // Distribute clipping/rounding remainder by complete symmetry orbits.
    bool changed=true;
    while (assigned<budget && changed) {
        changed=false;
        for (size_t i=0;i<groups.size();++i) {
            const auto size=groups[i].size();
            if (weights[i]<=0 || map.at(groups[i].front()).energy>=c.MAX_CELL_PRODUCTION || assigned+size>budget) continue;
            for (auto p : groups[i]) ++map.at(p).energy;
            assigned+=size;changed=true;
        }
    }
}
}}
