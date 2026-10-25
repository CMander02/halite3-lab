#pragma once
#include "Map.hpp"
#include "Store.hpp"
#include "nlohmann/json.hpp"
namespace hlt {
nlohmann::json make_observation(const Map &map, const Store &store, Player::id_type viewer, unsigned long turn);
}
