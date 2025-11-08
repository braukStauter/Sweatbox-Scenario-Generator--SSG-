"""
Dynamic scenario configuration screen with accordion sidebar navigation
"""
import tkinter as tk
from tkinter import messagebox
from gui.theme import DarkTheme
from gui.widgets import (ThemedLabel, ThemedButton, ThemedEntry, ThemedFrame,
                         Card, ScrollableFrame, Footer, AccordionSidebar)


class ScenarioConfigScreen(tk.Frame):
    """Screen for configuring scenario parameters with sidebar navigation"""

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Main container with sidebar and content area
        main_container = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)
        main_container.pack(fill='both', expand=True)

        # Left sidebar (250px width)
        self.sidebar = AccordionSidebar(
            main_container,
            on_category_select=self.on_category_select
        )
        self.sidebar.pack(side='left', fill='y', ipadx=0, ipady=0)
        self.sidebar.configure(width=250)
        self.sidebar.pack_propagate(False)

        # Vertical divider
        divider = tk.Frame(main_container, bg=DarkTheme.DIVIDER, width=1)
        divider.pack(side='left', fill='y')

        # Right content area
        content_area = tk.Frame(main_container, bg=DarkTheme.BG_PRIMARY)
        content_area.pack(side='left', fill='both', expand=True)

        # Header
        header = ThemedFrame(content_area)
        header.pack(fill='x', padx=DarkTheme.PADDING_XLARGE,
                   pady=(DarkTheme.PADDING_XLARGE, DarkTheme.PADDING_LARGE))

        self.title_label = ThemedLabel(
            header,
            text="Configure Scenario",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold')
        )
        self.title_label.pack(anchor='w')

        self.subtitle_label = ThemedLabel(
            header,
            text="Set parameters for your scenario",
            fg=DarkTheme.FG_SECONDARY
        )
        self.subtitle_label.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider_h = tk.Frame(content_area, bg=DarkTheme.DIVIDER, height=1)
        divider_h.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Scrollable content container for configuration panels
        self.scroll_container = ScrollableFrame(content_area)
        self.scroll_container.pack(fill='both', expand=True,
                            padx=DarkTheme.PADDING_XLARGE,
                            pady=DarkTheme.PADDING_MEDIUM)

        self.content_container = self.scroll_container.scrollable_frame

        # Footer with navigation buttons
        footer = ThemedFrame(content_area)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE,
                   pady=DarkTheme.PADDING_LARGE)

        back_button = ThemedButton(footer, text="Back",
                                  command=self.on_back, primary=False)
        back_button.pack(side='left')

        self.next_generate_button = ThemedButton(footer, text="Next",
                                          command=self.on_next_or_generate, primary=True)
        self.next_generate_button.pack(side='right')

        # Copyright footer
        copyright_footer = Footer(content_area)
        copyright_footer.pack(side='bottom', fill='x')

        # Store input widgets and content panels
        self.inputs = {}
        self.content_panels = {}
        self.current_panel = None
        self.current_category_index = 0
        self.category_order = []  # Will be populated based on scenario type

        # Initialize sidebar categories
        self._init_sidebar_categories()

    def _init_sidebar_categories(self):
        """Initialize sidebar navigation categories (will be rebuilt based on scenario type)"""
        # Categories will be dynamically added in load_config_for_scenario
        pass

    def _rebuild_sidebar_for_scenario(self, scenario_type):
        """Rebuild sidebar categories based on scenario type"""
        # Clear existing items
        for item in self.sidebar.items:
            item.destroy()
        self.sidebar.items.clear()
        self.sidebar.selected_item = None

        # Determine which features this scenario needs
        has_departures = scenario_type in ['ground_departures', 'ground_mixed', 'tower_mixed', 'tracon_departures', 'tracon_mixed']
        has_arrivals = scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_arrivals', 'tracon_mixed']
        has_tower_separation = scenario_type == 'tower_mixed'
        has_tracon_arrivals = scenario_type in ['tracon_arrivals', 'tracon_mixed']  # TRACON scenarios have configurable STAR arrivals
        has_tower_arrivals = scenario_type == 'tower_mixed'  # Tower scenarios have VFR arrivals

        # Build category order list for navigation
        self.category_order = []

        # Category 1: Aircraft & Traffic (always shown)
        self.sidebar.add_item("Aircraft & Traffic", "aircraft_traffic")
        self.category_order.append("aircraft_traffic")

        # Category 2: Runway & Airport (always shown, but content varies)
        self.sidebar.add_item("Runway & Airport", "runway_airport")
        self.category_order.append("runway_airport")

        # Category 3: Timing & Spawning (always shown)
        self.sidebar.add_item("Timing & Spawning", "timing_spawning")
        self.category_order.append("timing_spawning")

        # Category 4: Arrivals & Approach (for TRACON with STAR config, or Tower with VFR config)
        if has_tracon_arrivals or has_tower_arrivals:
            self.sidebar.add_item("Arrivals & Approach", "arrivals_approach")
            self.category_order.append("arrivals_approach")

        # Category 5: Departures & Climb (only for scenarios with departures)
        if has_departures:
            self.sidebar.add_item("Departures & Climb", "departures_climb")
            self.category_order.append("departures_climb")

        # Category 6: Advanced Options (always shown for future expansion)
        self.sidebar.add_item("Advanced Options", "advanced")
        self.category_order.append("advanced")

        # Category 7: Output & Export (always shown)
        self.sidebar.add_item("Output & Export", "output_export")
        self.category_order.append("output_export")

        # Store scenario features for use in panel building
        self.scenario_has_departures = has_departures
        self.scenario_has_arrivals = has_arrivals
        self.scenario_has_tower_separation = has_tower_separation
        self.scenario_has_tracon_arrivals = has_tracon_arrivals
        self.scenario_has_tower_arrivals = has_tower_arrivals

    def on_category_select(self, category_id):
        """Handle category selection from sidebar"""
        # Hide current panel
        if self.current_panel:
            self.current_panel.pack_forget()

        # Show selected panel (create if needed)
        if category_id not in self.content_panels:
            self.content_panels[category_id] = self._create_panel(category_id)

        panel = self.content_panels[category_id]
        panel.pack(fill='both', expand=True)

        # Update scroll region after panel is shown
        self.after(50, self._update_scroll_region)
        self.current_panel = panel

        # Update current category index and button text
        if category_id in self.category_order:
            self.current_category_index = self.category_order.index(category_id)
            self._update_button_text()

    def _create_panel(self, category_id):
        """Create content panel for a category"""
        panel = ThemedFrame(self.content_container)

        if category_id == "aircraft_traffic":
            self._build_aircraft_traffic_panel(panel)
        elif category_id == "runway_airport":
            self._build_runway_airport_panel(panel)
        elif category_id == "timing_spawning":
            self._build_timing_spawning_panel(panel)
        elif category_id == "arrivals_approach":
            self._build_arrivals_approach_panel(panel)
        elif category_id == "departures_climb":
            self._build_departures_climb_panel(panel)
        elif category_id == "advanced":
            self._build_advanced_panel(panel)
        elif category_id == "output_export":
            self._build_output_export_panel(panel)

        return panel

    def _update_scroll_region(self):
        """Force update the scroll region to show all content"""
        if hasattr(self, 'scroll_container'):
            # Force widget updates before recalculating scroll region
            self.update_idletasks()
            self.scroll_container.scrollable_frame.update_idletasks()
            self.scroll_container._update_scrollregion()

    def _build_aircraft_traffic_panel(self, panel):
        """Build Aircraft & Traffic configuration panel"""
        # Panel title
        title = ThemedLabel(
            panel,
            text="Aircraft & Traffic Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Difficulty levels section (collapsible)
        self._add_difficulty_section(panel)
        self._add_divider(panel)

        # Aircraft counts section (conditional based on scenario type)
        has_departures = getattr(self, 'scenario_has_departures', True)
        has_arrivals = getattr(self, 'scenario_has_arrivals', True)
        self._add_aircraft_counts_section(panel, has_departures, has_arrivals)

    def _build_runway_airport_panel(self, panel):
        """Build Runway & Airport configuration panel"""
        title = ThemedLabel(
            panel,
            text="Runway & Airport Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Active runways
        section = ThemedFrame(panel)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))

        label = ThemedLabel(
            section,
            text="Active Runways:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(section, placeholder="e.g., 7L, 25R")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['active_runways'] = entry

        hint = ThemedLabel(
            section,
            text="Comma separated list of runway identifiers",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        hint.pack(anchor='w')

        # Separation standards (only for tower scenarios)
        if hasattr(self, 'scenario_has_tower_separation') and self.scenario_has_tower_separation:
            self._add_divider(panel)
            self._add_separation_section(panel)

    def _build_timing_spawning_panel(self, panel):
        """Build Timing & Spawning configuration panel"""
        title = ThemedLabel(
            panel,
            text="Timing & Spawning Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Spawn delay configuration
        self._add_spawn_delay_section(panel)

    def _build_arrivals_approach_panel(self, panel):
        """Build Arrivals & Approach configuration panel"""
        title = ThemedLabel(
            panel,
            text="Arrivals & Approach Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # TRACON scenarios: Show STAR waypoint configuration
        if hasattr(self, 'scenario_has_tracon_arrivals') and self.scenario_has_tracon_arrivals:
            self._add_tracon_arrivals_section(panel)

        # Tower scenarios: Show VFR aircraft configuration
        if hasattr(self, 'scenario_has_tower_arrivals') and self.scenario_has_tower_arrivals:
            self._add_vfr_aircraft_section(panel)

    def _build_departures_climb_panel(self, panel):
        """Build Departures & Climb configuration panel"""
        title = ThemedLabel(
            panel,
            text="Departures & Climb Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # CIFP SID Configuration
        self._add_cifp_sid_section(panel)

    def _build_advanced_panel(self, panel):
        """Build Advanced Options configuration panel"""
        title = ThemedLabel(
            panel,
            text="Advanced Configuration Options",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Advanced options go here (difficulty is in Aircraft & Traffic tab)

    def _build_output_export_panel(self, panel):
        """Build Output & Export configuration panel"""
        title = ThemedLabel(
            panel,
            text="Output & Export Settings",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Output filename info
        info = ThemedLabel(
            panel,
            text="Output filename is automatically generated based on airport code",
            fg=DarkTheme.FG_SECONDARY
        )
        info.pack(anchor='w', pady=DarkTheme.PADDING_MEDIUM)

    # Helper methods for building sections

    def _add_divider(self, parent):
        """Add a subtle divider line"""
        divider = tk.Frame(parent, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

    def _add_difficulty_section(self, parent):
        """Add difficulty level configuration section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # Collapsible header with checkbox
        header_frame = ThemedFrame(section)
        header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_var = tk.BooleanVar(value=False)

        # Create clickable header with toggle indicator
        toggle_label = ThemedLabel(
            header_frame,
            text="▶",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
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
            command=lambda: self._toggle_difficulty_inputs(
                enable_var.get(), difficulty_frame, toggle_label
            )
        )
        enable_checkbox.pack(side='left')
        self.inputs['enable_difficulty'] = enable_var

        # Hint text
        hint = ThemedLabel(
            header_frame,
            text="(splits aircraft counts into difficulty tiers)",
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
        easy_label.grid(row=0, column=0, sticky='w',
                       padx=(0, DarkTheme.PADDING_SMALL))

        easy_entry = ThemedEntry(grid, placeholder="0")
        easy_entry.grid(row=0, column=1, sticky='ew',
                       padx=(0, DarkTheme.PADDING_LARGE))
        self.inputs['difficulty_easy'] = easy_entry

        # Medium difficulty
        medium_label = ThemedLabel(grid, text="Medium:")
        medium_label.grid(row=0, column=2, sticky='w',
                         padx=(0, DarkTheme.PADDING_SMALL))

        medium_entry = ThemedEntry(grid, placeholder="0")
        medium_entry.grid(row=0, column=3, sticky='ew',
                         padx=(0, DarkTheme.PADDING_LARGE))
        self.inputs['difficulty_medium'] = medium_entry

        # Hard difficulty
        hard_label = ThemedLabel(grid, text="Hard:")
        hard_label.grid(row=0, column=4, sticky='w',
                       padx=(0, DarkTheme.PADDING_SMALL))

        hard_entry = ThemedEntry(grid, placeholder="0")
        hard_entry.grid(row=0, column=5, sticky='ew')
        self.inputs['difficulty_hard'] = hard_entry

        # Make entry columns expand equally
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        grid.columnconfigure(5, weight=1)

        # Store references for toggling
        self.difficulty_section = section
        self.difficulty_frame = difficulty_frame
        self.difficulty_toggle_label = toggle_label

    def _add_aircraft_counts_section(self, parent, has_departures=True, has_arrivals=True):
        """Add aircraft counts section (conditional based on scenario type)"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Section title
        title = ThemedLabel(
            section,
            text="Aircraft Count",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Grid container for inputs
        grid_frame = ThemedFrame(section)
        grid_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        col = 0

        # Departures (if applicable)
        if has_departures:
            dep_label = ThemedLabel(grid_frame, text="Departures:")
            dep_label.grid(row=0, column=col, sticky='w',
                          padx=(0, DarkTheme.PADDING_SMALL))

            dep_entry = ThemedEntry(grid_frame, placeholder="e.g., 10")
            dep_entry.grid(row=0, column=col+1, sticky='ew',
                          padx=(0, DarkTheme.PADDING_LARGE))
            self.inputs['num_departures'] = dep_entry

            grid_frame.columnconfigure(col+1, weight=1)
            col += 2

        # Arrivals (if applicable)
        if has_arrivals:
            arr_label = ThemedLabel(grid_frame, text="Arrivals:")
            arr_label.grid(row=0, column=col, sticky='w',
                          padx=(0, DarkTheme.PADDING_SMALL))

            arr_entry = ThemedEntry(grid_frame, placeholder="e.g., 5")
            arr_entry.grid(row=0, column=col+1, sticky='ew',
                          padx=(0, DarkTheme.PADDING_LARGE if has_departures else 0))
            self.inputs['num_arrivals'] = arr_entry

            grid_frame.columnconfigure(col+1, weight=1)

        # Store reference
        self.aircraft_counts_section = section

    def _add_separation_section(self, parent):
        """Add separation standards section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        label = ThemedLabel(
            section,
            text="Separation Range (NM):",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(section, placeholder="3-6")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['separation_range'] = entry

        hint = ThemedLabel(
            section,
            text="Format: min-max (e.g., 3-6 for 3-6 nautical miles)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        hint.pack(anchor='w')

    def _add_spawn_delay_section(self, parent):
        """Add spawn delay configuration section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

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
        self.spawn_delay_frame.pack(fill='x',
                                   pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL))
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
        incremental_hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0),
                             pady=(0, DarkTheme.PADDING_SMALL))

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

        incremental_label = ThemedLabel(
            self.incremental_input_frame,
            text="Delay between aircraft (min):"
        )
        incremental_label.grid(row=0, column=0, sticky='w',
                              padx=(0, DarkTheme.PADDING_SMALL))

        incremental_entry = ThemedEntry(self.incremental_input_frame,
                                       placeholder="2-5 or 3")
        incremental_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['incremental_delay_value'] = incremental_entry

        incremental_input_hint = ThemedLabel(
            self.incremental_input_frame,
            text="(range or fixed value in minutes)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        incremental_input_hint.grid(row=0, column=2, sticky='w',
                                   padx=(DarkTheme.PADDING_SMALL, 0))

        self.incremental_input_frame.columnconfigure(1, weight=1)

        # Total mode input
        self.total_input_frame = ThemedFrame(inputs_grid)
        self.total_input_frame.pack(fill='x')
        self.total_input_frame.pack_forget()  # Hide initially

        total_label = ThemedLabel(self.total_input_frame,
                                 text="Total session length (min):")
        total_label.grid(row=0, column=0, sticky='w',
                        padx=(0, DarkTheme.PADDING_SMALL))

        total_entry = ThemedEntry(self.total_input_frame, placeholder="30")
        total_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['total_session_minutes'] = total_entry

        total_input_hint = ThemedLabel(
            self.total_input_frame,
            text="(desired training session length)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        total_input_hint.grid(row=0, column=2, sticky='w',
                             padx=(DarkTheme.PADDING_SMALL, 0))

        self.total_input_frame.columnconfigure(1, weight=1)

    def _add_tracon_arrivals_section(self, parent):
        """Add TRACON arrivals specific configuration"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # STAR Waypoints
        waypoint_label = ThemedLabel(
            section,
            text="STAR Waypoints:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        waypoint_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        waypoints_entry = ThemedEntry(section,
                                     placeholder="e.g., EAGUL.JESSE3, PINNG.PINNG1 (or leave blank for random)")
        waypoints_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['arrival_waypoints'] = waypoints_entry

        waypoint_hint = ThemedLabel(
            section,
            text="Format: WAYPOINT.STAR, WAYPOINT. (any STAR with waypoint), or WAYPOINT (waypoint only). Leave blank to auto-select random STAR transitions.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        waypoint_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM))

    def _add_vfr_aircraft_section(self, parent):
        """Add VFR aircraft configuration section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # Enable VFR aircraft checkbox
        vfr_header_frame = ThemedFrame(section)
        vfr_header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_vfr_var = tk.BooleanVar(value=False)

        enable_vfr_checkbox = tk.Checkbutton(
            vfr_header_frame,
            text="Dynamic Tower Approach Scenarios",
            variable=enable_vfr_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_vfr_inputs(enable_vfr_var.get())
        )
        enable_vfr_checkbox.pack(anchor='w')
        self.inputs['enable_vfr'] = enable_vfr_var

        # Hint text
        vfr_hint = ThemedLabel(
            section,
            text="Generate VFR GA aircraft for Class D / tower training scenarios",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        vfr_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Container for VFR-specific options (hidden by default)
        self.vfr_frame = ThemedFrame(section)
        self.vfr_frame.pack_forget()

        # Number of VFR aircraft
        num_vfr_label = ThemedLabel(
            self.vfr_frame,
            text="Number of VFR aircraft:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        num_vfr_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        num_vfr_entry = ThemedEntry(
            self.vfr_frame,
            placeholder="e.g., 5"
        )
        num_vfr_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['num_vfr'] = num_vfr_entry

        num_vfr_hint = ThemedLabel(
            self.vfr_frame,
            text="Number of VFR GA aircraft to generate",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        num_vfr_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM))

        # VFR spawn locations (optional)
        spawn_locations_label = ThemedLabel(
            self.vfr_frame,
            text="Spawn locations (optional):",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        spawn_locations_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        spawn_locations_entry = ThemedEntry(
            self.vfr_frame,
            placeholder="e.g., KABQ020010,KABQ090012 (FRD format)"
        )
        spawn_locations_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['vfr_spawn_locations'] = spawn_locations_entry

        spawn_locations_hint = ThemedLabel(
            self.vfr_frame,
            text="Comma-separated FRD strings (Fix/Radial/Distance). Leave blank to generate random positions 8-12 NM from airport.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        spawn_locations_hint.pack(anchor='w')

    def _add_cifp_sid_section(self, parent):
        """Add CIFP SID configuration section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # Enable CIFP SIDs checkbox
        sid_header_frame = ThemedFrame(section)
        sid_header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_cifp_sids_var = tk.BooleanVar(value=True)

        enable_cifp_checkbox = tk.Checkbutton(
            sid_header_frame,
            text="Use CIFP departure procedures (SIDs)",
            variable=enable_cifp_sids_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_cifp_sid_inputs(enable_cifp_sids_var.get())
        )
        enable_cifp_checkbox.pack(anchor='w')
        self.inputs['enable_cifp_sids'] = enable_cifp_sids_var

        # Hint text (on separate line below checkbox)
        cifp_hint = ThemedLabel(
            section,
            text="Filter API routes to only include SIDs that match active runways. Uncheck to accept any API route.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        cifp_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Container for SID-specific options (shown by default)
        self.cifp_sid_frame = ThemedFrame(section)
        self.cifp_sid_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))

        # Manual SID specification (optional)
        manual_sid_label = ThemedLabel(
            self.cifp_sid_frame,
            text="Specific SIDs to use (optional):",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        manual_sid_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        manual_sids_entry = ThemedEntry(
            self.cifp_sid_frame,
            placeholder="e.g., RDRNR3, CTZEN3 (leave blank for auto-selection)"
        )
        manual_sids_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['manual_sids'] = manual_sids_entry

        manual_sid_hint = ThemedLabel(
            self.cifp_sid_frame,
            text="Comma-separated list of SIDs. API routes will be filtered to only these SIDs. Leave blank to auto-filter by active runways.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        manual_sid_hint.pack(anchor='w')

    # Toggle methods

    def _toggle_difficulty_inputs(self, enabled, frame, toggle_label):
        """Show/hide difficulty input fields"""
        if enabled:
            frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
            toggle_label.config(text="▼")

            # Hide manual aircraft count section
            if hasattr(self, 'aircraft_counts_section'):
                self.aircraft_counts_section.pack_forget()
        else:
            frame.pack_forget()
            toggle_label.config(text="▶")

            # Show manual aircraft count section
            if hasattr(self, 'aircraft_counts_section'):
                self.aircraft_counts_section.pack(
                    fill='x',
                    pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL)
                )

        # Update scroll region to show new content
        self.after(50, self._update_scroll_region)

    def _toggle_spawn_delay_inputs(self, enabled):
        """Show/hide spawn delay configuration"""
        if enabled:
            self.spawn_delay_frame.pack(
                fill='x',
                pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL)
            )
        else:
            self.spawn_delay_frame.pack_forget()

        # Update scroll region to show new content
        self.after(50, self._update_scroll_region)

    def _toggle_cifp_sid_inputs(self, enabled):
        """Show/hide CIFP SID configuration"""
        if enabled:
            self.cifp_sid_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        else:
            self.cifp_sid_frame.pack_forget()

        # Update scroll region to show new content
        self.after(50, self._update_scroll_region)

    def _toggle_vfr_inputs(self, enabled):
        """Show/hide VFR aircraft configuration"""
        if enabled:
            self.vfr_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        else:
            self.vfr_frame.pack_forget()

        # Update scroll region multiple times to ensure it catches the layout changes
        self.after_idle(self._update_scroll_region)
        self.after(100, self._update_scroll_region)
        self.after(300, self._update_scroll_region)

    def _update_spawn_delay_mode_inputs(self, mode):
        """Show/hide spawn delay inputs based on selected mode"""
        if mode == "incremental":
            self.incremental_input_frame.pack(fill='x')
            self.total_input_frame.pack_forget()
        elif mode == "total":
            self.total_input_frame.pack(fill='x')
            self.incremental_input_frame.pack_forget()

        # Update scroll region to show new content
        self.after(50, self._update_scroll_region)

    # Screen lifecycle methods

    def load_config_for_scenario(self, scenario_type):
        """Load configuration form based on scenario type"""
        # Store scenario type for validation
        self.scenario_type = scenario_type

        # Update subtitle
        scenario_names = {
            'ground_departures': 'Ground - Departures Only',
            'ground_mixed': 'Ground - Mixed Operations',
            'tower_mixed': 'Tower - Mixed Operations',
            'tracon_departures': 'TRACON - Departures Only',
            'tracon_arrivals': 'TRACON - Arrivals Only',
            'tracon_mixed': 'TRACON - Mixed Operations'
        }
        scenario_name = scenario_names.get(scenario_type, 'Unknown')
        self.subtitle_label.config(text=f"Scenario Type: {scenario_name}")

        # Clear all content panels and inputs
        for panel in self.content_panels.values():
            panel.destroy()
        self.content_panels.clear()
        self.current_panel = None
        self.inputs.clear()

        # Rebuild sidebar based on scenario type
        self._rebuild_sidebar_for_scenario(scenario_type)

        # Select first category by default
        if self.sidebar.items:
            first_item = self.sidebar.items[0]
            first_item.select()
            self.sidebar.selected_item = first_item
            # Reset to first category
            self.current_category_index = 0
            # Trigger category selection
            self.on_category_select("aircraft_traffic")

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
        if not self.category_order:
            self.app_controller.show_screen('scenario_type')
            return

        # If on first tab, go back to scenario type selection
        if self.current_category_index <= 0:
            self.app_controller.show_screen('scenario_type')
        else:
            # Navigate to previous category/tab
            prev_index = self.current_category_index - 1
            if prev_index >= 0:
                prev_category = self.category_order[prev_index]

                # Select the previous sidebar item
                for item in self.sidebar.items:
                    if item.category_id == prev_category:
                        item.select()
                        break

                # Trigger category selection (which updates button text)
                self.on_category_select(prev_category)

    def _update_button_text(self):
        """Update button text based on current category"""
        if not self.category_order:
            return

        # Check if we're on the last category (Output & Export)
        is_last_category = self.current_category_index >= len(self.category_order) - 1

        if is_last_category:
            self.next_generate_button.config(text="Generate")
        else:
            self.next_generate_button.config(text="Next")

    def on_next_or_generate(self):
        """Handle Next/Generate button click"""
        if not self.category_order:
            return

        # Check if we're on the last category
        is_last_category = self.current_category_index >= len(self.category_order) - 1

        if is_last_category:
            # On last category - validate and generate
            self.on_generate()
        else:
            # Navigate to next category
            next_index = self.current_category_index + 1
            if next_index < len(self.category_order):
                next_category = self.category_order[next_index]

                # Select the next sidebar item
                for item in self.sidebar.items:
                    if item.category_id == next_category:
                        item.select()
                        break

                # Trigger category selection (which updates button text)
                self.on_category_select(next_category)

    def on_generate(self):
        """Handle generate button click"""
        config = self.get_config_values()

        # Validate required fields
        validation_errors = self._validate_config(config)
        if validation_errors:
            messagebox.showerror(
                "Configuration Error",
                "Please fix the following errors:\n\n" +
                "\n".join(f"• {error}" for error in validation_errors)
            )
            return

        self.app_controller.generate_scenario(config)

    def _validate_config(self, config):
        """Validate configuration values"""
        errors = []

        # Get scenario type from stored value
        scenario_type = self.scenario_type

        # Validate runways - required for all scenarios
        active_runways = config.get('active_runways', '').strip()
        if not active_runways:
            errors.append("Active runways are required (needed for CIFP SID filtering and arrival procedures)")

        # Check if difficulty levels are enabled
        difficulty_enabled = config.get('enable_difficulty', False)

        if difficulty_enabled:
            # Validate difficulty counts
            try:
                easy_count = int(config.get('difficulty_easy', '0') or '0')
                medium_count = int(config.get('difficulty_medium', '0') or '0')
                hard_count = int(config.get('difficulty_hard', '0') or '0')

                if easy_count < 0 or medium_count < 0 or hard_count < 0:
                    errors.append("Difficulty counts cannot be negative")

                total_aircraft = easy_count + medium_count + hard_count
                if total_aircraft == 0:
                    errors.append("Must specify at least one aircraft in difficulty levels")
            except ValueError:
                errors.append("Difficulty counts must be valid numbers")
        else:
            # Validate manual aircraft counts
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
                errors.append("Aircraft counts must be valid numbers")

        # Validate ranges
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

        # Validate spawn delay values if enabled
        if config.get('enable_spawn_delays'):
            mode = config.get('spawn_delay_mode', 'incremental')
            if mode == 'incremental':
                delay_value = config.get('incremental_delay_value', '')
                if not delay_value:
                    errors.append("Incremental delay value is required when spawn delays are enabled")
            elif mode == 'total':
                total_minutes = config.get('total_session_minutes', '')
                if not total_minutes:
                    errors.append("Total session minutes is required when using total spawn delay mode")
                else:
                    try:
                        minutes = int(total_minutes)
                        if minutes <= 0:
                            errors.append("Total session minutes must be positive")
                    except ValueError:
                        errors.append("Total session minutes must be a valid number")

        return errors
