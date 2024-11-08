import customtkinter as ctk
from driver.nrf905 import NRF905
from decoder import decode_packet
import threading
from pp_table import CTkTable
from gui.custom.pp_combobox import MyComboBox
from payload_display import PayloadDisplay

class SniffSettings(ctk.CTkFrame):
    def __init__(self, parent, controller, radio: NRF905):
        super().__init__(parent)
        self.controller = controller
        self.parent = parent
        self.radio = radio

        label = ctk.CTkLabel(self, text = "Sniffer", font=("CascadiaCode", 30))
        label.pack(pady=(30,30), padx=10)
        self.row_count = 0
        self.packet_database = []
        self.sniffing = False

        self.draw_buttons()
        self.draw_input()

    def draw_input(self):
        self.rx_value = ctk.StringVar(value='4')
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(side='top',pady=10, padx=10)

        rx_afw_label = ctk.CTkLabel(input_frame, text="Rx Match Width", pady=10, padx=10)
        rx_afw_combo = MyComboBox(
            input_frame,
            values=['1', '2', '3', '4'],
                        variable=self.rx_value,
            command=lambda value: self.change_config_value('RX_AFW', value)
        )
        

        rx_afw_label.grid(sticky='w', row=0, column=0)
        rx_afw_combo.grid(sticky='w', row=0, column=1, padx=10, pady=10)
        
        crc_value = ctk.IntVar(value=1)
        crc_enable = ctk.CTkCheckBox(input_frame, 
                                     text="CRC Enable",
                                     variable=crc_value,
                                     command=lambda value=crc_value: self.change_config_value('CRC_EN', value.get()))
        crc_enable.grid(row=0, column=2, padx=10, pady=10)

        # to lock the top row, perhaps use 2x tables? Not too sure

        self.header_frame = ctk.CTkFrame(self, width=600, height=25)
        self.header_frame.pack(side='top')

        self.header_row = CTkTable(self.header_frame, width=380, height=25, pady = 10, padx=1, row=1, column=7,
                                  values=[["id","src","dst","ctx","type","time","len"]])
        self.header_row.pack(side='left')

        self.data_table_frame= ctk.CTkScrollableFrame(self, width=600, height=500)
        self.data_table_frame.bind_all("<Button-4>", lambda e: self.data_table_frame._parent_canvas.yview("scroll", -1, "units"))
        self.data_table_frame.bind_all("<Button-5>", lambda e: self.data_table_frame._parent_canvas.yview("scroll", 1, "units"))
        self.data_table_frame.pack(side='top')

    def init_sniff_table(self, packet):
        self.data_rows = CTkTable(self.data_table_frame, width=380, height=25, pady = 2, padx=1, row=1, column=7,
                                 colors=["#4e4037", "#212121"], row_select_cb=self.inform_to_open)
        self.data_rows.delete_row(index=0)
        self.data_rows.add_row(row=0, index=0, values = [
                                    str(self.row_count),
                                    packet["source_address"],
                                    packet["destination_address"],
                                    packet["context_address"],
                                    packet["payload_type"],
                                    packet["timestamp"],
                                    packet["total_len"]
                                    ])
        self.data_rows.pack(side='top')

    def inform_to_open(self, row):
        self.popup_window = ctk.CTkToplevel(self)
        self.popup_window.geometry(self.controller.CenterWindowToDisplay(400, 500))
        self.popup_window.transient(self)
        self.popup_window.wait_visibility()
        self.popup_window.grab_set()
        self.popup_window.focus_set()
        PayloadDisplay(controller=self, parent=self.popup_window, packet=self.packet_database[row])


    # Get the config dict used to configure the radio elsewhere, and just update the single value we need for this window
    def change_config_value(self, config_key, new_value):
        config_dict_to_edit = self.radio.read_config_human()
        config_dict_to_edit[config_key] = int(new_value)
        self.configure_radio(config_dict_to_edit)

    def configure_radio(self, updated_config):
        self.radio.write_config(updated_config)
        print("Sniff config: ", self.radio.read_config_human())
        print("Sniff Raw Config read: ", self.radio.read_config_binary(10))


    def draw_buttons(self):
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(side='bottom', pady=10, padx=10)

        self.sniff_button = ctk.CTkButton(self.button_frame, text="Start",  command=self.toggle_sniff, hover=False)
        self.sniff_button.pack(side='left', pady=10, padx=10)
        
        self.clear_button = ctk.CTkButton(self.button_frame, text="Clear",  command=self.clear_table)
        self.clear_button.pack(side='left',pady=10, padx=10 )

        self.cancel_button = ctk.CTkButton(self.button_frame, text="Cancel",  command=lambda: self.parent.show_frame("MainMenu"))
        self.cancel_button.pack(side='left',pady=10, padx=10 )


    def clear_table(self):
        self.data_rows.delete_rows(list(range(self.data_rows.rows)))
        # my counter to allow me check before initing the first row
        self.row_count=0
        self.data_rows.pack_forget()
        self.packet_database = []

    def toggle_sniff(self):
        if not self.sniffing:
            if self.radio.radio_configured == False:
                print("Please configure the radio via the radio config menu!")
                return
            self.sniffing = True
            self.sniff_button.configure(text="Stop", require_redraw=True, fg_color="#90462c")
            self.sniff_thread = threading.Thread(target=self.sniff_loop)
            self.sniff_thread.start()
        else:
            self.sniffing = False
            self.sniff_button.configure(text="Start", require_redraw=True, fg_color="#ec7a1c")
            self.stop_sniffing()


    def sniff_loop(self):
        while self.sniffing:
            RX_OK, response = self.radio.rx()
            if RX_OK:
                packet = decode_packet(response)
                if packet is not None:
                    self.packet_database.append(packet)
                    if self.row_count == 0:
                        self.init_sniff_table(packet)
                    else:
                        self.add_row(packet)
                    self.row_count += 1
            if not self.sniffing:
                break
        print("stopped")

    def stop_sniffing(self):
        if self.sniff_thread.is_alive():
            self.sniff_thread.join()

    def add_row(self, packet):
        self.data_rows.add_row(values = [
            str(self.row_count),
            packet["source_address"],
            packet["destination_address"],
            packet["context_address"],
            packet["payload_type"],
            packet["timestamp"],
            packet["total_len"]
        ])
