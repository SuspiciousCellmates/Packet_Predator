import customtkinter as ctk

class MainMenu(ctk.CTkFrame):
    def __init__(self, parent, controller, radio):
        super().__init__(parent)
        self.controller = controller
        self.radio = radio
        self.nodes = []
        
        label = ctk.CTkLabel(self, text = "Packet Predator", font=("CascadiaCode", 30))
        label.pack(pady=(30,30), padx=10)

        
        spoof_button = ctk.CTkButton(self, text="Spoof",  command=lambda: controller.show_frame("SpoofSettings"))
        spoof_button.pack(pady=10, padx=10)

        sniff_button = ctk.CTkButton(self, text="Sniff",  command=lambda:controller.show_frame("SniffSettings"))
        sniff_button.pack(pady=10, padx=10)
        
        radio_config_button = ctk.CTkButton(self, text="Radio Config",  command=lambda:controller.show_frame("ConfigRadio"))
        radio_config_button.pack(pady=10, padx=10)

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(side="bottom", pady=10, padx=10)
        
        close_button = ctk.CTkButton(button_frame, command=parent.quit, text="Close")
        close_button.pack(side="bottom", pady=10, padx=10)
        
      
        

