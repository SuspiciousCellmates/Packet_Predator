from enum import Enum, auto

# |                  HEADER               |                 PAYLOAD           |
# | DEST | SRC | CONFIG_TYPE | TIMESTAMP  | SETTING_INDEX     | SETTING_VAL   |

VALID_CONFIG_SETTINGS = {
"raw" : 0,
"round_count" : 1,
"button_lockout" : 2,
"pattern_led" : 3,
"pattern_time" : 4,
"pattern_led_count" : 5,
"another_task_value" : 1,
"num_settings": 3,
"round_difficulty" : 2,
}

class EVENT_TYPES(Enum): 
    MEETING_START = 1
    MEETING_END = 2
    MATCH_END = 3
    SABOTAGE = 4
    COMPLETED = 5
    CHECK_IN = 6
    PLAYER_DEATH = 7
    TASK_FAIL = 8