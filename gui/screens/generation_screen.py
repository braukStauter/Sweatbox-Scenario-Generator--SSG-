"""
Generation progress and completion screen
"""
import tkinter as tk
import os
import subprocess
from pathlib import Path
from gui.theme import DarkTheme
from gui.widgets import ThemedLabel, ThemedButton, ThemedFrame, ProgressIndicator, Footer


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

        # Store the output filename
        self.output_filename = None

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
        self.new_scenario_button.pack_forget()  # Hide initially

        self.exit_button = ThemedButton(
            footer,
            text="Exit",
            command=self.on_exit,
            primary=False
        )
        self.exit_button.pack(side='left')
        self.exit_button.pack_forget()  # Hide initially

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

        self.new_scenario_button.pack_forget()
        self.exit_button.pack_forget()

    def show_success(self, aircraft_count, filename):
        """Show success message"""
        self.progress.stop()
        self.progress.pack_forget()

        self.title_label['text'] = "Generation Complete"
        self.subtitle_label['text'] = "Your scenario has been successfully generated!"

        self.result_icon['text'] = "✓"
        self.result_icon['fg'] = DarkTheme.SUCCESS
        self.result_message['text'] = f"Successfully generated {aircraft_count} aircraft"
        self.result_details['text'] = f"Saved to: {filename} (click to open folder)"

        # Store the filename and make it clickable
        self.output_filename = filename
        self.result_details.bind('<Button-1>', self._open_output_folder)
        self.result_details.bind('<Enter>', lambda e: self.result_details.configure(fg=DarkTheme.ACCENT_HOVER))
        self.result_details.bind('<Leave>', lambda e: self.result_details.configure(fg=DarkTheme.ACCENT_PRIMARY))
        self.result_details['fg'] = DarkTheme.ACCENT_PRIMARY  # Make it look clickable

        self.result_frame.pack(expand=True)
        self.new_scenario_button.pack(side='right')
        self.exit_button.pack(side='left')

    def _open_output_folder(self, event=None):
        """Open the folder containing the output file"""
        if self.output_filename:
            try:
                file_path = Path(self.output_filename).absolute()
                folder_path = file_path.parent

                # Open folder based on OS
                if os.name == 'nt':  # Windows
                    os.startfile(folder_path)
                elif os.name == 'posix':  # macOS and Linux
                    subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', folder_path])
            except Exception as e:
                print(f"Error opening folder: {e}")

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
        self.new_scenario_button.pack(side='right')
        self.exit_button.pack(side='left')

    def on_new_scenario(self):
        """Handle new scenario button click"""
        self.app_controller.reset()

    def on_exit(self):
        """Handle exit button click"""
        self.app_controller.quit_app()
