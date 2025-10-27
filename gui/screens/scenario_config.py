"""
Dynamic scenario configuration screen
"""
import tkinter as tk
from gui.theme import DarkTheme
from gui.widgets import ThemedLabel, ThemedButton, ThemedEntry, ThemedFrame, Card, ScrollableFrame, Footer


class ScenarioConfigScreen(tk.Frame):
    """Screen for configuring scenario parameters"""

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Header
        header = ThemedFrame(self)
        header.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=(DarkTheme.PADDING_XLARGE, DarkTheme.PADDING_LARGE))

        self.title_label = ThemedLabel(header, text="Configure Scenario", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold'))
        self.title_label.pack(anchor='w')

        self.subtitle_label = ThemedLabel(header, text="Set parameters for your scenario", fg=DarkTheme.FG_SECONDARY)
        self.subtitle_label.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Scrollable configuration container
        scroll_container = ScrollableFrame(self)
        scroll_container.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_MEDIUM)

        self.config_container = scroll_container.scrollable_frame

        # Footer with navigation buttons
        footer = ThemedFrame(self)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        back_button = ThemedButton(footer, text="Back", command=self.on_back, primary=False)
        back_button.pack(side='left')

        self.generate_button = ThemedButton(footer, text="Generate", command=self.on_generate, primary=True)
        self.generate_button.pack(side='right')

        # Copyright footer
        copyright_footer = Footer(self)
        copyright_footer.pack(side='bottom', fill='x')

        # Store input widgets
        self.inputs = {}

    def load_config_for_scenario(self, scenario_type):
        """Load configuration form based on scenario type"""
        # Clear existing inputs
        for widget in self.config_container.winfo_children():
            widget.destroy()
        self.inputs.clear()

        # Common for all scenarios with departures
        if scenario_type in ['ground_departures', 'ground_mixed', 'tower_mixed', 'tracon_departures', 'tracon_mixed']:
            self._add_departures_config()

        # Arrivals configuration
        if scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_arrivals', 'tracon_mixed']:
            self._add_arrivals_config()

        # Active runways
        if scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_departures']:
            self._add_runway_config()

        # Separation range for tower
        if scenario_type == 'tower_mixed':
            self._add_separation_config()

        # TRACON arrivals specific
        if scenario_type in ['tracon_arrivals', 'tracon_mixed']:
            self._add_tracon_arrivals_config()

        # Output filename
        self._add_output_config()

    def _add_departures_config(self):
        """Add departure aircraft configuration"""
        card = Card(self.config_container, title="Departure Aircraft")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Number of Departure Aircraft:")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="e.g., 10")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['num_departures'] = entry

    def _add_arrivals_config(self):
        """Add arrival aircraft configuration"""
        card = Card(self.config_container, title="Arrival Aircraft")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Number of Arrival Aircraft:")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="e.g., 5")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['num_arrivals'] = entry

    def _add_runway_config(self):
        """Add runway configuration"""
        card = Card(self.config_container, title="Active Runways")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Active Runway(s) (comma separated):")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc = ThemedLabel(card, text="Example: 7L, 25R", fg=DarkTheme.FG_DISABLED)
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="e.g., 7L, 25R")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['active_runways'] = entry

    def _add_separation_config(self):
        """Add separation configuration for tower scenarios"""
        card = Card(self.config_container, title="Separation Interval")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Separation interval (min-max in NM):")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc = ThemedLabel(card, text="Example: 3-6 (default)", fg=DarkTheme.FG_DISABLED)
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="3-6")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['separation_range'] = entry

    def _add_tracon_arrivals_config(self):
        """Add TRACON arrivals specific configuration"""
        card = Card(self.config_container, title="TRACON Arrivals Configuration")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Waypoints
        label = ThemedLabel(card, text="Arrival Waypoints (comma separated):")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc = ThemedLabel(card, text="Example: EAGUL, CHILY", fg=DarkTheme.FG_DISABLED)
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        waypoints_entry = ThemedEntry(card, placeholder="e.g., EAGUL, CHILY")
        waypoints_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))
        self.inputs['arrival_waypoints'] = waypoints_entry

        # Altitude range
        label2 = ThemedLabel(card, text="Arrival Altitude Min-Max (feet):")
        label2.configure(bg=DarkTheme.BG_SECONDARY)
        label2.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc2 = ThemedLabel(card, text="Example: 7000-18000 (default)", fg=DarkTheme.FG_DISABLED)
        desc2.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc2.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        altitude_entry = ThemedEntry(card, placeholder="7000-18000")
        altitude_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))
        self.inputs['altitude_range'] = altitude_entry

        # Delay range
        label3 = ThemedLabel(card, text="Spawn Delay Min-Max (minutes):")
        label3.configure(bg=DarkTheme.BG_SECONDARY)
        label3.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc3 = ThemedLabel(card, text="Example: 4-7 (default)", fg=DarkTheme.FG_DISABLED)
        desc3.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc3.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        delay_entry = ThemedEntry(card, placeholder="4-7")
        delay_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['delay_range'] = delay_entry

    def _add_output_config(self):
        """Add output filename configuration"""
        card = Card(self.config_container, title="Output File")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Output Filename:")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc = ThemedLabel(card, text="Leave blank for default name", fg=DarkTheme.FG_DISABLED)
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="scenario.air")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['output_filename'] = entry

    def get_config_values(self):
        """Get all configuration values from inputs"""
        values = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, ThemedEntry):
                values[key] = widget.get_value()
        return values

    def on_back(self):
        """Handle back button click"""
        self.app_controller.show_screen('scenario_type')

    def on_generate(self):
        """Handle generate button click"""
        config = self.get_config_values()
        self.app_controller.generate_scenario(config)
