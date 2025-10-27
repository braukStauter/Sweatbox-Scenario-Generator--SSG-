"""
Splash screen for application startup
"""
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk
from gui.theme import DarkTheme


class SplashScreen(tk.Toplevel):
    """Splash screen displayed during application startup"""

    def __init__(self, parent):
        super().__init__(parent)

        # Configure window
        self.title("")
        self.overrideredirect(True)  # Remove window decorations

        # Set size and center on screen
        width = 600
        height = 320
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

        # Load and display logo
        try:
            logo_path = Path("utils") / "Creative Shrimp.png"
            if logo_path.exists():
                logo_image = Image.open(logo_path)
                # Resize logo to fit nicely (max 100 pixels height)
                logo_height = 100
                aspect_ratio = logo_image.width / logo_image.height
                logo_width = int(logo_height * aspect_ratio)
                logo_image = logo_image.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

                self.logo_photo = ImageTk.PhotoImage(logo_image)
                logo_label = tk.Label(content, image=self.logo_photo, bg=DarkTheme.BG_PRIMARY)
                logo_label.pack(pady=(DarkTheme.PADDING_SMALL, 4))
        except Exception as e:
            # If logo can't be loaded, just skip it
            pass

        # App title
        title = tk.Label(
            content,
            text="Sweatbox Session Generator",
            font=(DarkTheme.FONT_FAMILY, 24, 'bold'),
            fg=DarkTheme.FG_PRIMARY,
            bg=DarkTheme.BG_PRIMARY,
            wraplength=550  # Wrap text if needed
        )
        title.pack(pady=(0, 2))

        # App subtitle (SSG)
        subtitle = tk.Label(
            content,
            text="(SSG)",
            font=(DarkTheme.FONT_FAMILY, 14),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_PRIMARY
        )
        subtitle.pack(pady=(0, DarkTheme.PADDING_MEDIUM))

        # Separator line
        separator = tk.Frame(content, bg=DarkTheme.ACCENT_PRIMARY, height=2)
        separator.pack(fill='x', pady=DarkTheme.PADDING_MEDIUM)

        # Status label
        self.status_label = tk.Label(
            content,
            text="Loading...",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_PRIMARY
        )
        self.status_label.pack(pady=DarkTheme.PADDING_LARGE)

        # Version label
        version = tk.Label(
            content,
            text="v1.0.0",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg=DarkTheme.FG_DISABLED,
            bg=DarkTheme.BG_PRIMARY
        )
        version.pack(side='bottom', pady=(0, DarkTheme.PADDING_SMALL))

        # Copyright label
        copyright_label = tk.Label(
            content,
            text="Developed by Creative Shrimp™ (Ethan M) for ZAB",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg="#404040",  # Very subtle gray
            bg=DarkTheme.BG_PRIMARY
        )
        copyright_label.pack(side='bottom', pady=DarkTheme.PADDING_SMALL)

        # Add border
        self.configure(highlightbackground=DarkTheme.BORDER, highlightthickness=1)

        # Center and show
        self.update()

    def update_status(self, message):
        """Update the status message"""
        self.status_label['text'] = message
        self.update()

    def close(self):
        """Close the splash screen"""
        self.destroy()
