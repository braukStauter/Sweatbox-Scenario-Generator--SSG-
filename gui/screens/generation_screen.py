"""
Generation progress and completion screen
"""
import tkinter as tk
from tkinter import simpledialog, messagebox
import os
import subprocess
import logging
from pathlib import Path
from gui.theme import DarkTheme
from gui.widgets import ThemedLabel, ThemedButton, ThemedFrame, ProgressIndicator, Footer

logger = logging.getLogger(__name__)


class GenerationScreen(tk.Frame):
    """Screen showing generation progress and results"""

    def __init__(self, parent, app_controller):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY)
        self.app_controller = app_controller

        # Header
        header = ThemedFrame(self)
        header.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=(DarkTheme.PADDING_XLARGE, DarkTheme.PADDING_LARGE))

        self.title_label = ThemedLabel(
            header,
            text="Generating Scenario",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_TITLE, 'bold')
        )
        self.title_label.pack(anchor='w')

        self.subtitle_label = ThemedLabel(
            header,
            text="Please wait while your scenario is being generated...",
            fg=DarkTheme.FG_SECONDARY
        )
        self.subtitle_label.pack(anchor='w', pady=(DarkTheme.PADDING_SMALL, 0))

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Content container
        content = ThemedFrame(self)
        content.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_XLARGE)

        # Progress indicator
        self.progress = ProgressIndicator(content)
        self.progress.pack(expand=True)

        # Result message (hidden initially)
        self.result_frame = ThemedFrame(content)
        self.result_frame.pack(expand=True)
        self.result_frame.pack_forget()  # Hide initially

        self.result_icon = ThemedLabel(
            self.result_frame,
            text="✓",
            font=(DarkTheme.FONT_FAMILY, 48),
            fg=DarkTheme.SUCCESS
        )
        self.result_icon.pack(pady=DarkTheme.PADDING_LARGE)

        self.result_message = ThemedLabel(
            self.result_frame,
            text="",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE)
        )
        self.result_message.pack(pady=DarkTheme.PADDING_SMALL)

        self.result_details = ThemedLabel(
            self.result_frame,
            text="",
            fg=DarkTheme.FG_SECONDARY,
            cursor='hand2'
        )
        self.result_details.pack(pady=DarkTheme.PADDING_SMALL)

        # Store the output filename and aircraft list
        self.output_filename = None
        self.aircraft_list = None
        self.airport_icao = None

        # Footer with navigation buttons
        footer = ThemedFrame(self)
        footer.pack(fill='x', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        self.new_scenario_button = ThemedButton(
            footer,
            text="New Scenario",
            command=self.on_new_scenario,
            primary=True
        )
        self.new_scenario_button.pack(side='right')
        self.new_scenario_button.pack_forget()

        self.push_vnas_button = ThemedButton(
            footer,
            text="Push to vNAS",
            command=self.on_push_to_vnas,
            primary=False
        )
        self.push_vnas_button.pack(side='right', padx=(0, DarkTheme.PADDING_MEDIUM))
        self.push_vnas_button.pack_forget()

        self.exit_button = ThemedButton(
            footer,
            text="Exit",
            command=self.on_exit,
            primary=False
        )
        self.exit_button.pack(side='left')
        self.exit_button.pack_forget()

        # Copyright footer
        copyright_footer = Footer(self)
        copyright_footer.pack(side='bottom', fill='x')

    def show_progress(self, message="Generating scenario..."):
        """Show progress indicator"""
        self.title_label['text'] = "Generating Scenario"
        self.subtitle_label['text'] = "Please wait while your scenario is being generated..."

        self.result_frame.pack_forget()
        self.progress.pack(expand=True)
        self.progress.start(message)

        # Hide all buttons during generation
        self.new_scenario_button.pack_forget()
        self.push_vnas_button.pack_forget()
        self.exit_button.pack_forget()

    def show_success(self, aircraft_count, filename, aircraft_list=None, airport_icao=None):
        """Show success message"""
        self.progress.stop()
        self.progress.pack_forget()

        self.title_label['text'] = "Generation Complete"
        self.subtitle_label['text'] = "Your scenario has been successfully generated!"

        self.result_icon['text'] = "✓"
        self.result_icon['fg'] = DarkTheme.SUCCESS
        self.result_message['text'] = f"Successfully generated {aircraft_count} aircraft"
        self.result_details['text'] = f"Saved to: {filename} (click to open folder)"

        self.output_filename = filename
        self.aircraft_list = aircraft_list
        self.airport_icao = airport_icao

        self.result_details.bind('<Button-1>', self._open_output_folder)
        self.result_details.bind('<Enter>', lambda e: self.result_details.configure(fg=DarkTheme.ACCENT_HOVER))
        self.result_details.bind('<Leave>', lambda e: self.result_details.configure(fg=DarkTheme.ACCENT_PRIMARY))
        self.result_details['fg'] = DarkTheme.ACCENT_PRIMARY

        self.result_frame.pack(expand=True)

        # Show buttons in consistent order: Exit (left), Push to vNAS (right-middle), New Scenario (right)
        self.exit_button.pack(side='left')
        self.new_scenario_button.pack(side='right')
        self.push_vnas_button.pack(side='right', padx=(0, DarkTheme.PADDING_MEDIUM))

    def _open_output_folder(self, event=None):
        """Open the folder containing the output file"""
        if self.output_filename:
            try:
                file_path = Path(self.output_filename).absolute()
                folder_path = file_path.parent

                if os.name == 'nt':
                    os.startfile(folder_path)
                elif os.name == 'posix':
                    subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', folder_path])
            except Exception as e:
                logger.error(f"Error opening folder: {e}")

    def show_error(self, error_message):
        """Show error message"""
        self.progress.stop()
        self.progress.pack_forget()

        self.title_label['text'] = "Generation Failed"
        self.subtitle_label['text'] = "An error occurred during generation"

        self.result_icon['text'] = "✗"
        self.result_icon['fg'] = DarkTheme.ERROR
        self.result_message['text'] = "Generation Failed"
        self.result_details['text'] = f"Error: {error_message}"

        self.result_frame.pack(expand=True)

        # Show buttons in consistent order: Exit (left), New Scenario (right)
        # Note: Don't show Push to vNAS on error since generation failed
        self.exit_button.pack(side='left')
        self.new_scenario_button.pack(side='right')

    def on_new_scenario(self):
        """Handle new scenario button click"""
        self.app_controller.reset()

    def on_exit(self):
        """Handle exit button click"""
        self.app_controller.quit_app()

    def on_push_to_vnas(self):
        """Handle push to vNAS button click"""
        if not self.aircraft_list or not self.airport_icao:
            messagebox.showerror(
                "Error",
                "No aircraft data available to push to vNAS."
            )
            return

        try:
            from utils.vnas_converter import VNASConverter
            from utils.vnas_client import VNASClient

            # Show info message about browser login and navigation
            messagebox.showinfo(
                "Browser Login Required",
                "A browser window will open for you to log in to vNAS.\n\n"
                "IMPORTANT STEPS:\n"
                "1. Log in to vNAS Data Admin\n"
                "2. Navigate to the scenario you want to update\n"
                "3. The scenario ID will be extracted automatically\n\n"
                "The browser will close after the push completes.\n\n"
                "Click OK to continue."
            )

            self.push_vnas_button.configure(state='disabled', text="Waiting for login...")
            self.update_idletasks()

            # Initialize client
            client = VNASClient()

            # Create converter and scenario data
            converter = VNASConverter(
                airport_icao=self.airport_icao,
                scenario_name=f"Generated Scenario - {self.airport_icao}"
            )

            scenario_data = converter.create_vnas_scenario(self.aircraft_list)

            # Push scenario (this will trigger browser login and auto-extract scenario ID)
            self.push_vnas_button.configure(state='disabled', text="Pushing...")
            self.update_idletasks()

            success, message = client.push_scenario(scenario_data)

            # Close the browser now that the API call is complete
            client.cleanup()

            self.push_vnas_button.configure(state='normal', text="Push to vNAS")

            if success:
                messagebox.showinfo(
                    "Success",
                    f"{message}\n\nScenario ID: {client.scenario_id}"
                )
            else:
                messagebox.showerror("Error", message)

        except Exception as e:
            # Make sure to clean up browser on error
            try:
                if 'client' in locals():
                    client.cleanup()
            except:
                pass

            self.push_vnas_button.configure(state='normal', text="Push to vNAS")
            logger.error(f"Error pushing to vNAS: {e}", exc_info=True)
            messagebox.showerror(
                "Error",
                f"Failed to push to vNAS:\n\n{str(e)}"
            )
