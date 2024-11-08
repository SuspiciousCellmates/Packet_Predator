from enum import Enum
from dataclasses import dataclass, field

class NodeType(Enum):
    INVALID= 0
    GOD = 1
    GAME_CONTROLLER = 2
    PLAYER = 3
    TASK = 4
    AMBIENT = 5

@dataclass
class Node:
    node_type: NodeType
    friendly_name: str
    address: int
    config_settings: dict = field(default_factory=dict)
