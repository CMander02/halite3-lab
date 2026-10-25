#include "BasicGenerator.hpp"
#include <queue>
#include <random>
#include <unordered_set>
#include "BlurTileGenerator.hpp"
#include "FractalValueNoiseTileGenerator.hpp"

namespace hlt {
namespace mapgen {

/**
 * Generate a map based on parameters.
 * @param[out] map The map to generate.
 * @param parameters The parameters to use.
 */
void Generator::generate(Map &map, const MapParameters &parameters) {
    switch (parameters.type) {
    case MapType::Basic:
        BasicGenerator(parameters).generate(map);
        break;
    case MapType::BlurTile:
        BlurTileGenerator(parameters).generate(map);
        break;
    case MapType::Fractal:
        FractalValueNoiseTileGenerator(parameters).generate(map);
        break;
    }
    if (Constants::get().REEF_PERCENT == 0) return;
    unsigned long rows = static_cast<unsigned long>(std::sqrt(parameters.num_players));
    while (parameters.num_players % rows) --rows;
    const auto cols = parameters.num_players / rows;
    const int tw = map.width / cols, th = map.height / rows;
    std::mt19937 terrain_rng(parameters.seed ^ 0x5eed1234U);
    for (int y = 0; y < th; ++y) for (int x = 0; x < tw; ++x) {
        if (terrain_rng() % 100 >= Constants::get().REEF_PERCENT) continue;
        std::vector<Location> group;
        bool protected_cell = false;
        for (unsigned long ry = 0; ry < rows; ++ry) for (unsigned long cx = 0; cx < cols; ++cx) {
            Location loc{x + static_cast<int>(cx) * tw, y + static_cast<int>(ry) * th};
            for (const auto &factory : map.factories) if (map.distance(factory, loc) <= 2) protected_cell = true;
            group.push_back(loc);
        }
        if (protected_cell) continue;
        for (const auto &loc : group) map.at(loc).reef = true;
        std::unordered_set<Location> visited;
        std::queue<Location> pending;
        pending.push(map.factories.front()); visited.insert(pending.front());
        while (!pending.empty()) {
            auto loc = pending.front(); pending.pop();
            for (const auto &next : map.get_neighbors(loc)) {
                if (!map.at(next).reef && visited.insert(next).second) pending.push(next);
            }
        }
        size_t water = 0;
        for (const auto &row : map.grid) for (const auto &cell : row) water += !cell.reef;
        if (visited.size() != water) for (const auto &loc : group) map.at(loc).reef = false;
    }
    for (auto &row : map.grid) for (auto &cell : row) if (cell.reef) cell.energy = 0;
}

/**
 * Read a MapType from command line input.
 * @param istream The input stream.
 * @param[out] type The MapType to read.
 * @return The input stream.
 */
std::istream &operator>>(std::istream &istream, MapType &type) {
    std::string type_string;
    istream >> type_string;
    if (type_string == "basic") {
        type = MapType::Basic;
    } else if (type_string == "blur_tile") {
        type = MapType::BlurTile;
    } else if (type_string == "fractal") {
        type = MapType::Fractal;
    } else {
        throw std::runtime_error("Illegal map type");
    }
    return istream;
}

std::ostream &operator<<(std::ostream &ostream, MapType type) {
    std::string str;
    switch (type) {
    case MapType::Basic: {
        str = "basic";
        break;
    }
    case MapType::BlurTile: {
        str = "blur_tile";
        break;
    }
    case MapType::Fractal: {
        str = "fractal";
        break;
    }
    default: {
        throw std::runtime_error("Illegal map type");
    }
    }
    ostream << str;

    return ostream;
}

}
}
