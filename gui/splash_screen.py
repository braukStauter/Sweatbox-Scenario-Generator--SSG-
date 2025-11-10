"""
Splash screen for application startup
"""
import tkinter as tk
from gui.theme import DarkTheme
from utils.version_manager import VersionManager


class SplashScreen(tk.Toplevel):
    """Splash screen displayed during application startup"""

    def __init__(self, parent):
        super().__init__(parent)

        # Configure window
        self.title("")
        self.overrideredirect(True)  # Remove window decorations

        # Set size and center on screen
        width = 600
        height = 360
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Configure background
        self.configure(bg=DarkTheme.BG_PRIMARY)

        # Create content frame
        content = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)
        content.pack(expand=True, fill='both', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_XLARGE)

        # App title
        title = tk.Label(
            content,
            text="Sweatbox Session Generator",
            font=(DarkTheme.FONT_FAMILY, 24, 'bold'),
            fg=DarkTheme.FG_PRIMARY,
            bg=DarkTheme.BG_PRIMARY,
            wraplength=550  # Wrap text if needed
        )
        title.pack(pady=(DarkTheme.PADDING_LARGE, 2))

        # App subtitle (SSG)
        subtitle = tk.Label(
            content,
            text="(SSG)",
            font=(DarkTheme.FONT_FAMILY, 14),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_PRIMARY
        )
        subtitle.pack(pady=(0, DarkTheme.PADDING_LARGE))

        # Status label
        self.status_label = tk.Label(
            content,
            text="Loading...",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_PRIMARY
        )
        self.status_label.pack(pady=(DarkTheme.PADDING_LARGE, DarkTheme.PADDING_SMALL))

        # Progress bar (canvas-based for better theme control)
        self.progress_canvas = tk.Canvas(
            content,
            width=400,
            height=6,
            bg=DarkTheme.BG_SECONDARY,
            highlightthickness=0,
            bd=0
        )
        self.progress_canvas.pack(pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_MEDIUM))

        # Create progress bar rectangle
        self.progress_bar = self.progress_canvas.create_rectangle(
            0, 0, 0, 6,
            fill=DarkTheme.ACCENT_PRIMARY,
            outline=""
        )
        self.progress_value = 0

        # Copyright label (pack first when using side='bottom')
        copyright_label = tk.Label(
            content,
            text="Developed by Creative Shrimp™ (Ethan M) for ZAB",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg="#404040",  # Very subtle gray
            bg=DarkTheme.BG_PRIMARY
        )
        copyright_label.pack(side='bottom', pady=DarkTheme.PADDING_SMALL)

        # Version label (dynamic) - pack second to appear above copyright
        version_manager = VersionManager()
        version_text = version_manager.get_display_version()

        self.version_label = tk.Label(
            content,
            text=version_text,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            fg=DarkTheme.FG_SECONDARY,  # More visible than disabled
            bg=DarkTheme.BG_PRIMARY
        )
        self.version_label.pack(side='bottom', pady=(DarkTheme.PADDING_MEDIUM, 0))

        # Add border
        self.configure(highlightbackground=DarkTheme.BORDER, highlightthickness=1)

        # Center and show
        self.update()

    def update_status(self, message, progress=None):
        """
        Update the status message and progress bar

        Args:
            message: Status message to display
            progress: Progress value (0-100), None to leave unchanged
        """
        self.status_label['text'] = message
        if progress is not None:
            self.set_progress(progress)
        self.update()

    def set_progress(self, value):
        """
        Set progress bar value

        Args:
            value: Progress value (0-100)
        """
        self.progress_value = max(0, min(100, value))  # Clamp between 0-100
        # Calculate bar width based on percentage
        bar_width = int((self.progress_value / 100) * 400)
        self.progress_canvas.coords(self.progress_bar, 0, 0, bar_width, 6)
        self.update_idletasks()

    def update_version_display(self):
        """Update the version label with current version"""
        version_manager = VersionManager()
        version_text = version_manager.get_display_version()
        self.version_label['text'] = version_text
        self.update()

    def show_version_change(self, old_version, new_version):
        """
        Show version change notification

        Args:
            old_version: Previous version string
            new_version: New version string
        """
        self.version_label['text'] = f"v{old_version} → v{new_version}"
        self.version_label['fg'] = DarkTheme.ACCENT_PRIMARY
        self.update()

    def close(self):
        """Close the splash screen"""
        self.destroy()
