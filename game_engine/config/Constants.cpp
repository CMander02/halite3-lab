#include "Constants.hpp"

#include "nlohmann/json.hpp"

/** A JSON key and value corresponding to a game constant. */
#define FIELD_TO_JSON(x) {#x, constants.x}

/** Get a field from JSON. */
#define FIELD_FROM_JSON(x) json.at(#x)

namespace hlt {

/**
 * Encode the constants to JSON.
 * @param[out] json The JSON output.
 * @param constants The constants.
 */
void to_json(nlohmann::json &json, const Constants &constants) {
    json = {
            FIELD_TO_JSON(LAB_PROTOCOL),
            FIELD_TO_JSON(FOG_ENABLED),
            FIELD_TO_JSON(VISION_RADIUS),
            FIELD_TO_JSON(REEF_PERCENT),
            FIELD_TO_JSON(LIGHT_SHIP_COLLISIONS),
            FIELD_TO_JSON(STRICT_ERRORS),

            FIELD_TO_JSON(MAX_PLAYERS),

            FIELD_TO_JSON(DEFAULT_MAP_WIDTH),
            FIELD_TO_JSON(DEFAULT_MAP_HEIGHT),
            FIELD_TO_JSON(MAX_CELL_PRODUCTION),
            FIELD_TO_JSON(MIN_CELL_PRODUCTION),

            FIELD_TO_JSON(MAX_ENERGY),
            FIELD_TO_JSON(NEW_ENTITY_ENERGY_COST),
            FIELD_TO_JSON(INITIAL_ENERGY),

            FIELD_TO_JSON(DROPOFF_COST),
            FIELD_TO_JSON(MOVE_COST_RATIO),
            FIELD_TO_JSON(DROPOFF_PENALTY_RATIO),
            FIELD_TO_JSON(EXTRACT_RATIO),

            FIELD_TO_JSON(PERSISTENCE),
            FIELD_TO_JSON(FACTOR_EXP_1),
            FIELD_TO_JSON(FACTOR_EXP_2),

            FIELD_TO_JSON(MIN_TURNS),
            FIELD_TO_JSON(MIN_TURN_THRESHOLD),
            FIELD_TO_JSON(MAX_TURNS),
            FIELD_TO_JSON(MAX_TURN_THRESHOLD),

            FIELD_TO_JSON(CAPTURE_ENABLED),
            FIELD_TO_JSON(CAPTURE_RADIUS),
            FIELD_TO_JSON(SHIPS_ABOVE_FOR_CAPTURE),

            FIELD_TO_JSON(INSPIRATION_ENABLED),
            FIELD_TO_JSON(INSPIRED_EXTRACT_RATIO),
            FIELD_TO_JSON(INSPIRED_BONUS_MULTIPLIER),
            FIELD_TO_JSON(INSPIRED_MOVE_COST_RATIO),
            FIELD_TO_JSON(INSPIRATION_RADIUS),
            FIELD_TO_JSON(INSPIRATION_SHIP_COUNT)
    };
}

/**
 * Decode the constants from JSON.
 * @param json The JSON input.
 * @param[out] constants The decoded constants.
 */
void from_json(const nlohmann::json &json, Constants &constants) {
    constants.LAB_PROTOCOL = json.value("LAB_PROTOCOL", constants.LAB_PROTOCOL);
    constants.FOG_ENABLED = json.value("FOG_ENABLED", constants.FOG_ENABLED);
    constants.VISION_RADIUS = json.value("VISION_RADIUS", constants.VISION_RADIUS);
    constants.REEF_PERCENT = json.value("REEF_PERCENT", constants.REEF_PERCENT);
    constants.LIGHT_SHIP_COLLISIONS = json.value("LIGHT_SHIP_COLLISIONS", constants.LIGHT_SHIP_COLLISIONS);
    constants.STRICT_ERRORS = json.value("STRICT_ERRORS", constants.STRICT_ERRORS);
    constants.MAX_PLAYERS = json.value("MAX_PLAYERS", constants.MAX_PLAYERS);
    constants.DEFAULT_MAP_WIDTH = json.value("DEFAULT_MAP_WIDTH", constants.DEFAULT_MAP_WIDTH);
    constants.DEFAULT_MAP_HEIGHT = json.value("DEFAULT_MAP_HEIGHT", constants.DEFAULT_MAP_HEIGHT);
    constants.MAX_CELL_PRODUCTION = json.value("MAX_CELL_PRODUCTION", constants.MAX_CELL_PRODUCTION);
    constants.MIN_CELL_PRODUCTION = json.value("MIN_CELL_PRODUCTION", constants.MIN_CELL_PRODUCTION);
    constants.MAX_ENERGY = json.value("MAX_ENERGY", constants.MAX_ENERGY);
    constants.NEW_ENTITY_ENERGY_COST = json.value("NEW_ENTITY_ENERGY_COST", constants.NEW_ENTITY_ENERGY_COST);
    constants.INITIAL_ENERGY = json.value("INITIAL_ENERGY", constants.INITIAL_ENERGY);
    constants.DROPOFF_COST = json.value("DROPOFF_COST", constants.DROPOFF_COST);
    constants.MOVE_COST_RATIO = json.value("MOVE_COST_RATIO", constants.MOVE_COST_RATIO);
    constants.DROPOFF_PENALTY_RATIO = json.value("DROPOFF_PENALTY_RATIO", constants.DROPOFF_PENALTY_RATIO);
    constants.EXTRACT_RATIO = json.value("EXTRACT_RATIO", constants.EXTRACT_RATIO);
    constants.PERSISTENCE = json.value("PERSISTENCE", constants.PERSISTENCE);
    constants.FACTOR_EXP_1 = json.value("FACTOR_EXP_1", constants.FACTOR_EXP_1);
    constants.FACTOR_EXP_2 = json.value("FACTOR_EXP_2", constants.FACTOR_EXP_2);
    constants.MIN_TURNS = json.value("MIN_TURNS", constants.MIN_TURNS);
    constants.MIN_TURN_THRESHOLD = json.value("MIN_TURN_THRESHOLD", constants.MIN_TURN_THRESHOLD);
    constants.MAX_TURNS = json.value("MAX_TURNS", constants.MAX_TURNS);
    constants.MAX_TURN_THRESHOLD = json.value("MAX_TURN_THRESHOLD", constants.MAX_TURN_THRESHOLD);
    constants.CAPTURE_ENABLED = json.value("CAPTURE_ENABLED", constants.CAPTURE_ENABLED);
    constants.CAPTURE_RADIUS = json.value("CAPTURE_RADIUS", constants.CAPTURE_RADIUS);
    constants.SHIPS_ABOVE_FOR_CAPTURE = json.value("SHIPS_ABOVE_FOR_CAPTURE", constants.SHIPS_ABOVE_FOR_CAPTURE);
    constants.INSPIRATION_ENABLED = json.value("INSPIRATION_ENABLED", constants.INSPIRATION_ENABLED);
    constants.INSPIRED_EXTRACT_RATIO = json.value("INSPIRED_EXTRACT_RATIO", constants.INSPIRED_EXTRACT_RATIO);
    constants.INSPIRED_BONUS_MULTIPLIER = json.value("INSPIRED_BONUS_MULTIPLIER", constants.INSPIRED_BONUS_MULTIPLIER);
    constants.INSPIRED_MOVE_COST_RATIO = json.value("INSPIRED_MOVE_COST_RATIO", constants.INSPIRED_MOVE_COST_RATIO);
    constants.INSPIRATION_RADIUS = json.value("INSPIRATION_RADIUS", constants.INSPIRATION_RADIUS);
    constants.INSPIRATION_SHIP_COUNT = json.value("INSPIRATION_SHIP_COUNT", constants.INSPIRATION_SHIP_COUNT);
    if ((constants.FOG_ENABLED || constants.REEF_PERCENT > 0) && !constants.LAB_PROTOCOL) {
        throw std::runtime_error("Fog and terrain require LAB_PROTOCOL=true");
    }
    if (constants.VISION_RADIUS < 0 || constants.REEF_PERCENT > 40) {
        throw std::runtime_error("VISION_RADIUS must be nonnegative; REEF_PERCENT must be <= 40");
    }

}

}
