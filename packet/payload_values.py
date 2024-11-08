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
    INIT = auto()
    START = auto()
    STOP = auto()
    SABOTAGE = auto()
    COMPLETED = auto()
    RUNNING = auto()
    PAUSE = auto()