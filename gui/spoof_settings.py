import customtkinter as ctk
from driver.nrf905 import NRF905
from gui.custom.pp_combobox import MyComboBox
from nodes.node import Node, NodeType
from packet.packet import PacketType, Packet
from packet.payload_values import *
from datetime import datetime

class SpoofSettings(ctk.CTkFrame):
    def __init__(self, parent, controller, radio: NRF905):
        super().__init__(parent)
        self.controller = controller
        self.parent = parent
        self.radio = radio

        self.setup_gui()
        self.create_buttons()
        self.create_input_fields()
        
        self.dest_node: Node = None
        self.src_node: Node = None
        self.packet_type: PacketType = None
        self.packet= Packet()

    def setup_gui(self):
        label = ctk.CTkLabel(self, text="Spoof Settings")
        label.pack(pady=(20, 30), padx=10)

        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(side="bottom", pady=10, padx=10)

        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=10)
        
    def create_buttons(self):
        launch_button = ctk.CTkButton(
            self.button_frame,
            text="Launch",
            width=100,
            command= self.launch_packet,
        )
        launch_button.pack(side="left", pady=10, padx=(10, 5))

        back_button = ctk.CTkButton(
            self.button_frame,
            text="Cancel",
            width=100,
            
            command=lambda: self.parent.show_frame("MainMenu"),
        )
        back_button.pack(side="left", pady=10, padx=(10, 5))

        clear_packet_button = ctk.CTkButton(
            self.button_frame,
            text="Clear Packet",
            width=100,
            command=self.clear_packet,
        )
        clear_packet_button.pack(side="left", pady=10, padx=10)
        
    def clear_packet(self):
        self.packet = Packet()
        
    def create_input_fields(self):
        self.dest_node_frame = ctk.CTkFrame(self.input_frame)
        self.dest_node_frame.pack(side='top')
        self.dest_label = ctk.CTkLabel(self.dest_node_frame, text="Dest Node")
        self.dest_label.pack(side='left')
        
        self.dest_node_type_box = MyComboBox(self.dest_node_frame, values=[e.name for e in NodeType], width=200, 
                                         command=lambda selected_value: self.populate_node_names(selected_value, self.dest_node_id_box))
        self.dest_node_type_box.pack(side='left', padx= 20)
        self.dest_node_id_box = MyComboBox(self.dest_node_frame, width= 200, command=lambda selected_value: self.choose_node(selected_value, self.dest_node_type_box.get(), "DEST"))
        self.dest_node_id_box.pack(side='left', padx= 20)
        
        self.src_node_frame = ctk.CTkFrame(self.input_frame)
        self.src_node_frame.pack(side='top', pady = 20)
        self.src_label = ctk.CTkLabel(self.src_node_frame, text="Source Node")
        self.src_label.pack(side='left')
        
        self.src_node_type_box = MyComboBox(self.src_node_frame, values=[e.name for e in NodeType], width=200, 
                                        command=lambda selected_value: self.populate_node_names(selected_value, self.src_node_id_box))
        self.src_node_type_box.pack(side='left', padx= 20)
        
        self.src_node_id_box = MyComboBox(self.src_node_frame, width= 200,command=lambda selected_value: self.choose_node(selected_value, self.src_node_type_box.get(), "SOURCE"))
        self.src_node_id_box.pack(side='left', padx= 20)
        
        self.payload_type_frame = ctk.CTkFrame(self.input_frame)
        self.payload_type_frame.pack(side='top', pady = 20)
        
        self.payload_label = ctk.CTkLabel(self.payload_type_frame, text="Payload Type")
        self.payload_label.pack(side='left', padx= 20)
        
        self.payloads = MyComboBox(self.payload_type_frame, values=[e.name for e in PacketType], width= 400, command= self.populate_payload_frame)
        self.payloads.pack(side='left')
        
        self.payload_config_frame = ctk.CTkScrollableFrame(self.input_frame, width = 500, height=300)
        self.payload_config_frame.pack(side='top')

    def choose_node(self, selected_value, node_type, direction):
        if direction == "DEST":
            self.dest_node = self.controller.nodes[selected_value]
            self.populate_payload_frame(self.payloads.get())
            print(self.dest_node)
        elif direction == "SOURCE":
            self.src_node = self.controller.nodes[selected_value]
            print(self.src_node)
        else:
            raise ValueError("I don't even know how you did this...")


    def populate_node_names(self, selected_value, combo_box):
        node_key = getattr(NodeType, selected_value, None)       
        
        # Check if there are nodes available
        if self.controller.nodes:
            # Set node friendly names in the combo box
            node_names_of_type = [node_name for node_name, node in self.controller.nodes.items() if node.node_type == node_key]
            combo_box.configure(values=node_names_of_type)
            # Set the first node as the default selected value (if nodes exist)
            combo_box.set("Select Node")
        else:
            # Handle case when there are no nodes
            combo_box.configure(values=[])
            combo_box.set("No Nodes Available")

    def pack_payload_value(self, packet_type, entry, value):
        self.packet.packet_type = packet_type
            
        index = self.controller.settings[entry]
        if value:
            self.packet.stage_payload(index=index, value=value)
        else:
            self.packet.stage_payload(index, None)
            
        print(self.packet.staged_payload)
        
        # TODO: View the payload somehow in the gui before sending?
        
    def populate_payload_frame(self, selected_value):
        for widget in self.payload_config_frame.winfo_children():
            widget.destroy()
        self.packet.unstage_payload()
        self.packet_type = getattr(PacketType, self.payloads.get(), None)
        if selected_value == "CONFIG":
            settings = self.dest_node.config_settings
            for i, entry in enumerate(settings):
                label = ctk.CTkLabel(self.payload_config_frame, text=entry)
                value = ctk.CTkEntry(self.payload_config_frame, placeholder_text="")
                pack_button = ctk.CTkButton(self.payload_config_frame, text="Pack", command= lambda e=entry, v=value: self.pack_payload_value(self.packet_type, e, v.get()))
                label.grid(row= i, column=0, sticky="w", pady = 10, padx=10)
                value.grid(row = i, column=1, sticky="w", pady = 10, padx=10)
                pack_button.grid(row=i, column=2, sticky="w", pady = 10, padx=10)
            
        if selected_value == "EVENT":
            label = ctk.CTkLabel(self.payload_config_frame, text="Trigger event:")
            event = MyComboBox(self.payload_config_frame, values=[e.name for e in EVENT_TYPES])
            pack_button = ctk.CTkButton(self.payload_config_frame, text="Pack", command= lambda v=event: self.pack_payload_value(self.packet_type, None, v.get()))
            label.grid(row= 0, column=0, sticky="w", pady = 10, padx=10)
            event.grid(row = 0, column=1, sticky="w", pady = 10, padx=10)
            pack_button.grid(row=0, column=2, sticky="w", pady = 10, padx=10)


    def launch_packet(self):
        self.packet.dest_address = self.dest_node.address
        self.packet.src_address = self.src_node.address

        self.packet.timestamp = 69
        staged_packet = self.packet.encode()
        print(self.packet)
        
        # self.radio.tx(staged_packet, ADDRESS, 5, 0.01)
        
        
    def get_bytes(self, bytes) -> str:
        return(" ".join(f"{byte:02x}" for byte in bytes))
        
