"""
Airport selection screen
"""
import tkinter as tk
from tkinter import messagebox, filedialog
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

        title = ThemedLabel(header, text="Select Scenario Type", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold'))
        title.pack(anchor='w')

        subtitle = ThemedLabel(header, text="Choose an airport or create an enroute ARTCC scenario", fg=DarkTheme.FG_SECONDARY)
        subtitle.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Create outer container for the scrollable area
        outer_container = ThemedFrame(self)
        outer_container.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_MEDIUM)

        # Create canvas with no scrollbar
        self.canvas = tk.Canvas(
            outer_container,
            bg=DarkTheme.BG_PRIMARY,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(side='left', fill='both', expand=True)

        # Create the scrollable frame inside canvas
        self.airport_container = ThemedFrame(self.canvas)
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.airport_container, anchor='nw')

        # Update scroll region when frame changes
        def configure_scroll_region(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))

        self.airport_container.bind('<Configure>', configure_scroll_region)

        # Update canvas window width when canvas resizes
        def configure_canvas_width(event):
            self.canvas.itemconfig(self.canvas_frame, width=event.width)

        self.canvas.bind('<Configure>', configure_canvas_width)

        # Bind mousewheel events for scrolling
        def on_mouse_wheel(event):
            # Scroll the canvas
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        # Bind to the canvas and all child widgets
        def bind_to_mousewheel(widget):
            widget.bind('<MouseWheel>', on_mouse_wheel)
            for child in widget.winfo_children():
                bind_to_mousewheel(child)

        self.canvas.bind('<MouseWheel>', on_mouse_wheel)
        self.airport_container.bind('<MouseWheel>', on_mouse_wheel)

        # Store the binding function for later use
        self._bind_mousewheel = bind_to_mousewheel

        # Footer with navigation buttons
        footer = ThemedFrame(self)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        # Upload to vNAS button on the left
        self.upload_button = ThemedButton(footer, text="Backup File Upload", command=self.on_upload_scenario, primary=False)
        self.upload_button.pack(side='left')

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

        # Add airport header first
        airport_header = ThemedLabel(
            self.airport_container,
            text="Airport-Based Scenarios",
            fg=DarkTheme.FG_SECONDARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        airport_header.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

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

        # Create airport cards
        for geojson_file in geojson_files:
            # Format ICAO code: add "K" prefix only for 3-letter codes (US airports)
            # 4-letter codes already have their proper prefix (e.g., PHOG, PHNL, CYYZ)
            base_code = geojson_file.stem.upper()
            icao = base_code if len(base_code) == 4 else "K" + base_code

            card = SelectableCard(
                self.airport_container,
                title=icao,
                description=f"Airport data from {geojson_file.name}"
            )

            # Set command with card reference
            card.set_command(lambda a=icao, c=card: self.select_airport(a, c))

            card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)
            self.airport_cards.append(card)

            # Bind mousewheel to the card and its children
            self._bind_mousewheel(card)

        # If only one airport, auto-select it
        if len(geojson_files) == 1:
            base_code = geojson_files[0].stem.upper()
            icao = base_code if len(base_code) == 4 else "K" + base_code
            self.select_airport(icao, self.airport_cards[0])

        # Add divider between airports and enroute
        divider = tk.Frame(self.airport_container, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_LARGE)

        # Add Enroute Scenario option at the BOTTOM
        enroute_card = SelectableCard(
            self.airport_container,
            title="Enroute (ARTCC) Scenario",
            description="Create an enroute scenario."
        )
        enroute_card.set_command(lambda: self.select_enroute_scenario(enroute_card))
        enroute_card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)
        self.airport_cards.append(enroute_card)

        # Bind mousewheel to the enroute card
        self._bind_mousewheel(enroute_card)

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

    def select_enroute_scenario(self, card):
        """Handle enroute scenario selection"""
        # Show warning dialog
        warning_result = messagebox.showwarning(
            "Experimental Feature Warning",
            "WARNING: This is EXPERIMENTAL. Ongoing development is extensive, so support will not be offered (except bugs) until the next update. Expect longer load times (~30 seconds for complex scenarios).",
            type=messagebox.OKCANCEL
        )

        # If user cancels, don't select the card
        if warning_result == 'cancel':
            return

        # Deselect all cards
        for c in self.airport_cards:
            c.deselect()

        # Select enroute card
        if card:
            card.select()

        self.selected_airport = "ENROUTE"  # Special marker
        self.next_button['state'] = 'normal'

    def show_loading(self, message="Loading airport data..."):
        """Show loading overlay"""
        self.loading_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.loading_progress.start(message)
        self.next_button['state'] = 'disabled'

    def hide_loading(self):
        """Hide loading overlay"""
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.next_button['state'] = 'normal'

    def on_upload_scenario(self):
        """Handle upload scenario button click"""
        # Open file dialog to select JSON scenario file
        filepath = filedialog.askopenfilename(
            title="Select vNAS Scenario File",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ],
            initialdir="."
        )

        if filepath:
            # Upload the scenario file to vNAS
            self.app_controller.upload_scenario_to_vnas(filepath)

    def on_next(self):
        """Handle next button click"""
        if self.selected_airport:
            # Show loading indicator
            self.show_loading()
            # Load airport data in background thread
            self.app_controller.load_airport_data(self.selected_airport)
