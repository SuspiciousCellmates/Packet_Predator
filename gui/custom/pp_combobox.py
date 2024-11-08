import customtkinter as ctk

class MyComboBox(ctk.CTkComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_custom_bindings()

    def _create_custom_bindings(self):
        """Bind click events to the entire widget, ensuring dropdown opens no matter where clicked."""
        # Bind click event for the entire combobox to ensure the dropdown opens
        self.bind("<Button-1>", self._clicked)

        # Bind specific internal parts to trigger the dropdown on click
        self._canvas.tag_bind("inner_parts", "<Button-1>", self._clicked)
        self._canvas.tag_bind("right_parts", "<Button-1>", self._clicked)
        self._canvas.tag_bind("dropdown_arrow", "<Button-1>", self._clicked)

        # Explicitly handle the Entry widget (internal text field)
        if hasattr(self, 'entry'):
            # Prevent text selection and focus artifacts
            self.entry.bind("<Button-1>", self._prevent_selection)
            self.entry.bind("<FocusIn>", self._prevent_focus)

        # Handle dropdown close event to reset any internal states
        self.bind("<FocusOut>", self._on_focus_out)

    def _prevent_selection(self, event):
        """Prevent text from being selected/highlighted when clicked."""
        # Intercept click and prevent default selection
        self.entry.selection_clear()  # Clear any selection
        return "break"  # Stop further processing

    def _prevent_focus(self, event):
        """Prevent focus-related artifacts like text highlighting."""
        self.entry.selection_clear()  # Clear any selection when gaining focus
        return "break"  # Stop the default focus behavior

    def _on_focus_out(self, event):
        """Handle focus out event to ensure proper state reset."""
        # Reset any custom state or behavior when the combobox loses focus
        if hasattr(self, 'entry'):
            self.entry.selection_clear()  # Clear text selection when focus is lost
        return "break"
        
    def inspect_canvas_tags(self):
        # Check if _canvas exists (it should after initialization)
        if hasattr(self, '_canvas'):
            # Get all items on the canvas
            canvas_items = self._canvas.find_all()

            # Loop through all items and print their associated tags
            for item in canvas_items:
                tags = self._canvas.gettags(item)
                print(f"Item ID: {item}, Tags: {tags}")
        else:
            print("No canvas found in this widget.")