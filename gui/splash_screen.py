"""
Splash screen for application startup
"""
import tkinter as tk
from PIL import Image, ImageTk
from gui.theme import DarkTheme
from utils.version_manager import VersionManager
import os
import sys


class SplashScreen(tk.Toplevel):
    """Splash screen displayed during application startup"""

    def __init__(self, parent):
        super().__init__(parent)

        # Configure window
        self.title("")
        self.overrideredirect(True)  # Remove window decorations

        # Configure background
        self.configure(bg=DarkTheme.BG_PRIMARY)

        # Create content frame
        content = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)
        content.pack(expand=True, fill='both', padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_XLARGE)

        # Load and display logo
        try:
            # Determine base path (different for PyInstaller vs normal Python)
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_path = sys._MEIPASS
            else:
                # Running as normal Python script
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            logo_path = os.path.join(base_path, 'gui', 'SSG_Logo.png')

            if os.path.exists(logo_path):
                # Load and resize logo to reasonable size (max width 400px, maintain aspect ratio)
                pil_image = Image.open(logo_path)

                # Calculate new size maintaining aspect ratio
                max_width = 400
                aspect_ratio = pil_image.height / pil_image.width
                new_width = min(pil_image.width, max_width)
                new_height = int(new_width * aspect_ratio)

                # Resize image
                resized_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logo_image = ImageTk.PhotoImage(resized_image)

                # Keep reference to prevent garbage collection
                self.logo_image = logo_image

                logo_label = tk.Label(
                    content,
                    image=logo_image,
                    bg=DarkTheme.BG_PRIMARY
                )
                logo_label.pack(pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_MEDIUM))
            else:
                # Fallback to text if image not found
                title = tk.Label(
                    content,
                    text="Sweatbox Session Generator",
                    font=(DarkTheme.FONT_FAMILY, 24, 'bold'),
                    fg=DarkTheme.FG_PRIMARY,
                    bg=DarkTheme.BG_PRIMARY,
                    wraplength=550
                )
                title.pack(pady=(DarkTheme.PADDING_LARGE, 2))

                subtitle = tk.Label(
                    content,
                    text="(SSG)",
                    font=(DarkTheme.FONT_FAMILY, 14),
                    fg=DarkTheme.FG_SECONDARY,
                    bg=DarkTheme.BG_PRIMARY
                )
                subtitle.pack(pady=(0, DarkTheme.PADDING_LARGE))
        except Exception as e:
            # Fallback to text if image loading fails
            title = tk.Label(
                content,
                text="Sweatbox Session Generator",
                font=(DarkTheme.FONT_FAMILY, 24, 'bold'),
                fg=DarkTheme.FG_PRIMARY,
                bg=DarkTheme.BG_PRIMARY,
                wraplength=550
            )
            title.pack(pady=(DarkTheme.PADDING_LARGE, 2))

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

        # Update to calculate required size
        self.update_idletasks()

        # Get the required size based on content
        width = 600  # Fixed width
        required_height = self.winfo_reqheight()

        # Set geometry with dynamic height and center on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - required_height) // 2
        self.geometry(f"{width}x{required_height}+{x}+{y}")

        # Final update to show centered window
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
