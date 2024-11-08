import customtkinter as ctk
from driver.nrf905 import NRF905
from gui.custom.pp_combobox import MyComboBox

class ConfigRadio(ctk.CTkFrame):
    def __init__(self, parent, controller, radio:NRF905):
        super().__init__(parent)
        self.controller = controller
        self.parent = parent
        self.pack(fill="both", expand=True)

        self.fields = {}
        self.widgets = {}
        self.radio = radio
        self.setup_gui()
        self.create_input_fields()
        
        
    def setup_gui(self):

        label = ctk.CTkLabel(self, text="Configure Radio")
        label.pack(pady=(20, 20), padx=10)

        self.button_frame = ctk.CTkFrame(self, width=600, height = 50)
        self.button_frame.pack(side="bottom")

        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack()
        
        self.create_buttons()

        
    
                
    def create_label(self, frame, specs, row, column, sticky='w'):
        label = ctk.CTkLabel(frame, pady=10, padx=10, text=specs['label'])
        label.grid(sticky=sticky, row=row, column=column)
        return label

    def create_widget(self, frame, field_name, specs):
        if specs['widget'] == 'ctkEntry':
            widget = ctk.CTkEntry(frame, width=200)
            widget.insert(0, str(specs['default']))
        elif specs['widget'] == 'ctkComboBox':
            widget = MyComboBox(frame, width=200, values=specs['values'])
            widget.set(specs['default'])
        elif specs['widget'] == 'ctkCheckBox':
            widget = ctk.CTkCheckBox(frame, text='', width=200)
            widget.select() if specs['default'] else widget.deselect()
        return widget

    def get_frame_and_positions(self, field_name, i):
            return self.input_frame, (i + 1, 0, 1)

    def create_buttons(self):
        self.launch_button = ctk.CTkButton(
            self.button_frame,
            text="Save",
            width=100,
            
            command=self.send_config
        )
        self.launch_button.pack(side="left", pady=10, padx=(10, 5))

        self.back_button = ctk.CTkButton(
            self.button_frame,
            text="Cancel",
            width=100,
            
            command=lambda: self.parent.show_frame("MainMenu"),
        )
        self.back_button.pack(side="left", pady=10, padx=(10, 5))
                
        
    def send_config(self):
        values = {}
        for field_name, widget in self.widgets.items():
            if isinstance(widget, MyComboBox):
                input_val = widget.get()
                index = self.fields[field_name]['values'].index(input_val)
                data = self.fields[field_name]['data_values'][index]
                values[field_name] = data
            elif isinstance(widget, ctk.CTkEntry):
                # only rx_address is entered as hex
                if field_name == 'RX_ADDRESS':
                    input_val = int(widget.get(), 16)
                else:
                    input_val = int(widget.get())
                values[field_name] = input_val
            else:
                values[field_name] = widget.get()

        values['CH_NO_MSB'] = (values['CH_NO'] >> 8) & 0x1     
        values['CH_NO'] = values['CH_NO'] & 0xFF
        
        self.radio.write_config(values)
        print("Wrote: ", self.radio.read_config_human())
        print("Raw read after writing: ", self.radio.read_config_binary(10))
        

        self.parent.show_frame("MainMenu")

    def create_input_fields(self):
        self.fields = {
                'AUTO_RETRAN': {
                    'label': 'Auto Retransmit', 
                    'widget': 'ctkCheckBox', 
                    'default': False,
                    'data_values' : [0, 1]
                    },
                'RX_RED_PWR': {
                    'label' : 'Rx Power', 
                    'widget' : 'ctkComboBox', 
                    'values': ['Normal Operation', 'Reduced Power'], 
                    'default' :'Normal Operation',
                    'data_values' : [0, 1]
                    },
                'PA_PWR': {
                    'label' : 'Output Power',
                    'widget' : 'ctkComboBox', 
                    'values': ['-10dBm', '-2dBm', '+6dBm', '+10dBm'], 
                    'default' : '+10dBm',
                    'data_values' : [0,1,2,3]
                    },
                'HFREQ_PLL': {
                    'label' : 'Frequency Band', 
                    'widget' : 'ctkComboBox', 
                    'values' : ['433MHz', '868/915MHz'], 
                    'default' : '433MHz',
                    'data_values' : [0,1]
                    },
                'CH_NO':{
                    'label': 'Channel No. [0-255]', 
                    'widget': 'ctkEntry',
                    'default': '108',
                    'data_values' : list(range(0,256))
                    },
                'TX_AFW': {
                    'label':'Tx Address Width', 
                    'widget':'ctkComboBox', 
                    'values':['1 byte', '2 bytes', '3 bytes', '4 bytes'], 
                    'default' : '4 bytes',
                    'data_values' : [1,2,3,4]
                    },
                'RX_AFW': {
                    'label':'Rx Address Width', 
                    'widget':'ctkComboBox', 
                    'values':['1 byte', '2 bytes', '3 bytes', '4 bytes'],  
                    'default' : '4 bytes',
                    'data_values' : [1,2,3,4]
                    },
                'TX_PW':{
                    'label':'Tx Payload Width [1-32 bytes]', 
                    'widget': 'ctkEntry', 
                    'default' : '32',
                    'data_values' : list(range(1, 32))
                    },
                'RX_PW':{
                    'label':'Rx Address Width [1-32 bytes]', 
                    'widget': 'ctkEntry', 
                    'default' : '32',
                    'data_values' : list(range(1, 32))
                    },
                'RX_ADDRESS' : {
                    'label': 'Local Address [hex]', 
                    'widget' : 'ctkEntry',
                    'default' : 'DEADBEEF'
                    },
                'CRC_MODE': {
                    'label': 'CRC Mode', 
                    'widget':'ctkComboBox', 
                    'values':['8-bit', '16-bit'], 
                    'default' : '16-bit',
                    'data_values' : [0,1]
                    },
                'CRC_EN': {
                    'label' : 'CRC Enabled', 
                    'widget' : 'ctkCheckBox', 
                    'default' : True,
                    'data_values' : [0,1]
                    },
                'XOF': {
                    'label' : 'Crystal Oscilator Freq', 
                    'widget' : 'ctkComboBox', 
                    'values' : ['4MHz','8MHz','12MHz','16MHz','20MHz'], 
                    'default' : '16MHz',
                    'data_values' : [0,1,2,3,4]
                    },
                'UP_CLK_EN': {
                    'label' : 'Enable Output Clock', 
                    'widget' : 'ctkCheckBox', 
                    'default' : False,
                    'data_values' : [0,1]
                    },
                'UP_CLK_FREQ': {
                    'label' : 'Output Clock Freq', 
                    'widget':'ctkComboBox', 
                    'values':['4MHz', '2MHz', '1MHz', '500kHz'], 
                    'default' : '4MHz',
                    'data_values' : [0,1,2,3]
                    }
                }
        
        for i, (field_name, specs) in enumerate(self.fields.items()):
            frame, (label_row, label_col, widget_col) = self.get_frame_and_positions(field_name, i)
            self.create_label(frame, specs, label_row, label_col)
            widget = self.create_widget(frame, field_name, specs)
            widget.grid(sticky='e', row=label_row, column=widget_col)
        
            self.widgets[field_name] = widget