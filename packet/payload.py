from dataclasses import dataclass, field

@dataclass
class Payload:
    gui_fields: dict = field(default_factory=dict)
    