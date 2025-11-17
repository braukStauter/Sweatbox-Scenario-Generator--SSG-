"""
Dynamic scenario configuration screen with accordion sidebar navigation
"""
import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import DarkTheme
from gui.widgets import (ThemedLabel, ThemedButton, ThemedEntry, ThemedFrame,
                         Card, ScrollableFrame, Footer, AccordionSidebar)
from models.preset_command import PresetCommandRule
from utils.preset_command_processor import get_available_variables, get_variable_description


class ScenarioConfigScreen(tk.Frame):
    """Screen for configuring scenario parameters with sidebar navigation"""

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Configure dark theme for comboboxes
        self._setup_combobox_style()

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

        # Store preset command rules
        self.preset_command_rules = []

        # Initialize sidebar categories
        self._init_sidebar_categories()

    def _setup_combobox_style(self):
        """Setup dark-themed combobox styling"""
        style = ttk.Style()
        style.theme_use('clam')

        # Configure the dark theme combobox
        style.configure(
            'Dark.TCombobox',
            fieldbackground=DarkTheme.BG_SECONDARY,
            background=DarkTheme.BG_SECONDARY,
            foreground=DarkTheme.FG_PRIMARY,
            arrowcolor=DarkTheme.FG_PRIMARY,
            bordercolor=DarkTheme.BORDER,
            lightcolor=DarkTheme.BG_SECONDARY,
            darkcolor=DarkTheme.BG_SECONDARY,
            borderwidth=1,
            relief='solid'
        )

        # Configure combobox states
        style.map('Dark.TCombobox',
                  fieldbackground=[('readonly', DarkTheme.BG_SECONDARY), ('disabled', DarkTheme.BG_TERTIARY)],
                  selectbackground=[('readonly', DarkTheme.BG_SECONDARY)],
                  selectforeground=[('readonly', DarkTheme.FG_PRIMARY)],
                  foreground=[('disabled', DarkTheme.FG_DISABLED)])

        # Configure the dropdown list
        self.option_add('*TCombobox*Listbox.background', DarkTheme.BG_SECONDARY)
        self.option_add('*TCombobox*Listbox.foreground', DarkTheme.FG_PRIMARY)
        self.option_add('*TCombobox*Listbox.selectBackground', DarkTheme.ACCENT_PRIMARY)
        self.option_add('*TCombobox*Listbox.selectForeground', DarkTheme.FG_PRIMARY)
        self.option_add('*TCombobox*Listbox.font', (DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL))

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

        # Build category order list for navigation
        self.category_order = []

        # Check if this is an enroute scenario
        is_enroute = self.app_controller.is_enroute_scenario

        if is_enroute:
            # Enroute scenario sidebar
            self.sidebar.add_item("ARTCC & Aircraft", "enroute_aircraft")
            self.category_order.append("enroute_aircraft")

            self.sidebar.add_item("Airports & Routes", "enroute_airports")
            self.category_order.append("enroute_airports")

            self.sidebar.add_item("Timing & Spawning", "timing_spawning")
            self.category_order.append("timing_spawning")

            self.sidebar.add_item("Custom Commands", "custom_commands")
            self.category_order.append("custom_commands")

            self.sidebar.add_item("Output & Export", "output_export")
            self.category_order.append("output_export")

            # Store enroute flag
            self.is_enroute_scenario = True
        else:
            # Regular airport-based scenario sidebar
            self.is_enroute_scenario = False

            # Determine which features this scenario needs
            has_departures = scenario_type in ['ground_departures', 'ground_mixed', 'tower_mixed', 'tracon_mixed']
            has_arrivals = scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_arrivals', 'tracon_mixed']
            has_tower_separation = scenario_type in ['ground_mixed', 'tower_mixed']  # Scenarios with arrival separation
            has_tracon_arrivals = scenario_type in ['tracon_arrivals', 'tracon_mixed']  # TRACON scenarios have configurable STAR arrivals
            has_tower_arrivals = scenario_type == 'tower_mixed'  # Tower scenarios have VFR arrivals

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

    def _validate_current_category(self):
        """Validate the current category before allowing navigation away from it"""
        if not hasattr(self, 'current_category_index') or self.current_category_index is None:
            return True  # No current category, allow navigation

        current_category_id = self.category_order[self.current_category_index]
        errors = []

        # Get current configuration
        config = self.get_config_values()
        scenario_type = self.scenario_type

        # Validate based on current category
        if current_category_id == "aircraft_traffic":
            # Validate aircraft counts
            difficulty_enabled = config.get('enable_difficulty', False)
            if difficulty_enabled:
                try:
                    # Check departures difficulty
                    dep_easy = int(config.get('difficulty_departures_easy', '0') or '0')
                    dep_medium = int(config.get('difficulty_departures_medium', '0') or '0')
                    dep_hard = int(config.get('difficulty_departures_hard', '0') or '0')

                    # Check arrivals difficulty
                    arr_easy = int(config.get('difficulty_arrivals_easy', '0') or '0')
                    arr_medium = int(config.get('difficulty_arrivals_medium', '0') or '0')
                    arr_hard = int(config.get('difficulty_arrivals_hard', '0') or '0')

                    if any(x < 0 for x in [dep_easy, dep_medium, dep_hard, arr_easy, arr_medium, arr_hard]):
                        errors.append("Difficulty counts cannot be negative")

                    total_aircraft = dep_easy + dep_medium + dep_hard + arr_easy + arr_medium + arr_hard
                    if total_aircraft == 0:
                        errors.append("Must specify at least one aircraft across all difficulty levels and categories")
                except ValueError:
                    errors.append("Difficulty counts must be valid numbers")
            else:
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

        elif current_category_id == "runway_airport":
            # Validate runways
            active_runways = config.get('active_runways', '').strip()
            if not active_runways:
                errors.append("Active runways are required")

        elif current_category_id == "arrivals_approach":
            # Validate TRACON arrival waypoints if applicable
            if scenario_type in ['tracon_arrivals', 'tracon_mixed']:
                arrival_waypoints = config.get('arrival_waypoints', '').strip()
                if not arrival_waypoints:
                    errors.append("STAR Waypoints are required (e.g., EAGUL.EAGUL6, PINNG.PINNG1)")

        elif current_category_id == "enroute_aircraft":
            # Validate enroute aircraft counts
            difficulty_enabled = config.get('enable_difficulty_enroute', False)
            if difficulty_enabled:
                # Validate difficulty levels
                try:
                    enroute_easy = int(config.get('difficulty_enroute_easy', '0') or '0')
                    enroute_medium = int(config.get('difficulty_enroute_medium', '0') or '0')
                    enroute_hard = int(config.get('difficulty_enroute_hard', '0') or '0')

                    arrivals_easy = int(config.get('difficulty_arrivals_easy', '0') or '0')
                    arrivals_medium = int(config.get('difficulty_arrivals_medium', '0') or '0')
                    arrivals_hard = int(config.get('difficulty_arrivals_hard', '0') or '0')

                    departures_easy = int(config.get('difficulty_departures_easy', '0') or '0')
                    departures_medium = int(config.get('difficulty_departures_medium', '0') or '0')
                    departures_hard = int(config.get('difficulty_departures_hard', '0') or '0')

                    if any(x < 0 for x in [enroute_easy, enroute_medium, enroute_hard,
                                           arrivals_easy, arrivals_medium, arrivals_hard,
                                           departures_easy, departures_medium, departures_hard]):
                        errors.append("Difficulty counts cannot be negative")

                    total_enroute = enroute_easy + enroute_medium + enroute_hard
                    total_arrivals = arrivals_easy + arrivals_medium + arrivals_hard
                    total_departures = departures_easy + departures_medium + departures_hard
                    total_aircraft = total_enroute + total_arrivals + total_departures

                    if total_aircraft == 0:
                        errors.append("Must specify at least one aircraft across all difficulty levels and categories")

                except ValueError:
                    errors.append("Difficulty counts must be valid numbers")
            else:
                # Validate aircraft counts
                try:
                    num_enroute = int(config.get('num_enroute', '0') or '0')
                    num_arrivals = int(config.get('num_arrivals_enroute', '0') or '0')
                    num_departures = int(config.get('num_departures_enroute', '0') or '0')

                    if num_enroute < 0:
                        errors.append("Number of enroute aircraft cannot be negative")
                    if num_arrivals < 0:
                        errors.append("Number of arrivals cannot be negative")
                    if num_departures < 0:
                        errors.append("Number of departures cannot be negative")

                    if num_enroute == 0 and num_arrivals == 0 and num_departures == 0:
                        errors.append("Must generate at least one aircraft (enroute, arrival, or departure)")
                except ValueError:
                    errors.append("Aircraft counts must be valid numbers")

        elif current_category_id == "enroute_airports":
            # Validate arrival and departure airports if aircraft are specified
            config_dict = config

            # Check if any arrivals are specified
            difficulty_enabled = config_dict.get('enable_difficulty_enroute', False)
            if difficulty_enabled:
                arrivals_count = (int(config_dict.get('difficulty_arrivals_easy', '0') or '0') +
                                 int(config_dict.get('difficulty_arrivals_medium', '0') or '0') +
                                 int(config_dict.get('difficulty_arrivals_hard', '0') or '0'))
                departures_count = (int(config_dict.get('difficulty_departures_easy', '0') or '0') +
                                   int(config_dict.get('difficulty_departures_medium', '0') or '0') +
                                   int(config_dict.get('difficulty_departures_hard', '0') or '0'))
            else:
                arrivals_count = int(config_dict.get('num_arrivals_enroute', '0') or '0')
                departures_count = int(config_dict.get('num_departures_enroute', '0') or '0')

            # Validate arrival airports if arrivals are specified
            if arrivals_count > 0:
                arrival_airports = config_dict.get('arrival_airports_group', '').strip()
                if not arrival_airports:
                    arrival_manual = config_dict.get('arrival_airports_manual', '').strip()
                    if not arrival_manual:
                        errors.append("Arrival airports are required when generating arrival aircraft")

            # Validate departure airports if departures are specified
            if departures_count > 0:
                departure_airports = config_dict.get('departure_airports_group', '').strip()
                if not departure_airports:
                    departure_manual = config_dict.get('departure_airports_manual', '').strip()
                    if not departure_manual:
                        errors.append("Departure airports are required when generating departure aircraft")

        elif current_category_id == "timing_spawning":
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

        # Show errors if any
        if errors:
            from tkinter import messagebox
            error_message = "Please fix the following issues before continuing:\n\n" + "\n".join(f"• {error}" for error in errors)
            messagebox.showerror("Validation Error", error_message)
            return False

        return True

    def on_category_select(self, category_id):
        """Handle category selection from sidebar"""
        # Only validate if we have a current panel (not initial load)
        # and if we're actually changing categories AND moving forward
        should_validate = False
        if (hasattr(self, 'current_panel') and
            self.current_panel is not None and
            hasattr(self, 'current_category_index') and
            self.current_category_index is not None and
            category_id in self.category_order):

            current_index = self.current_category_index
            new_index = self.category_order.index(category_id)

            # Only validate if moving forward (to a higher index)
            should_validate = new_index > current_index

        if should_validate and not self._validate_current_category():
            # Validation failed, re-select the current category
            current_id = self.category_order[self.current_category_index]
            # Re-select current item in sidebar
            for item in self.sidebar.items:
                if hasattr(item, 'category_id') and item.category_id == current_id:
                    if self.sidebar.selected_item != item:
                        if self.sidebar.selected_item:
                            self.sidebar.selected_item.deselect()
                        item.select()
                        self.sidebar.selected_item = item
                    break
            return

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

        # Enroute scenario panels
        if category_id == "enroute_aircraft":
            self._build_enroute_aircraft_panel(panel)
        elif category_id == "enroute_airports":
            self._build_enroute_airports_panel(panel)
        elif category_id == "custom_commands":
            self._build_custom_commands_panel(panel)
        # Regular scenario panels
        elif category_id == "aircraft_traffic":
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

        # Create label with red asterisk for required field
        label_frame = tk.Frame(section, bg=DarkTheme.BG_PRIMARY)
        label_frame.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            label_frame,
            text="Active Runways:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        ).pack(side='left')

        tk.Label(
            label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        entry = ThemedEntry(section, placeholder="e.g., 7L, 25R", validate_type="runway")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['active_runways'] = entry

        hint = ThemedLabel(
            section,
            text="Comma separated list of runway identifiers",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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

        # Preset Commands Section
        self._add_preset_commands_section(panel)

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

    # Enroute scenario panel builders

    def _build_enroute_aircraft_panel(self, panel):
        """Build ARTCC & Aircraft configuration panel for enroute scenarios"""
        title = ThemedLabel(
            panel,
            text="ARTCC & Aircraft Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # ARTCC Info
        artcc_id = getattr(self.app_controller, 'artcc_id', 'Unknown')
        info = ThemedLabel(
            panel,
            text=f"Selected ARTCC: {artcc_id}",
            fg=DarkTheme.FG_SECONDARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        info.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Container for aircraft configuration (maintains position in layout)
        aircraft_config_container = ThemedFrame(panel)
        aircraft_config_container.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))

        # Aircraft counts section (will be hidden when difficulty is enabled)
        counts_section = ThemedFrame(aircraft_config_container)
        counts_section.pack(fill='x')

        # Aircraft counts label with red asterisk (required field)
        counts_label_frame = tk.Frame(counts_section, bg=DarkTheme.BG_PRIMARY)
        counts_label_frame.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            counts_label_frame,
            text="Aircraft Counts",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        ).pack(side='left')

        tk.Label(
            counts_label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        # Grid for inputs
        grid = ThemedFrame(counts_section)
        grid.pack(fill='x')

        # Enroute transient
        enroute_label_frame = tk.Frame(grid, bg=DarkTheme.BG_PRIMARY)
        enroute_label_frame.grid(row=0, column=0, sticky='w',
                                 padx=(0, DarkTheme.PADDING_SMALL), pady=DarkTheme.PADDING_SMALL)
        ThemedLabel(enroute_label_frame, text="Enroute (Transient):").pack(side='left')

        enroute_entry = ThemedEntry(grid, placeholder="e.g., 5", validate_type="integer")
        enroute_entry.grid(row=0, column=1, sticky='ew', pady=DarkTheme.PADDING_SMALL)
        self.inputs['num_enroute'] = enroute_entry

        # Arrivals
        arrivals_label_frame = tk.Frame(grid, bg=DarkTheme.BG_PRIMARY)
        arrivals_label_frame.grid(row=1, column=0, sticky='w',
                                  padx=(0, DarkTheme.PADDING_SMALL), pady=DarkTheme.PADDING_SMALL)
        ThemedLabel(arrivals_label_frame, text="Arrivals:").pack(side='left')

        arrivals_entry = ThemedEntry(grid, placeholder="e.g., 3", validate_type="integer")
        arrivals_entry.grid(row=1, column=1, sticky='ew', pady=DarkTheme.PADDING_SMALL)
        self.inputs['num_arrivals_enroute'] = arrivals_entry

        # Departures
        departures_label_frame = tk.Frame(grid, bg=DarkTheme.BG_PRIMARY)
        departures_label_frame.grid(row=2, column=0, sticky='w',
                                    padx=(0, DarkTheme.PADDING_SMALL), pady=DarkTheme.PADDING_SMALL)
        ThemedLabel(departures_label_frame, text="Departures:").pack(side='left')

        departures_entry = ThemedEntry(grid, placeholder="e.g., 3", validate_type="integer")
        departures_entry.grid(row=2, column=1, sticky='ew', pady=DarkTheme.PADDING_SMALL)
        self.inputs['num_departures_enroute'] = departures_entry

        # Note about at least one required
        note_label = ThemedLabel(
            counts_section,
            text="Note: At least one aircraft category must have a count greater than 0",
            fg=DarkTheme.FG_SECONDARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        note_label.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        grid.columnconfigure(1, weight=1)

        # Difficulty levels section (collapsible) - in same container
        difficulty_divider = tk.Frame(aircraft_config_container, bg=DarkTheme.DIVIDER, height=1)
        difficulty_divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        difficulty_section = ThemedFrame(aircraft_config_container)
        difficulty_section.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, 0))

        # Collapsible header with checkbox
        header_frame = ThemedFrame(difficulty_section)
        header_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        enable_difficulty_var = tk.BooleanVar(value=False)

        # Toggle indicator
        toggle_label = ThemedLabel(
            header_frame,
            text="▶",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
        )
        toggle_label.pack(side='left', padx=(0, DarkTheme.PADDING_SMALL))

        # Checkbox
        enable_checkbox = tk.Checkbutton(
            header_frame,
            text="Configure by difficulty level (Easy/Medium/Hard)",
            variable=enable_difficulty_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2',
            command=lambda: self._toggle_enroute_difficulty_inputs(
                enable_difficulty_var.get(), difficulty_content_frame, toggle_label,
                counts_section, difficulty_divider
            )
        )
        enable_checkbox.pack(anchor='w')
        self.inputs['enable_difficulty_enroute'] = enable_difficulty_var

        # Hint text (below checkbox)
        hint = ThemedLabel(
            difficulty_section,
            text="(splits aircraft counts into difficulty tiers per category)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0), pady=(0, DarkTheme.PADDING_SMALL))

        # Container for difficulty inputs (hidden by default)
        difficulty_content_frame = ThemedFrame(difficulty_section)
        difficulty_content_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        difficulty_content_frame.pack_forget()  # Hide initially

        # Helper to create difficulty section for a category
        def create_category_difficulty(parent, category_name, key_prefix):
            section = ThemedFrame(parent)
            section.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0), padx=(DarkTheme.PADDING_LARGE, 0))

            section_title = ThemedLabel(
                section,
                text=category_name,
                fg=DarkTheme.FG_SECONDARY,
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
            )
            section_title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

            grid = ThemedFrame(section)
            grid.pack(fill='x')

            # Easy
            ThemedLabel(grid, text="Easy:", fg=DarkTheme.SUCCESS).grid(
                row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            easy_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            easy_entry.grid(row=0, column=1, sticky='ew', padx=(0, DarkTheme.PADDING_MEDIUM))
            self.inputs[f'{key_prefix}_easy'] = easy_entry

            # Medium
            ThemedLabel(grid, text="Medium:", fg=DarkTheme.WARNING).grid(
                row=0, column=2, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            medium_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            medium_entry.grid(row=0, column=3, sticky='ew', padx=(0, DarkTheme.PADDING_MEDIUM))
            self.inputs[f'{key_prefix}_medium'] = medium_entry

            # Hard
            ThemedLabel(grid, text="Hard:", fg=DarkTheme.ERROR).grid(
                row=0, column=4, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            hard_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            hard_entry.grid(row=0, column=5, sticky='ew')
            self.inputs[f'{key_prefix}_hard'] = hard_entry

            grid.columnconfigure(1, weight=1)
            grid.columnconfigure(3, weight=1)
            grid.columnconfigure(5, weight=1)

        # Create difficulty sections for each category
        create_category_difficulty(difficulty_content_frame, "Enroute (Transient)", "difficulty_enroute")
        create_category_difficulty(difficulty_content_frame, "Arrivals", "difficulty_arrivals")
        create_category_difficulty(difficulty_content_frame, "Departures", "difficulty_departures")

    def _build_enroute_airports_panel(self, panel):
        """Build Airports & Routes configuration panel for enroute scenarios"""
        title = ThemedLabel(
            panel,
            text="Airports & Routes Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Get ARTCC airport groups from config
        artcc_id = getattr(self.app_controller, 'artcc_id', 'Unknown')
        import json
        from pathlib import Path
        try:
            config_path = Path('config.json')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    airport_groups = config.get('artcc_airport_groups', {})
                    artcc_airport_groups = airport_groups.get(artcc_id, {})
            else:
                artcc_airport_groups = {}
        except:
            artcc_airport_groups = {}

        # Combined airports section (applies to both arrivals and departures)
        airports_section = ThemedFrame(panel)
        airports_section.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))

        # Airports label with red asterisk (required field)
        airports_label_frame = tk.Frame(airports_section, bg=DarkTheme.BG_PRIMARY)
        airports_label_frame.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            airports_label_frame,
            text="Airports Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        ).pack(side='left')

        tk.Label(
            airports_label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        airports_info = ThemedLabel(
            airports_section,
            text="Select airport configuration (applies to both arrivals and departures)",
            fg=DarkTheme.FG_SECONDARY
        )
        airports_info.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        if artcc_airport_groups:
            airports_dropdown_var = tk.StringVar(value="")
            airports_dropdown = ttk.Combobox(
                airports_section,
                textvariable=airports_dropdown_var,
                state='readonly',
                style='Dark.TCombobox',
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL)
            )
            # Format: "Group Name: ICAO,ICAO,ICAO"
            airports_values = [f"{name}: {airports}" for name, airports in artcc_airport_groups.items()]
            airports_dropdown['values'] = airports_values
            airports_dropdown.pack(fill='x', pady=DarkTheme.PADDING_SMALL)
            # Store in both keys for backward compatibility with validation logic
            self.inputs['airports_group'] = airports_dropdown_var
            self.inputs['arrival_airports_group'] = airports_dropdown_var
            self.inputs['departure_airports_group'] = airports_dropdown_var
        else:
            # Manual entry fallback
            airports_entry = ThemedEntry(airports_section, placeholder="e.g., KPHX,KTUS,KABQ")
            airports_entry.pack(fill='x', pady=DarkTheme.PADDING_SMALL)
            # Store in both keys for backward compatibility
            self.inputs['airports_manual'] = airports_entry
            self.inputs['arrival_airports_manual'] = airports_entry
            self.inputs['departure_airports_manual'] = airports_entry

    def _build_custom_commands_panel(self, panel):
        """Build Custom Commands panel (reuses preset commands section)"""
        title = ThemedLabel(
            panel,
            text="Custom Commands",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        info = ThemedLabel(
            panel,
            text="Configure automatic command assignments for aircraft based on conditions",
            fg=DarkTheme.FG_SECONDARY
        )
        info.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Reuse the preset commands section
        self._add_preset_commands_section(panel)

    # Helper methods for building sections

    def _add_divider(self, parent):
        """Add a subtle divider line"""
        divider = tk.Frame(parent, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

    def _add_difficulty_section(self, parent):
        """Add difficulty level configuration section with separate arrivals/departures"""
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
        enable_checkbox.pack(anchor='w')
        self.inputs['enable_difficulty'] = enable_var

        # Hint text (below checkbox)
        hint = ThemedLabel(
            section,
            text="(splits aircraft counts into difficulty tiers per category)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0), pady=(0, DarkTheme.PADDING_SMALL))

        # Container for difficulty inputs (hidden by default)
        difficulty_frame = ThemedFrame(section)
        difficulty_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
        difficulty_frame.pack_forget()  # Hide initially

        # Helper to create difficulty section for a category
        def create_category_difficulty(parent, category_name, key_prefix):
            section = ThemedFrame(parent)
            section.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0), padx=(DarkTheme.PADDING_LARGE, 0))

            section_title = ThemedLabel(
                section,
                text=category_name,
                fg=DarkTheme.FG_SECONDARY,
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)
            )
            section_title.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

            grid = ThemedFrame(section)
            grid.pack(fill='x')

            # Easy
            ThemedLabel(grid, text="Easy:", fg=DarkTheme.SUCCESS).grid(
                row=0, column=0, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            easy_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            easy_entry.grid(row=0, column=1, sticky='ew', padx=(0, DarkTheme.PADDING_MEDIUM))
            self.inputs[f'{key_prefix}_easy'] = easy_entry

            # Medium
            ThemedLabel(grid, text="Medium:", fg=DarkTheme.WARNING).grid(
                row=0, column=2, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            medium_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            medium_entry.grid(row=0, column=3, sticky='ew', padx=(0, DarkTheme.PADDING_MEDIUM))
            self.inputs[f'{key_prefix}_medium'] = medium_entry

            # Hard
            ThemedLabel(grid, text="Hard:", fg=DarkTheme.ERROR).grid(
                row=0, column=4, sticky='w', padx=(0, DarkTheme.PADDING_SMALL)
            )
            hard_entry = ThemedEntry(grid, placeholder="0", validate_type="integer")
            hard_entry.grid(row=0, column=5, sticky='ew')
            self.inputs[f'{key_prefix}_hard'] = hard_entry

            grid.columnconfigure(1, weight=1)
            grid.columnconfigure(3, weight=1)
            grid.columnconfigure(5, weight=1)

        # Create difficulty sections for each category
        create_category_difficulty(difficulty_frame, "Departures", "difficulty_departures")
        create_category_difficulty(difficulty_frame, "Arrivals", "difficulty_arrivals")

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
            # Create label with red asterisk for required field
            dep_label_frame = tk.Frame(grid_frame, bg=DarkTheme.BG_PRIMARY)
            dep_label_frame.grid(row=0, column=col, sticky='w',
                                padx=(0, DarkTheme.PADDING_SMALL))

            ThemedLabel(dep_label_frame, text="Departures:").pack(side='left')
            tk.Label(
                dep_label_frame,
                text=" *",
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
                fg='#FF4444',
                bg=DarkTheme.BG_PRIMARY
            ).pack(side='left')

            dep_entry = ThemedEntry(grid_frame, placeholder="e.g., 10", validate_type="integer")
            dep_entry.grid(row=0, column=col+1, sticky='ew',
                          padx=(0, DarkTheme.PADDING_LARGE))
            self.inputs['num_departures'] = dep_entry

            grid_frame.columnconfigure(col+1, weight=1)
            col += 2

        # Arrivals (if applicable)
        if has_arrivals:
            # Create label with red asterisk for required field
            arr_label_frame = tk.Frame(grid_frame, bg=DarkTheme.BG_PRIMARY)
            arr_label_frame.grid(row=0, column=col, sticky='w',
                                padx=(0, DarkTheme.PADDING_SMALL))

            ThemedLabel(arr_label_frame, text="Arrivals:").pack(side='left')
            tk.Label(
                arr_label_frame,
                text=" *",
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
                fg='#FF4444',
                bg=DarkTheme.BG_PRIMARY
            ).pack(side='left')

            arr_entry = ThemedEntry(grid_frame, placeholder="e.g., 5", validate_type="integer")
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
            text="Additional Separation (NM):",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        )
        label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        entry = ThemedEntry(section, placeholder="0", validate_type="integer")
        entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['separation_range'] = entry

        hint = ThemedLabel(
            section,
            text="Additional NM to add to minimum separation for each aircraft (e.g., 2 adds 2 NM to the minimum)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
        )
        total_hint.pack(anchor='w', padx=(DarkTheme.PADDING_XLARGE, 0))

        # Input fields (shown/hidden based on mode)
        inputs_grid = ThemedFrame(self.spawn_delay_frame)
        inputs_grid.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_SMALL))

        # Incremental mode input
        self.incremental_input_frame = ThemedFrame(inputs_grid)
        self.incremental_input_frame.pack(fill='x')

        # Create label with red asterisk for required field
        incremental_label_frame = tk.Frame(self.incremental_input_frame, bg=DarkTheme.BG_PRIMARY)
        incremental_label_frame.grid(row=0, column=0, sticky='w',
                                    padx=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            incremental_label_frame,
            text="Delay between aircraft (min):"
        ).pack(side='left')

        tk.Label(
            incremental_label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        incremental_entry = ThemedEntry(self.incremental_input_frame,
                                       placeholder="2-5 or 3",
                                       validate_type="range")
        incremental_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['incremental_delay_value'] = incremental_entry

        incremental_input_hint = ThemedLabel(
            self.incremental_input_frame,
            text="(range or fixed value in minutes)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=300
        )
        incremental_input_hint.grid(row=0, column=2, sticky='w',
                                   padx=(DarkTheme.PADDING_SMALL, 0))

        self.incremental_input_frame.columnconfigure(1, weight=1)

        # Total mode input
        self.total_input_frame = ThemedFrame(inputs_grid)
        self.total_input_frame.pack(fill='x')
        self.total_input_frame.pack_forget()  # Hide initially

        # Create label with red asterisk for required field
        total_label_frame = tk.Frame(self.total_input_frame, bg=DarkTheme.BG_PRIMARY)
        total_label_frame.grid(row=0, column=0, sticky='w',
                              padx=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            total_label_frame,
            text="Total session length (min):"
        ).pack(side='left')

        tk.Label(
            total_label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        total_entry = ThemedEntry(self.total_input_frame, placeholder="30", validate_type="integer")
        total_entry.grid(row=0, column=1, sticky='ew')
        self.inputs['total_session_minutes'] = total_entry

        total_input_hint = ThemedLabel(
            self.total_input_frame,
            text="(desired training session length)",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=300
        )
        total_input_hint.grid(row=0, column=2, sticky='w',
                             padx=(DarkTheme.PADDING_SMALL, 0))

        self.total_input_frame.columnconfigure(1, weight=1)

    def _add_tracon_arrivals_section(self, parent):
        """Add TRACON arrivals specific configuration"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        # STAR Waypoints - Required field with red asterisk
        label_frame = tk.Frame(section, bg=DarkTheme.BG_PRIMARY)
        label_frame.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        ThemedLabel(
            label_frame,
            text="STAR Waypoints:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')
        ).pack(side='left')

        tk.Label(
            label_frame,
            text=" *",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            fg='#FF4444',
            bg=DarkTheme.BG_PRIMARY
        ).pack(side='left')

        waypoints_entry = ThemedEntry(section,
                                     placeholder="e.g., EAGUL.JESSE3, PINNG.PINNG1, etc.",
                                     validate_type="waypoint")
        waypoints_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['arrival_waypoints'] = waypoints_entry

        waypoint_hint = ThemedLabel(
            section,
            text="Format: WAYPOINT.STAR. The aircraft will spawn 3NM prior to that fix along the lateral course of the arrival. The generation will only function appropriately if you pick a waypoint prior to any runway-specific splits.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=550
        )
        waypoint_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM))

        # Use CIFP Speeds checkbox
        use_cifp_speeds_var = tk.BooleanVar(value=True)

        use_cifp_speeds_checkbox = tk.Checkbutton(
            section,
            text="Use CIFP Speed Restrictions",
            variable=use_cifp_speeds_var,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            selectcolor=DarkTheme.BG_TERTIARY,
            activebackground=DarkTheme.BG_PRIMARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            cursor='hand2'
        )
        use_cifp_speeds_checkbox.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['use_cifp_speeds'] = use_cifp_speeds_var

        # Hint for CIFP speeds
        cifp_speed_hint = ThemedLabel(
            section,
            text="When enabled, arrival aircraft will spawn at speeds matching CIFP parsed speed restrictions for the arrival procedure. Falls back to altitude-based calculation if no restriction exists.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=550
        )
        cifp_speed_hint.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM))

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
            text="Dynamic Tower Arrivals",
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
            text="Generate inbound VFR GA aircraft",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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
            placeholder="e.g., 5",
            validate_type="integer"
        )
        num_vfr_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        self.inputs['num_vfr'] = num_vfr_entry

        num_vfr_hint = ThemedLabel(
            self.vfr_frame,
            text="Number of VFR GA aircraft to generate",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=600
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

    def _toggle_enroute_difficulty_inputs(self, enabled, difficulty_frame, toggle_label, counts_section, difficulty_divider):
        """Toggle between aircraft counts and difficulty distribution for enroute scenarios"""
        if enabled:
            # Show difficulty inputs
            difficulty_frame.pack(fill='x', pady=(DarkTheme.PADDING_SMALL, 0))
            toggle_label.config(text="▼")
            # Hide aircraft counts
            counts_section.pack_forget()
        else:
            # Hide difficulty inputs
            difficulty_frame.pack_forget()
            toggle_label.config(text="▶")
            # Show aircraft counts back in correct position (before the divider)
            counts_section.pack(fill='x', before=difficulty_divider)

        # Update scroll region to show new content
        self.after(50, self._update_scroll_region)

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

        # Reset preset command rules for new scenario
        self.preset_command_rules = []

        # Rebuild sidebar based on scenario type
        self._rebuild_sidebar_for_scenario(scenario_type)

        # Select first category by default
        if self.sidebar.items and self.category_order:
            first_item = self.sidebar.items[0]
            first_item.select()
            self.sidebar.selected_item = first_item
            # Reset to first category
            self.current_category_index = 0
            # Trigger category selection with first category from order
            first_category_id = self.category_order[0]
            self.on_category_select(first_category_id)

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

        # Include preset command rules
        values['preset_command_rules'] = self.preset_command_rules

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

                # Deselect previous item and select the previous sidebar item
                if self.sidebar.selected_item:
                    self.sidebar.selected_item.deselect()

                for item in self.sidebar.items:
                    if item.category_id == prev_category:
                        item.select()
                        self.sidebar.selected_item = item
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

                # Deselect previous item and select the next sidebar item
                if self.sidebar.selected_item:
                    self.sidebar.selected_item.deselect()

                for item in self.sidebar.items:
                    if item.category_id == next_category:
                        item.select()
                        self.sidebar.selected_item = item
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

        # Validate runways - required for all scenarios EXCEPT enroute
        if not self.is_enroute_scenario:
            active_runways = config.get('active_runways', '').strip()
            if not active_runways:
                errors.append("Active runways are required (needed for CIFP SID filtering and arrival procedures)")

        # Check if difficulty levels are enabled (different for enroute vs other scenarios)
        if self.is_enroute_scenario:
            difficulty_enabled = config.get('enable_difficulty_enroute', False)
        else:
            difficulty_enabled = config.get('enable_difficulty', False)

        if difficulty_enabled:
            if self.is_enroute_scenario:
                # Validate enroute difficulty counts
                try:
                    enroute_easy = int(config.get('difficulty_enroute_easy', '0') or '0')
                    enroute_medium = int(config.get('difficulty_enroute_medium', '0') or '0')
                    enroute_hard = int(config.get('difficulty_enroute_hard', '0') or '0')

                    arrivals_easy = int(config.get('difficulty_arrivals_easy', '0') or '0')
                    arrivals_medium = int(config.get('difficulty_arrivals_medium', '0') or '0')
                    arrivals_hard = int(config.get('difficulty_arrivals_hard', '0') or '0')

                    departures_easy = int(config.get('difficulty_departures_easy', '0') or '0')
                    departures_medium = int(config.get('difficulty_departures_medium', '0') or '0')
                    departures_hard = int(config.get('difficulty_departures_hard', '0') or '0')

                    if any(x < 0 for x in [enroute_easy, enroute_medium, enroute_hard,
                                           arrivals_easy, arrivals_medium, arrivals_hard,
                                           departures_easy, departures_medium, departures_hard]):
                        errors.append("Difficulty counts cannot be negative")

                    total_aircraft = (enroute_easy + enroute_medium + enroute_hard +
                                    arrivals_easy + arrivals_medium + arrivals_hard +
                                    departures_easy + departures_medium + departures_hard)
                    if total_aircraft == 0:
                        errors.append("Must specify at least one aircraft in difficulty levels")
                except ValueError:
                    errors.append("Difficulty counts must be valid numbers")
            else:
                # Validate airport scenario difficulty counts (separate for departures/arrivals)
                try:
                    # Check departures difficulty
                    dep_easy = int(config.get('difficulty_departures_easy', '0') or '0')
                    dep_medium = int(config.get('difficulty_departures_medium', '0') or '0')
                    dep_hard = int(config.get('difficulty_departures_hard', '0') or '0')

                    # Check arrivals difficulty
                    arr_easy = int(config.get('difficulty_arrivals_easy', '0') or '0')
                    arr_medium = int(config.get('difficulty_arrivals_medium', '0') or '0')
                    arr_hard = int(config.get('difficulty_arrivals_hard', '0') or '0')

                    if any(x < 0 for x in [dep_easy, dep_medium, dep_hard, arr_easy, arr_medium, arr_hard]):
                        errors.append("Difficulty counts cannot be negative")

                    total_aircraft = dep_easy + dep_medium + dep_hard + arr_easy + arr_medium + arr_hard
                    if total_aircraft == 0:
                        errors.append("Must specify at least one aircraft across all difficulty levels and categories")
                except ValueError:
                    errors.append("Difficulty counts must be valid numbers")
        else:
            if self.is_enroute_scenario:
                # Validate enroute manual aircraft counts
                num_enroute = config.get('num_enroute', '')
                num_arrivals = config.get('num_arrivals_enroute', '')
                num_departures = config.get('num_departures_enroute', '')

                try:
                    num_en = int(num_enroute) if num_enroute else 0
                    num_arr = int(num_arrivals) if num_arrivals else 0
                    num_dep = int(num_departures) if num_departures else 0

                    if num_en < 0:
                        errors.append("Number of enroute aircraft cannot be negative")
                    if num_arr < 0:
                        errors.append("Number of arrivals cannot be negative")
                    if num_dep < 0:
                        errors.append("Number of departures cannot be negative")
                    if num_en == 0 and num_arr == 0 and num_dep == 0:
                        errors.append("Must generate at least one aircraft (enroute, arrival, or departure)")
                except ValueError:
                    errors.append("Aircraft counts must be valid numbers")
            else:
                # Validate manual aircraft counts for airport scenarios
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

        # Validate additional separation (single integer)
        if config.get('separation_range'):
            try:
                additional_sep = int(config['separation_range'])
                if additional_sep < 0:
                    errors.append("Additional separation cannot be negative")
            except ValueError:
                errors.append("Additional separation must be a valid number")

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

        # Validate TRACON arrival waypoints (required for TRACON arrivals/mixed scenarios)
        if scenario_type in ['tracon_arrivals', 'tracon_mixed']:
            # Check if arrivals are being generated
            num_arrivals = config.get('num_arrivals', '')
            difficulty_enabled = config.get('enable_difficulty', False)

            has_arrivals = False
            if difficulty_enabled:
                try:
                    # Check arrivals difficulty counts
                    arr_easy = int(config.get('difficulty_arrivals_easy', '0') or '0')
                    arr_medium = int(config.get('difficulty_arrivals_medium', '0') or '0')
                    arr_hard = int(config.get('difficulty_arrivals_hard', '0') or '0')
                    has_arrivals = (arr_easy + arr_medium + arr_hard) > 0
                except ValueError:
                    pass
            else:
                try:
                    num_arr = int(num_arrivals) if num_arrivals else 0
                    has_arrivals = num_arr > 0
                except ValueError:
                    pass

            # If generating arrivals, waypoints are required
            if has_arrivals:
                arrival_waypoints = config.get('arrival_waypoints', '').strip()
                if not arrival_waypoints:
                    errors.append("STAR Waypoints are required for TRACON scenarios with arrivals (e.g., EAGUL.EAGUL6, PINNG.PINNG1)")

        return errors

    # ==================== PRESET COMMANDS SECTION ====================

    def _add_preset_commands_section(self, parent):
        """Add preset commands configuration section"""
        section = ThemedFrame(parent)
        section.pack(fill='x', pady=(0, DarkTheme.PADDING_LARGE))

        # Section header
        header = ThemedLabel(
            section,
            text="Preset Commands (vNAS)",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        header.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Description
        desc = ThemedLabel(
            section,
            text="Apply vNAS commands to groups of aircraft. Commands are applied cumulatively (aircraft can receive multiple commands).",
            fg=DarkTheme.FG_SECONDARY,
            wraplength=600,
            justify='left'
        )
        desc.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM), fill='x')

        # List frame with border
        list_frame = tk.Frame(
            section,
            bg=DarkTheme.BG_SECONDARY,
            relief='solid',
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=DarkTheme.BORDER,
            highlightcolor=DarkTheme.BORDER
        )
        list_frame.pack(fill='both', expand=True, pady=(0, DarkTheme.PADDING_SMALL))

        # Listbox with scrollbar
        scrollbar = tk.Scrollbar(list_frame, bg=DarkTheme.BG_SECONDARY)
        scrollbar.pack(side='right', fill='y')

        self.preset_commands_listbox = tk.Listbox(
            list_frame,
            bg=DarkTheme.BG_SECONDARY,
            fg=DarkTheme.FG_PRIMARY,
            selectbackground=DarkTheme.ACCENT_PRIMARY,
            selectforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            activestyle='none',
            yscrollcommand=scrollbar.set,
            height=8
        )
        self.preset_commands_listbox.pack(side='left', fill='both', expand=True, padx=8, pady=8)
        scrollbar.config(command=self.preset_commands_listbox.yview)

        # Buttons frame
        buttons_frame = ThemedFrame(section)
        buttons_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        add_btn = ThemedButton(
            buttons_frame,
            text="Add Command",
            command=self._add_preset_command,
            primary=True
        )
        add_btn.pack(side='left', padx=(0, DarkTheme.PADDING_SMALL))

        edit_btn = ThemedButton(
            buttons_frame,
            text="Edit",
            command=self._edit_preset_command,
            primary=False
        )
        edit_btn.pack(side='left', padx=(0, DarkTheme.PADDING_SMALL))

        remove_btn = ThemedButton(
            buttons_frame,
            text="Remove",
            command=self._remove_preset_command,
            primary=False
        )
        remove_btn.pack(side='left')

        # Info about variables
        var_info = ThemedLabel(
            section,
            text="Available Variables: $aid, $type, $operator, $gate, $departure, $arrival, $altitude, $heading, $speed, $procedure, and more. Click 'Add Command' to see full list. Missing values show as 'N/A'.",
            fg=DarkTheme.FG_DISABLED,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            wraplength=550,
            justify='left'
        )
        var_info.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0), fill='x')

    def _refresh_preset_commands_list(self):
        """Refresh the preset commands listbox display"""
        self.preset_commands_listbox.delete(0, tk.END)

        group_type_labels = {
            "all": "All Aircraft",
            "airline": "Airline",
            "destination": "Destination",
            "origin": "Origin",
            "aircraft_type": "Aircraft Type",
            "random": "Random",
            "departures": "Departures",
            "arrivals": "Arrivals",
            "parking": "Parking Spot",
            "sid": "SID",
            "star": "STAR"
        }

        for rule in self.preset_command_rules:
            group_label = group_type_labels.get(rule.group_type, rule.group_type)

            if rule.group_value:
                display_text = f"[{group_label}: {rule.group_value}] → {rule.command_template}"
            else:
                display_text = f"[{group_label}] → {rule.command_template}"

            self.preset_commands_listbox.insert(tk.END, display_text)

    def _add_preset_command(self):
        """Open dialog to add a new preset command"""
        self._open_preset_command_dialog()

    def _edit_preset_command(self):
        """Open dialog to edit the selected preset command"""
        selection = self.preset_commands_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a command to edit")
            return

        index = selection[0]
        rule = self.preset_command_rules[index]
        self._open_preset_command_dialog(rule, index)

    def _remove_preset_command(self):
        """Remove the selected preset command"""
        selection = self.preset_commands_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a command to remove")
            return

        index = selection[0]
        del self.preset_command_rules[index]
        self._refresh_preset_commands_list()

    def _open_preset_command_dialog(self, rule=None, edit_index=None):
        """
        Open dialog to add or edit a preset command rule

        Args:
            rule: PresetCommandRule to edit (None for new)
            edit_index: Index of rule being edited (None for new)
        """
        dialog = tk.Toplevel(self)
        dialog.title("Add Preset Command" if rule is None else "Edit Preset Command")
        dialog.configure(bg=DarkTheme.BG_PRIMARY)
        dialog.geometry("650x650")
        dialog.resizable(True, True)

        # Make dialog modal
        dialog.transient(self)
        dialog.grab_set()

        # Content frame
        content = ThemedFrame(dialog)
        content.pack(fill='both', expand=True, padx=DarkTheme.PADDING_LARGE, pady=DarkTheme.PADDING_LARGE)

        # Title
        title = ThemedLabel(
            content,
            text="Configure Preset Command",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold')
        )
        title.pack(anchor='w', pady=(0, DarkTheme.PADDING_LARGE))

        # Group Type
        group_type_label = ThemedLabel(content, text="Apply to:")
        group_type_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        group_type_var = tk.StringVar()

        group_types = [
            ("All Aircraft", "all"),
            ("Airline/Operator", "airline"),
            ("Destination Airport", "destination"),
            ("Origin Airport", "origin"),
            ("Aircraft Type", "aircraft_type"),
            ("Parking Spot/Gate", "parking"),
            ("SID (Departure Procedure)", "sid"),
            ("STAR (Arrival Procedure)", "star"),
            ("Random Count", "random"),
            ("All Departures", "departures"),
            ("All Arrivals", "arrivals")
        ]

        group_frame = ThemedFrame(content)
        group_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))

        # Style the combobox
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Preset.TCombobox',
            fieldbackground=DarkTheme.BG_SECONDARY,
            background=DarkTheme.BG_SECONDARY,
            foreground=DarkTheme.FG_PRIMARY,
            arrowcolor=DarkTheme.FG_PRIMARY,
            borderwidth=1,
            relief='solid'
        )
        style.map('Preset.TCombobox',
                  fieldbackground=[('readonly', DarkTheme.BG_SECONDARY)],
                  selectbackground=[('readonly', DarkTheme.BG_SECONDARY)],
                  selectforeground=[('readonly', DarkTheme.FG_PRIMARY)])

        group_type_combo = ttk.Combobox(
            group_frame,
            textvariable=group_type_var,
            values=[label for label, _ in group_types],
            state='readonly',
            style='Preset.TCombobox',
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            width=30
        )
        group_type_combo.pack(fill='x')

        # Map display names to values
        type_map = {label: value for label, value in group_types}
        reverse_type_map = {value: label for label, value in group_types}

        # Set initial selection
        if rule:
            group_type_combo.set(reverse_type_map.get(rule.group_type, "All Aircraft"))
        else:
            group_type_combo.set("All Aircraft")

        # Group Value (conditional) - frame to hold label and entry
        group_value_frame = ThemedFrame(content)

        group_value_label = ThemedLabel(group_value_frame, text="Variable Group Condition:")
        group_value_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Create entry with dynamic placeholder based on selected type
        group_value_entry = ThemedEntry(group_value_frame, placeholder="Enter a value which corresponds to the selected variable type.")
        group_value_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_MEDIUM))

        def update_placeholder(*_args):
            """Update placeholder based on group type selection"""
            selected_label = group_type_var.get()
            selected_value = type_map.get(selected_label, "all")

            placeholders = {
                "airline": "e.g., UAL, AAL, DAL",
                "destination": "e.g., KLAX, KORD",
                "origin": "e.g., KDEN, KATL",
                "aircraft_type": "e.g., B738, A320",
                "parking": "e.g., B3, A1-A10, C#",
                "sid": "e.g., BAYLR6, SLEEK2 (exact format as in route)",
                "star": "e.g., EAGUL6, NIIXX4 (exact format as in route)",
                "random": "e.g., 5 (number of aircraft)"
            }

            placeholder = placeholders.get(selected_value, "Enter a value which corresponds to the selected variable type.")
            group_value_entry.entry.config(state='normal')
            group_value_entry.entry.delete(0, 'end')
            group_value_entry.placeholder = placeholder
            if not group_value_entry.get_value():
                group_value_entry.entry.config(state='normal', fg=DarkTheme.FG_SECONDARY)
                group_value_entry.entry.insert(0, placeholder)

        if rule and rule.group_value:
            group_value_entry.set_value(rule.group_value)

        # Command Template - declare this BEFORE the visibility function so we can pack group_value_frame before it
        command_label = ThemedLabel(content, text="Command Template:")
        command_entry = ThemedEntry(content, placeholder="e.g., SAYF THIS IS $aid OUT OF $altitude.")

        # Now pack the command template widgets FIRST
        command_label.pack(anchor='w', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))
        command_entry.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        def update_group_value_visibility(*args):
            """Show/hide group value field based on group type"""
            selected_label = group_type_var.get()
            selected_value = type_map.get(selected_label, "all")

            if selected_value in ["airline", "destination", "origin", "aircraft_type", "parking", "random", "sid", "star"]:
                # Pack before command_label to maintain proper order (command_label is already packed now)
                group_value_frame.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, 0), before=command_label)
            else:
                group_value_frame.pack_forget()

        # Bind both functions to combobox selection
        def on_combobox_change(event):
            update_group_value_visibility(event)
            update_placeholder(event)

        group_type_combo.bind('<<ComboboxSelected>>', on_combobox_change)
        update_group_value_visibility()  # Initial call - command_label is now packed so this works

        if rule:
            command_entry.set_value(rule.command_template)

        # Available variables info
        vars_label = ThemedLabel(
            content,
            text="Available Variables:",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL, 'bold'),
            fg=DarkTheme.FG_SECONDARY
        )
        vars_label.pack(anchor='w', pady=(DarkTheme.PADDING_MEDIUM, DarkTheme.PADDING_SMALL))

        # Variables list (read-only, no scrollbar)
        vars_frame = tk.Frame(
            content,
            bg=DarkTheme.BG_SECONDARY,
            relief='solid',
            borderwidth=1
        )
        vars_frame.pack(fill='both', expand=True, pady=(0, DarkTheme.PADDING_MEDIUM))

        vars_text = tk.Text(
            vars_frame,
            bg=DarkTheme.BG_SECONDARY,
            fg=DarkTheme.FG_SECONDARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            height=8,
            wrap='word'
        )
        vars_text.pack(fill='both', expand=True, padx=8, pady=8)

        # Populate variables with descriptions in a nicely formatted table
        all_vars = get_available_variables()

        # Build formatted output
        output_lines = []
        for var in all_vars:
            description = get_variable_description(var)
            # Format: $variable - Description
            output_lines.append(f"{var:<20} {description}")

        vars_text.insert('1.0', "\n".join(output_lines))
        vars_text.config(state='disabled')

        # Buttons
        button_frame = ThemedFrame(content)
        button_frame.pack(fill='x', pady=(DarkTheme.PADDING_MEDIUM, 0))

        def on_save():
            """Save the preset command rule"""
            selected_label = group_type_var.get()
            selected_type = type_map.get(selected_label, "all")
            value = group_value_entry.get_value().strip() if selected_type in ["airline", "destination", "origin", "aircraft_type", "parking", "random", "sid", "star"] else None
            command = command_entry.get_value().strip()

            # Validation
            if not command:
                messagebox.showerror("Validation Error", "Command template is required")
                return

            if selected_type in ["airline", "destination", "origin", "aircraft_type", "parking", "random", "sid", "star"] and not value:
                messagebox.showerror("Validation Error", f"Value is required for {selected_label}")
                return

            # Create or update rule
            try:
                new_rule = PresetCommandRule(
                    group_type=selected_type,
                    group_value=value,
                    command_template=command
                )

                if edit_index is not None:
                    # Update existing rule
                    self.preset_command_rules[edit_index] = new_rule
                else:
                    # Add new rule
                    self.preset_command_rules.append(new_rule)

                self._refresh_preset_commands_list()
                dialog.destroy()

            except ValueError as e:
                messagebox.showerror("Validation Error", str(e))

        def on_cancel():
            dialog.destroy()

        cancel_btn = ThemedButton(button_frame, text="Cancel", command=on_cancel, primary=False)
        cancel_btn.pack(side='right', padx=(DarkTheme.PADDING_SMALL, 0))

        save_btn = ThemedButton(button_frame, text="Save", command=on_save, primary=True)
        save_btn.pack(side='right', padx=(0, DarkTheme.PADDING_SMALL))
