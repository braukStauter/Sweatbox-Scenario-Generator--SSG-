"""
Scenario type selection screen
"""
import tkinter as tk
from gui.theme import DarkTheme
from gui.widgets import ThemedLabel, ThemedButton, SelectableCard, ThemedFrame, ScrollableFrame, Footer


class ScenarioTypeSelectionScreen(tk.Frame):
    """Screen for selecting scenario type"""

    SCENARIO_TYPES = {
        "ground_departures": {
            "title": "Ground (Departures)",
            "description": "Ground departure aircraft only at parking spots"
        },
        "ground_mixed": {
            "title": "Ground (Departures/Arrivals)",
            "description": "Ground departures with arriving aircraft on final approach"
        },
        "tower_mixed": {
            "title": "Tower (Departures/Arrivals)",
            "description": "Tower position with mixed departures and arrivals"
        },
        "tracon_departures": {
            "title": "TRACON (Departures)",
            "description": "TRACON departure aircraft starting from the ground"
        },
        "tracon_arrivals": {
            "title": "TRACON (Arrivals)",
            "description": "TRACON arrival aircraft at designated waypoints"
        },
        "tracon_mixed": {
            "title": "TRACON (Departures/Arrivals)",
            "description": "TRACON position with mixed departures and arrivals"
        }
    }

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Header
        header = ThemedFrame(self)
        header.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=(DarkTheme.PADDING_XLARGE, DarkTheme.PADDING_LARGE))

        title = ThemedLabel(header, text="Select Scenario Type", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold'))
        title.pack(anchor='w')

        subtitle = ThemedLabel(header, text="Choose the type of scenario you want to generate", fg=DarkTheme.FG_SECONDARY)
        subtitle.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Scrollable scenario list container
        scroll_container = ScrollableFrame(self)
        scroll_container.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_MEDIUM)

        self.scenario_container = scroll_container.scrollable_frame

        # Footer with navigation buttons
        footer = ThemedFrame(self)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        back_button = ThemedButton(footer, text="Back", command=self.on_back, primary=False)
        back_button.pack(side='left')

        self.next_button = ThemedButton(footer, text="Next", command=self.on_next, primary=True)
        self.next_button.pack(side='right')
        self.next_button['state'] = 'disabled'

        # Copyright footer
        copyright_footer = Footer(self)
        copyright_footer.pack(side='bottom', fill='x')

        # Store selected scenario and cards
        self.selected_scenario = None
        self.scenario_cards = []

        # Load scenario types
        self.load_scenario_types()

    def load_scenario_types(self):
        """Load scenario type options"""
        for scenario_id, info in self.SCENARIO_TYPES.items():
            card = SelectableCard(
                self.scenario_container,
                title=info['title'],
                description=info['description']
            )

            # Set command with card reference
            card.set_command(lambda s=scenario_id, c=card: self.select_scenario(s, c))

            card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)
            self.scenario_cards.append((scenario_id, card))

    def select_scenario(self, scenario_id, card):
        """Handle scenario type selection"""
        # Deselect all cards
        for _, c in self.scenario_cards:
            c.deselect()

        # Select clicked card
        if card:
            card.select()

        self.selected_scenario = scenario_id
        self.next_button['state'] = 'normal'

    def on_back(self):
        """Handle back button click"""
        self.app_controller.show_screen('airport')

    def on_next(self):
        """Handle next button click"""
        if self.selected_scenario:
            self.app_controller.set_scenario_type(self.selected_scenario)
            self.app_controller.show_screen('scenario_config')
