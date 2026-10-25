#include "Observation.hpp"
namespace hlt {
nlohmann::json make_observation(const Map &map, const Store &store, Player::id_type viewer, unsigned long turn) {
    std::vector<Location> sources;
    const auto &self = store.get_player(viewer);
    sources.push_back(self.factory);
    for (const auto &dropoff : self.dropoffs) sources.push_back(dropoff.location);
    for (const auto &[id, loc] : self.entities) sources.push_back(loc);
    auto visible = [&](const Location &loc) {
        if (!Constants::get().FOG_ENABLED) return true;
        for (const auto &source : sources) if (map.distance(source, loc) <= Constants::get().VISION_RADIUS) return true;
        return false;
    };
    nlohmann::json j = {{"type", "turn"}, {"turn", turn}, {"player_id", viewer.value},
                        {"width", map.width}, {"height", map.height}};
    j["halite"] = nlohmann::json::array();
    j["terrain"] = nlohmann::json::array();
    for (int y = 0; y < map.height; ++y) for (int x = 0; x < map.width; ++x) {
        j["halite"].push_back(visible({x,y}) ? nlohmann::json(map.at(x,y).energy) : nlohmann::json(nullptr));
        j["terrain"].push_back(map.at(x,y).reef ? 1 : 0);
    }
    j["players"] = nlohmann::json::array();
    for (const auto &[pid, player] : store.get_players()) {
        nlohmann::json item = {{"id", pid.value}, {"factory", {player.factory.x, player.factory.y}}};
        item["bank"] = pid == viewer || !Constants::get().FOG_ENABLED ? nlohmann::json(player.energy) : nlohmann::json(nullptr);
        item["ships"] = nlohmann::json::array(); item["dropoffs"] = nlohmann::json::array();
        for (const auto &[id, loc] : player.entities) if (pid == viewer || visible(loc)) {
            item["ships"].push_back({{"id", id.value}, {"x", loc.x}, {"y", loc.y}, {"cargo", store.get_entity(id).energy}});
        }
        for (const auto &dropoff : player.dropoffs) if (pid == viewer || visible(dropoff.location))
            item["dropoffs"].push_back({dropoff.location.x, dropoff.location.y});
        j["players"].push_back(item);
    }
    return j;
}
}
