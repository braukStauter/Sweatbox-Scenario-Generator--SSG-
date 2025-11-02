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

        # Store scenario type flags for later use
        has_departures = scenario_type in ['ground_departures', 'ground_mixed', 'tower_mixed', 'tracon_departures', 'tracon_mixed']
        has_arrivals = scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_arrivals', 'tracon_mixed']
        has_runways = scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_departures', 'tracon_arrivals', 'tracon_mixed']
        is_tower = scenario_type == 'tower_mixed'
        is_tracon_arrivals = scenario_type in ['tracon_arrivals', 'tracon_mixed']

        # Difficulty levels configuration FIRST (collapsible)
        self._add_difficulty_config()
        self._add_divider()

        # Aircraft counts section - compact grid layout
        if has_departures or has_arrivals:
            self._add_aircraft_counts_section(has_departures, has_arrivals)
            self._add_divider()

        # Runway and separation config - compact inline
        if has_runways or is_tower:
            self._add_runway_and_separation_section(has_runways, is_tower)
            self._add_divider()

        # TRACON arrivals specific - compact
        if is_tracon_arrivals:
            self._add_tracon_arrivals_config()
            self._add_divider()

        # Spawn delay and output - compact inline
        self._add_spawn_and_output_section()

    def _add_divider(self):
        """Add a subtle divider line between sections"""
        divider = tk.Frame(self.config_container, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

    def _add_aircraft_counts_section(self, has_departures, has_arrivals):
        """Add aircraft counts in a compact grid layout"""
        section = ThemedFrame(self.config_container)
        section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Section title
        title = ThemedLabel(section, text="Aircraft Count", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'))
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Grid container for inputs
        grid_frame = ThemedFrame(section)
        grid_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        col = 0
        if has_departures:
            dep_label = ThemedLabel(grid_frame, text="Departures:")
            dep_label.grid(row=0, column=col, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

            dep_entry = ThemedEntry(grid_frame, placeholder="e.g., 10")
            dep_entry.grid(row=0, column=col+1, sticky='ew', padx=(0, DarkTheme.PADDING_LARGE))
            self.inputs['num_departures'] = dep_entry
            self.departure_entry_frame = dep_entry
            col += 2

        if has_arrivals:
            arr_label = ThemedLabel(grid_frame, text="Arrivals:")
            arr_label.grid(row=0, column=col, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

            arr_entry = ThemedEntry(grid_frame, placeholder="e.g., 5")
            arr_entry.grid(row=0, column=col+1, sticky='ew', padx=(0, DarkTheme.PADDING_LARGE))
            self.inputs['num_arrivals'] = arr_entry
            self.arrival_entry_frame = arr_entry

        # Make entry columns expand
        grid_frame.columnconfigure(1, weight=1)
        if has_departures and has_arrivals:
            grid_frame.columnconfigure(3, weight=1)

        # Store references for hiding/showing
        self.aircraft_counts_section = section

        # Store the pack info immediately after packing for the first time
        # This ensures we can restore it to this exact position later
        self.config_container.update_idletasks()  # Force layout to complete
        self._aircraft_counts_pack_info = section.pack_info()

    def _add_runway_and_separation_section(self, has_runways, is_tower):
        """Add runway and separation config in compact inline layout"""
        section = ThemedFrame(self.config_container)
        section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Section title
        title = ThemedLabel(section, text="Runway Configuration", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'))
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Grid container
        grid_frame = ThemedFrame(section)
        grid_frame.pack(fill='x')

        row = 0
        if has_runways:
            # Runways label and input
            runway_label = ThemedLabel(grid_frame, text="Active Runways:")
            runway_label.grid(row=row, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

            runway_entry = ThemedEntry(grid_frame, placeholder="e.g., 7L, 25R")
            runway_entry.grid(row=row, column=1, sticky='ew', pady=(0, DarkTheme.PADDING_SMALL))
            self.inputs['active_runways'] = runway_entry

            runway_hint = ThemedLabel(grid_frame, text="(comma separated)", fg=DarkTheme.FG_DISABLED, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
            runway_hint.grid(row=row, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))
            row += 1

        if is_tower:
            # Separation label and input
            sep_label = ThemedLabel(grid_frame, text="Separation (NM):")
            sep_label.grid(row=row, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

            sep_entry = ThemedEntry(grid_frame, placeholder="3-6")
            sep_entry.grid(row=row, column=1, sticky='ew', pady=(0, DarkTheme.PADDING_SMALL))
            self.inputs['separation_range'] = sep_entry

            sep_hint = ThemedLabel(grid_frame, text="(min-max)", fg=DarkTheme.FG_DISABLED, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
            sep_hint.grid(row=row, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        # Make entry column expand
        grid_frame.columnconfigure(1, weight=1)

    def _add_tracon_arrivals_config(self):
        """Add TRACON arrivals specific configuration (compact)"""
        section = ThemedFrame(self.config_container)
        section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Section title
        title = ThemedLabel(section, text="TRACON Arrivals", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'))
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Grid container
        grid_frame = ThemedFrame(section)
        grid_frame.pack(fill='x')

        # STAR Waypoints
        waypoint_label = ThemedLabel(grid_frame, text="STAR Waypoints:")
        waypoint_label.grid(row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        waypoints_entry = ThemedEntry(grid_frame, placeholder="e.g., EAGUL.JESSE3, PINNG.PINNG1")
        waypoints_entry.grid(row=0, column=1, sticky='ew', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['arrival_waypoints'] = waypoints_entry

        waypoint_hint = ThemedLabel(grid_frame, text="(WAYPOINT.STAR, spawn 10NM out)", fg=DarkTheme.FG_DISABLED, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        waypoint_hint.grid(row=0, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        # Altitude range
        alt_label = ThemedLabel(grid_frame, text="Altitude Range (ft):")
        alt_label.grid(row=1, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        altitude_entry = ThemedEntry(grid_frame, placeholder="7000-18000")
        altitude_entry.grid(row=1, column=1, sticky='ew', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['altitude_range'] = altitude_entry

        alt_hint = ThemedLabel(grid_frame, text="(fallback when CIFP lacks constraints)", fg=DarkTheme.FG_DISABLED, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        alt_hint.grid(row=1, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        # Make entry column expand
        grid_frame.columnconfigure(1, weight=1)

    def _add_spawn_and_output_section(self):
        """Add spawn delay configuration and output filename"""
        section = ThemedFrame(self.config_container)
        section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Section title
        title = ThemedLabel(section, text="Timing & Output", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'))
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Spawn delay checkbox
        spawn_header_frame = ThemedFrame(section)
        spawn_header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_spawn_var = tk.BooleanVar(value=False)

        enable_spawn_checkbox = tk.Checkbutton(
            spawn_header_frame,
            text="Enable spawn time delays",
            variable=enable_spawn_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_spawn_delay_inputs(enable_spawn_var.get())
        )
        enable_spawn_checkbox.pack(side='left')
        self.inputs['enable_spawn_delays'] = enable_spawn_var

        # Hint text
        spawn_checkbox_hint = ThemedLabel(
            spawn_header_frame,
            text="(all aircraft spawn at once if unchecked)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        spawn_checkbox_hint.pack(side='left', padx=(DarkTheme.PADDING_SMALL, 0))

        # Container for spawn delay options (hidden by default)
        self.spawn_delay_frame = ThemedFrame(section)
        self.spawn_delay_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL))
        self.spawn_delay_frame.pack_forget()  # Hide initially

        # Radio buttons for spawn delay mode
        mode_frame = ThemedFrame(self.spawn_delay_frame)
        mode_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        spawn_mode_label = ThemedLabel(mode_frame, text="Spawn delay mode:")
        spawn_mode_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        spawn_mode_var = tk.StringVar(value="incremental")
        self.inputs['spawn_delay_mode'] = spawn_mode_var

        # Incremental mode radio
        incremental_radio = tk.Radiobutton(
            mode_frame,
            text="Incremental",
            variable=spawn_mode_var,
            value="incremental",
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._update_spawn_delay_mode_inputs("incremental")
        )
        incremental_radio.pack(anchor='w', padx=(DarkTheme.PADDING_MEDIUM, 0))

        incremental_hint = ThemedLabel(
            mode_frame,
            text="Delays accumulate between each aircraft (e.g., a/c1: 0s, a/c2: 180s, a/c3: 360s...)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        incremental_hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0), pady=(0, DarkTheme.PADDING_SMALL))

        # Total mode radio
        total_radio = tk.Radiobutton(
            mode_frame,
            text="Total (Realistic)",
            variable=spawn_mode_var,
            value="total",
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._update_spawn_delay_mode_inputs("total")
        )
        total_radio.pack(anchor='w', padx=(DarkTheme.PADDING_MEDIUM, 0))

        total_hint = ThemedLabel(
            mode_frame,
            text="Random spawn times distributed across total session length for realistic traffic",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        total_hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0))

        # Input fields (shown/hidden based on mode)
        inputs_grid = ThemedFrame(self.spawn_delay_frame)
        inputs_grid.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL))

        # Incremental mode input
        self.incremental_input_frame = ThemedFrame(inputs_grid)
        self.incremental_input_frame.pack(fill='x')

        incremental_label = ThemedLabel(self.incremental_input_frame, text="Delay between aircraft (min):")
        incremental_label.grid(row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        incremental_entry = ThemedEntry(self.incremental_input_frame, placeholder="2-5 or 3")
        incremental_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['incremental_delay_value'] = incremental_entry

        incremental_input_hint = ThemedLabel(
            self.incremental_input_frame,
            text="(range or fixed value in minutes)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        incremental_input_hint.grid(row=0, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        self.incremental_input_frame.columnconfigure(1, weight=1)

        # Total mode input
        self.total_input_frame = ThemedFrame(inputs_grid)
        self.total_input_frame.pack(fill='x')
        self.total_input_frame.pack_forget()  # Hide initially

        total_label = ThemedLabel(self.total_input_frame, text="Total session length (min):")
        total_label.grid(row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        total_entry = ThemedEntry(self.total_input_frame, placeholder="30")
        total_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['total_session_minutes'] = total_entry

        total_input_hint = ThemedLabel(
            self.total_input_frame,
            text="(desired training session length)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        total_input_hint.grid(row=0, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        self.total_input_frame.columnconfigure(1, weight=1)

        # Output filename (always visible)
        output_grid = ThemedFrame(section)
        output_grid.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, 0))

        output_label = ThemedLabel(output_grid, text="Output Filename:")
        output_label.grid(row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        output_entry = ThemedEntry(output_grid, placeholder="scenario.air")
        output_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['output_filename'] = output_entry

        output_hint = ThemedLabel(output_grid, text="(optional, auto-generated if empty)", fg=DarkTheme.FG_DISABLED, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        output_hint.grid(row=0, column=2, sticky='w', padx=(DarkTheme.PADDING_SMALL, 0))

        output_grid.columnconfigure(1, weight=1)

    def _add_difficulty_config(self):
        """Add difficulty level configuration (collapsible)"""
        section = ThemedFrame(self.config_container)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # Collapsible header with checkbox
        header_frame = ThemedFrame(section)
        header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_var = tk.BooleanVar(value=False)

        # Create clickable header with toggle indicator
        toggle_label = ThemedLabel(header_frame, text="▶", font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL))
        toggle_label.pack(side='left', padx=(0, DarkTheme.PADDING_SMALL))

        enable_checkbox = tk.Checkbutton(
            header_frame,
            text="Configure by difficulty level (Easy/Medium/Hard)",
            variable=enable_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_difficulty_inputs(enable_var.get(), difficulty_frame, toggle_label)
        )
        enable_checkbox.pack(side='left')
        self.inputs['enable_difficulty'] = enable_var

        # Hint text
        hint = ThemedLabel(
            header_frame,
            text="(splits counts for mixed scenarios)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        hint.pack(side='left', padx=(DarkTheme.PADDING_SMALL, 0))

        # Container for difficulty inputs (hidden by default)
        difficulty_frame = ThemedFrame(section)
        difficulty_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        difficulty_frame.pack_forget()  # Hide initially

        # Grid layout for difficulty inputs
        grid = ThemedFrame(difficulty_frame)
        grid.pack(fill='x', padx=(DarkTheme.PADDING_LARGE, 0))

        # Easy difficulty
        easy_label = ThemedLabel(grid, text="Easy:")
        easy_label.grid(row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        easy_entry = ThemedEntry(grid, placeholder="0")
        easy_entry.grid(row=0, column=1, sticky='ew', padx=(0, DarkTheme.PADDING_LARGE))
        self.inputs['difficulty_easy'] = easy_entry

        # Medium difficulty
        medium_label = ThemedLabel(grid, text="Medium:")
        medium_label.grid(row=0, column=2, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        medium_entry = ThemedEntry(grid, placeholder="0")
        medium_entry.grid(row=0, column=3, sticky='ew', padx=(0, DarkTheme.PADDING_LARGE))
        self.inputs['difficulty_medium'] = medium_entry

        # Hard difficulty
        hard_label = ThemedLabel(grid, text="Hard:")
        hard_label.grid(row=0, column=4, sticky='w', padx=(0, DarkTheme.PADDING_SMALL))

        hard_entry = ThemedEntry(grid, placeholder="0")
        hard_entry.grid(row=0, column=5, sticky='ew')
        self.inputs['difficulty_hard'] = hard_entry

        # Make entry columns expand equally
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        grid.columnconfigure(5, weight=1)

    def _toggle_difficulty_inputs(self, enabled, frame, toggle_label):
        """Show/hide difficulty input fields and aircraft count section based on checkbox state"""
        if enabled:
            # Show difficulty inputs
            frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
            toggle_label.config(text="▼")

            # Hide manual aircraft count section
            if hasattr(self, 'aircraft_counts_section'):
                self.aircraft_counts_section.pack_forget()
        else:
            # Hide difficulty inputs
            frame.pack_forget()
            toggle_label.config(text="▶")

            # Restore manual aircraft count section to its original position
            if hasattr(self, 'aircraft_counts_section'):
                if hasattr(self, '_aircraft_counts_pack_info'):
                    # Use stored pack info to restore exact position
                    self.aircraft_counts_section.pack(**self._aircraft_counts_pack_info)
                else:
                    # Fallback if pack info wasn't stored
                    self.aircraft_counts_section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

    def _toggle_spawn_delay_inputs(self, enabled):
        """Show/hide spawn delay configuration based on checkbox state"""
        if enabled:
            # Store pack info before showing if not already stored
            if not hasattr(self, '_spawn_delay_pack_info'):
                # Since this is the first show, use default pack options
                self.spawn_delay_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL))
                self._spawn_delay_pack_info = self.spawn_delay_frame.pack_info()
            else:
                # Restore to exact original position using stored pack info
                self.spawn_delay_frame.pack(**self._spawn_delay_pack_info)
        else:
            # Store pack info before hiding
            if not hasattr(self, '_spawn_delay_pack_info'):
                self._spawn_delay_pack_info = self.spawn_delay_frame.pack_info()
            self.spawn_delay_frame.pack_forget()

    def _update_spawn_delay_mode_inputs(self, mode):
        """Show/hide spawn delay inputs based on selected mode"""
        if mode == "incremental":
            # Show incremental frame, hide total frame
            if not hasattr(self, '_incremental_pack_info'):
                self.incremental_input_frame.pack(fill='x')
                self._incremental_pack_info = self.incremental_input_frame.pack_info()
            else:
                self.incremental_input_frame.pack(**self._incremental_pack_info)

            if not hasattr(self, '_total_pack_info'):
                self._total_pack_info = self.total_input_frame.pack_info()
            self.total_input_frame.pack_forget()

        elif mode == "total":
            # Show total frame, hide incremental frame
            if not hasattr(self, '_total_pack_info'):
                self.total_input_frame.pack(fill='x')
                self._total_pack_info = self.total_input_frame.pack_info()
            else:
                self.total_input_frame.pack(**self._total_pack_info)

            if not hasattr(self, '_incremental_pack_info'):
                self._incremental_pack_info = self.incremental_input_frame.pack_info()
            self.incremental_input_frame.pack_forget()

    def get_config_values(self):
        """Get all configuration values from inputs"""
        values = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, ThemedEntry):
                values[key] = widget.get_value()
            elif isinstance(widget, tk.BooleanVar):
                values[key] = widget.get()
            elif isinstance(widget, tk.StringVar):
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

        # Validate runways - required for scenarios with arrivals or TRACON (for STAR routing)
        # ground_departures doesn't need runways (uses parking spots only)
        active_runways = config.get('active_runways', '').strip()
        scenarios_requiring_runways = ['ground_mixed', 'tower_mixed', 'tracon_arrivals', 'tracon_mixed']
        if not active_runways and scenario_type in scenarios_requiring_runways:
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
