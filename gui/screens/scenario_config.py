"""
Dynamic scenario configuration screen
"""
import tkinter as tk
from tkinter import messagebox
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

        # Difficulty levels configuration FIRST (all scenarios)
        self._add_difficulty_config()

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

        # Spawn delay configuration (all scenarios)
        self._add_spawn_delay_config()

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

        # Store reference to card for hiding/showing
        self.departure_card = card

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

        # Store reference to card for hiding/showing
        self.arrival_card = card

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

    def _add_spawn_delay_config(self):
        """Add spawn delay configuration"""
        card = Card(self.config_container, title="Spawn Timing")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        label = ThemedLabel(card, text="Spawn Delay Range (min-max in minutes):")
        label.configure(bg=DarkTheme.BG_SECONDARY)
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        desc = ThemedLabel(card, text="Aircraft will spawn at random intervals within this range. Use 0-0 for all aircraft to spawn at once (default)", fg=DarkTheme.FG_DISABLED)
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(card, placeholder="0-0")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['spawn_delay_range'] = entry

    def _add_difficulty_config(self):
        """Add difficulty level configuration"""
        card = Card(self.config_container, title="Aircraft Difficulty (Optional)")
        card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Checkbox to enable difficulty levels
        enable_var = tk.BooleanVar(value=False)
        enable_checkbox = tk.Checkbutton(
            card,
            text="Configure difficulty levels (if unchecked, specify total aircraft count below)",
            variable=enable_var,
            bg=DarkTheme.BG_SECONDARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_SECONDARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_difficulty_inputs(enable_var.get(), difficulty_frame)
        )
        enable_checkbox.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['enable_difficulty'] = enable_var

        # Description
        desc = ThemedLabel(
            card,
            text="When enabled, aircraft counts are determined by difficulty levels. For mixed scenarios, totals will be split evenly between departures and arrivals.",
            fg=DarkTheme.FG_DISABLED,
            wraplength=600,
            justify='left'
        )
        desc.configure(bg=DarkTheme.BG_SECONDARY, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Container for difficulty inputs (hidden by default)
        difficulty_frame = ThemedFrame(card)
        difficulty_frame.configure(bg=DarkTheme.BG_SECONDARY)
        difficulty_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        difficulty_frame.pack_forget()  # Hide initially

        # Easy difficulty
        easy_label = ThemedLabel(difficulty_frame, text="Easy Aircraft:")
        easy_label.configure(bg=DarkTheme.BG_SECONDARY)
        easy_label.grid(row=0, column=0, sticky='w', pady=DarkTheme.PADDING_SMALL)

        easy_entry = ThemedEntry(difficulty_frame, placeholder="0")
        easy_entry.grid(row=0, column=1, sticky='ew', padx=(DarkTheme.PADDING_MEDIUM, 0), pady=DarkTheme.PADDING_SMALL)
        self.inputs['difficulty_easy'] = easy_entry

        # Medium difficulty
        medium_label = ThemedLabel(difficulty_frame, text="Medium Aircraft:")
        medium_label.configure(bg=DarkTheme.BG_SECONDARY)
        medium_label.grid(row=1, column=0, sticky='w', pady=DarkTheme.PADDING_SMALL)

        medium_entry = ThemedEntry(difficulty_frame, placeholder="0")
        medium_entry.grid(row=1, column=1, sticky='ew', padx=(DarkTheme.PADDING_MEDIUM, 0), pady=DarkTheme.PADDING_SMALL)
        self.inputs['difficulty_medium'] = medium_entry

        # Hard difficulty
        hard_label = ThemedLabel(difficulty_frame, text="Hard Aircraft:")
        hard_label.configure(bg=DarkTheme.BG_SECONDARY)
        hard_label.grid(row=2, column=0, sticky='w', pady=DarkTheme.PADDING_SMALL)

        hard_entry = ThemedEntry(difficulty_frame, placeholder="0")
        hard_entry.grid(row=2, column=1, sticky='ew', padx=(DarkTheme.PADDING_MEDIUM, 0), pady=DarkTheme.PADDING_SMALL)
        self.inputs['difficulty_hard'] = hard_entry

        # Make column 1 expand
        difficulty_frame.columnconfigure(1, weight=1)

    def _toggle_difficulty_inputs(self, enabled, frame):
        """Show/hide difficulty input fields and aircraft count cards based on checkbox state"""
        if enabled:
            # Show difficulty inputs
            frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))

            # Hide manual aircraft count cards
            if hasattr(self, 'departure_card'):
                self.departure_card.pack_forget()
            if hasattr(self, 'arrival_card'):
                self.arrival_card.pack_forget()
        else:
            # Hide difficulty inputs
            frame.pack_forget()

            # Show manual aircraft count cards (restore them in order)
            if hasattr(self, 'departure_card'):
                self.departure_card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)
            if hasattr(self, 'arrival_card'):
                self.arrival_card.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

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
            elif isinstance(widget, tk.BooleanVar):
                values[key] = widget.get()
        return values

    def on_back(self):
        """Handle back button click"""
        self.app_controller.show_screen('scenario_type')

    def on_generate(self):
        """Handle generate button click"""
        config = self.get_config_values()

        # Validate required fields
        validation_errors = self._validate_config(config)
        if validation_errors:
            messagebox.showerror(
                "Configuration Error",
                "Please fix the following errors:\n\n" + "\n".join(f"• {error}" for error in validation_errors)
            )
            return

        self.app_controller.generate_scenario(config)

    def _validate_config(self, config):
        """
        Validate configuration values

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Get scenario type from app controller
        scenario_type = self.app_controller.scenario_type

        # Validate runways - ONLY required for scenarios with arrivals or runway-based departures
        # ground_departures uses parking spots only, so runways not required
        active_runways = config.get('active_runways', '').strip()
        if not active_runways and scenario_type != 'ground_departures':
            errors.append("Active runways are required")

        # Check if difficulty levels are enabled
        difficulty_enabled = config.get('enable_difficulty', False)

        if difficulty_enabled:
            # When difficulty is enabled, validate difficulty counts
            try:
                easy_count = int(config.get('difficulty_easy', '0') or '0')
                medium_count = int(config.get('difficulty_medium', '0') or '0')
                hard_count = int(config.get('difficulty_hard', '0') or '0')

                if easy_count < 0 or medium_count < 0 or hard_count < 0:
                    errors.append("Difficulty counts cannot be negative")

                total_aircraft = easy_count + medium_count + hard_count
                if total_aircraft == 0:
                    errors.append("Must specify at least one aircraft in difficulty levels")

                # Store calculated totals for later use
                num_dep = total_aircraft
                num_arr = 0  # Will be calculated based on scenario type
            except ValueError:
                errors.append("Difficulty counts must be valid numbers")
                num_dep = 0
                num_arr = 0
        else:
            # When difficulty is disabled, validate manual aircraft counts
            num_departures = config.get('num_departures', '')
            num_arrivals = config.get('num_arrivals', '')

            try:
                num_dep = int(num_departures) if num_departures else 0
                num_arr = int(num_arrivals) if num_arrivals else 0

                if num_dep < 0:
                    errors.append("Number of departures cannot be negative")
                if num_arr < 0:
                    errors.append("Number of arrivals cannot be negative")
                if num_dep == 0 and num_arr == 0:
                    errors.append("Must generate at least one departure or arrival")
            except ValueError:
                errors.append("Number of departures and arrivals must be valid numbers")
                num_dep = 0
                num_arr = 0

        # Validate ranges (if provided)
        if config.get('separation_range'):
            try:
                parts = config['separation_range'].split('-')
                if len(parts) != 2:
                    errors.append("Separation range must be in format: min-max (e.g., 3-6)")
                else:
                    min_sep, max_sep = int(parts[0]), int(parts[1])
                    if min_sep < 0 or max_sep < 0:
                        errors.append("Separation values cannot be negative")
                    if min_sep > max_sep:
                        errors.append("Minimum separation cannot be greater than maximum")
            except ValueError:
                errors.append("Separation range must contain valid numbers")

        if config.get('altitude_range'):
            try:
                parts = config['altitude_range'].split('-')
                if len(parts) != 2:
                    errors.append("Altitude range must be in format: min-max (e.g., 7000-18000)")
                else:
                    min_alt, max_alt = int(parts[0]), int(parts[1])
                    if min_alt < 0 or max_alt < 0:
                        errors.append("Altitude values cannot be negative")
                    if min_alt > max_alt:
                        errors.append("Minimum altitude cannot be greater than maximum")
            except ValueError:
                errors.append("Altitude range must contain valid numbers")

        if config.get('delay_range'):
            try:
                parts = config['delay_range'].split('-')
                if len(parts) != 2:
                    errors.append("Delay range must be in format: min-max (e.g., 4-7)")
                else:
                    min_delay, max_delay = int(parts[0]), int(parts[1])
                    if min_delay < 0 or max_delay < 0:
                        errors.append("Delay values cannot be negative")
                    if min_delay > max_delay:
                        errors.append("Minimum delay cannot be greater than maximum")
            except ValueError:
                errors.append("Delay range must contain valid numbers")

        if config.get('spawn_delay_range'):
            try:
                parts = config['spawn_delay_range'].split('-')
                if len(parts) != 2:
                    errors.append("Spawn delay range must be in format: min-max (e.g., 0-0 or 1-5)")
                else:
                    min_spawn, max_spawn = int(parts[0]), int(parts[1])
                    if min_spawn < 0 or max_spawn < 0:
                        errors.append("Spawn delay values cannot be negative")
                    if min_spawn > max_spawn:
                        errors.append("Minimum spawn delay cannot be greater than maximum")
            except ValueError:
                errors.append("Spawn delay range must contain valid numbers")

        return errors
