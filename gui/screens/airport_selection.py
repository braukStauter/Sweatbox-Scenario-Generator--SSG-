"""
Airport selection screen
"""
import tkinter as tk
from pathlib import Path
from gui.theme import DarkTheme
from gui.widgets import ThemedLabel, ThemedButton, SelectableCard, ThemedFrame, Footer, ProgressIndicator


class AirportSelectionScreen(tk.Frame):
    """Screen for selecting an airport"""

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Header
        header = ThemedFrame(self)
        header.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=(DarkTheme.PADDING_XLARGE, DarkTheme.PADDING_LARGE))

        title = ThemedLabel(header, text="Select Primary Airport", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold'))
        title.pack(anchor='w')

        subtitle = ThemedLabel(header, text="Choose the airport for your scenario", fg=DarkTheme.FG_SECONDARY)
        subtitle.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Airport list container
        self.airport_container = ThemedFrame(self)
        self.airport_container.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_MEDIUM)

        # Footer with navigation buttons
        footer = ThemedFrame(self)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        self.next_button = ThemedButton(footer, text="Next", command=self.on_next, primary=True)
        self.next_button.pack(side='right')
        self.next_button['state'] = 'disabled'

        # Copyright footer
        copyright_footer = Footer(self)
        copyright_footer.pack(side='bottom', fill='x')

        # Loading overlay (hidden by default)
        self.loading_overlay = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)

        # Center the progress indicator
        center_frame = ThemedFrame(self.loading_overlay)
        center_frame.place(relx=0.5, rely=0.5, anchor='center')

        self.loading_progress = ProgressIndicator(center_frame)
        self.loading_progress.pack()

        # Store selected airport and cards
        self.selected_airport = None
        self.airport_cards = []

        # Load airports
        self.load_airports()

    def load_airports(self):
        """Load available airports from airport_data directory"""
        airport_data_dir = Path("airport_data")

        if not airport_data_dir.exists():
            error_label = ThemedLabel(
                self.airport_container,
                text="Error: No airport_data directory found!",
                fg=DarkTheme.ERROR
            )
            error_label.pack(pady=DarkTheme.PADDING_LARGE)
            return

        # Find all GeoJSON files
        geojson_files = list(airport_data_dir.glob("*.geojson"))

        if not geojson_files:
            error_label = ThemedLabel(
                self.airport_container,
                text="Error: No airport GeoJSON files found!",
                fg=DarkTheme.ERROR
            )
            error_label.pack(pady=DarkTheme.PADDING_LARGE)
            return

        # Create grid for airport cards
        for i, geojson_file in enumerate(geojson_files):
            icao = "K" + geojson_file.stem.upper()
            card = SelectableCard(
                self.airport_container,
                title=icao,
                description=f"Airport data from {geojson_file.name}"
            )

            # Set command with card reference
            card.set_command(lambda a=icao, c=card: self.select_airport(a, c))

            card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)
            self.airport_cards.append(card)

        # If only one airport, auto-select it
        if len(geojson_files) == 1:
            self.select_airport("K" + geojson_files[0].stem.upper(), self.airport_cards[0])

    def select_airport(self, icao, card):
        """Handle airport selection"""
        # Deselect all cards
        for c in self.airport_cards:
            c.deselect()

        # Select clicked card
        if card:
            card.select()

        self.selected_airport = icao
        self.next_button['state'] = 'normal'

    def show_loading(self):
        """Show loading overlay"""
        self.loading_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.loading_progress.start("Loading airport data...")
        self.next_button['state'] = 'disabled'

    def hide_loading(self):
        """Hide loading overlay"""
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.next_button['state'] = 'normal'

    def on_next(self):
        """Handle next button click"""
        if self.selected_airport:
            # Show loading indicator
            self.show_loading()
            # Load airport data in background thread
            self.app_controller.load_airport_data(self.selected_airport)
