#!/usr/bin/env python3

# Put what you are currently working on here (in case of context switch):
import customtkinter
from gui.main_menu import MainMenu
from gui.spoof_settings import SpoofSettings
from gui.config_radio import ConfigRadio
from driver.nrf905 import NRF905
from nodes.node import NodeType, Node

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.frames = {}
        self.frame_dimensions = {
            "MainMenu": (600,750),
            "SpoofSettings": (600, 750),
            "SniffSettings": (600,750),
            "ConfigRadio" : (600,750),
        }
        # The below also sets CascadiaCode as global font option, copy the .ttf to /usr/share/fonts
        customtkinter.set_default_color_theme("./resources/theme.json")
        self.nodes = {}
        self.settings = {}
        
        self.register_nodes()
        
        self.radio_config = None
        self.radio = NRF905(self.radio_config)
        
        for F in (MainMenu, SpoofSettings, ConfigRadio):
            frame = F(parent=self, controller=self, radio=self.radio)
            self.frames[F.__name__] = frame
            frame.place(x=0, y=0, relwidth=1, relheight=1)
            frame.lower()
            
        self.show_frame("MainMenu")

    def show_frame(self, page_name):
        for frame in self.frames.values():
            frame.lower()
        self.frames[page_name].tkraise()
        
        frame = self.frames[page_name]
        self.update_idletasks()

        width, height = self.frame_dimensions[page_name]

        self.geometry(self.CenterWindowToDisplay(width, height))
        self.update_idletasks()


    def CenterWindowToDisplay(self, width: int, height: int, scale_factor: float = 1):
        """Centers the window to the main display/monitor"""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        scaled_width = int(width * scale_factor)
        scaled_height = int(height * scale_factor)

        x = (screen_width - scaled_width) // 2
        y = (screen_height - scaled_height) // 2

        return f"{scaled_width}x{scaled_height}+{x}+{y}"


    def configure_radio(self, radio_config):
        self.radio.write_config(radio_config)

    def register_nodes(self):
        # Redundancy here, the Nodes themselves store their type, and then they are also stored in the dict under the node type key.
        task_node = Node(node_type= NodeType.TASK, 
                         friendly_name= "Simon Says",
                         address= 0x01,
                         config_settings=   {
                             "num_settings" : 3,
                             "round_count": 1,
                             "round_difficulty" : 2,
                             })
        
        self.nodes[task_node.friendly_name] = task_node
        
        task_node = Node(node_type=NodeType.TASK, 
                         friendly_name="Guitar Hero", 
                         config_settings={
                             "num_settings" : 3,
                             "guitar_count": 1,
                             "round_difficulty" : 2,
                             },
                         address= 0x02)
        self.nodes[task_node.friendly_name] = task_node
        
        player_node = Node(node_type=NodeType.PLAYER,
                           friendly_name="Player 1",
                           config_settings= {
                               "number_of_others" : 1,
                               "imposter" : 2,
                               "player_strings": 3,
                           },
                           address=0x01)
        self.nodes[player_node.friendly_name] = player_node
        player_node = Node(node_type=NodeType.PLAYER,
                           friendly_name="Player 2",
                           config_settings= {
                               "number_of_others" : 1,
                               "imposter" : 2,
                               "player_strings": 3,
                           },
                           address=0x02)
        self.nodes[player_node.friendly_name] = player_node
        
        for _, node in self.nodes.items():
            for setting, value in node.config_settings.items():
                self.settings[setting] = value
        
        print(self.settings)

def main():
    customtkinter.set_appearance_mode("dark")
    customtkinter.set_default_color_theme("blue")
    app = App()
    app.title("")
    app.mainloop()

if __name__ == "__main__":
    main()
