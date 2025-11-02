"""
Dark theme configuration for the GUI
"""

class DarkTheme:
    """Dark theme color palette and styles"""

    BG_PRIMARY = "#1e1e1e"
    BG_SECONDARY = "#2d2d2d"
    BG_TERTIARY = "#3d3d3d"

    FG_PRIMARY = "#ffffff"
    FG_SECONDARY = "#b0b0b0"
    FG_DISABLED = "#666666"

    ACCENT_PRIMARY = "#0078d4"
    ACCENT_HOVER = "#106ebe"
    ACCENT_PRESSED = "#005a9e"

    SUCCESS = "#107c10"
    WARNING = "#ff8c00"
    ERROR = "#e81123"

    BORDER = "#404040"
    DIVIDER = "#2d2d2d"

    FONT_FAMILY = "Segoe UI"
    FONT_SIZE_LARGE = 16
    FONT_SIZE_NORMAL = 11
    FONT_SIZE_SMALL = 9
    FONT_SIZE_TITLE = 24
    FONT_SIZE_HEADING = 18

    PADDING_SMALL = 8
    PADDING_MEDIUM = 16
    PADDING_LARGE = 24
    PADDING_XLARGE = 32

    BORDER_RADIUS = 4

    BUTTON_HEIGHT = 36
    BUTTON_MIN_WIDTH = 120

    @classmethod
    def get_button_style(cls):
        """Get button style configuration"""
        return {
            'bg': cls.ACCENT_PRIMARY,
            'fg': cls.FG_PRIMARY,
            'activebackground': cls.ACCENT_PRESSED,
            'activeforeground': cls.FG_PRIMARY,
            'relief': 'flat',
            'borderwidth': 0,
            'cursor': 'hand2',
            'font': (cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL, 'bold')
        }

    @classmethod
    def get_secondary_button_style(cls):
        """Get secondary button style configuration"""
        return {
            'bg': cls.BG_TERTIARY,
            'fg': cls.FG_PRIMARY,
            'activebackground': cls.BG_SECONDARY,
            'activeforeground': cls.FG_PRIMARY,
            'relief': 'flat',
            'borderwidth': 0,
            'cursor': 'hand2',
            'font': (cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL)
        }

    @classmethod
    def get_entry_style(cls):
        """Get entry/input style configuration"""
        return {
            'bg': cls.BG_SECONDARY,
            'fg': cls.FG_PRIMARY,
            'insertbackground': cls.FG_PRIMARY,
            'relief': 'solid',
            'borderwidth': 2,
            'highlightthickness': 2,
            'highlightcolor': cls.ACCENT_PRIMARY,
            'highlightbackground': cls.BORDER,
            'font': (cls.FONT_FAMILY, 12)
        }

    @classmethod
    def get_label_style(cls):
        """Get label style configuration"""
        return {
            'bg': cls.BG_PRIMARY,
            'fg': cls.FG_PRIMARY,
            'font': (cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL)
        }

    @classmethod
    def get_heading_style(cls):
        """Get heading label style configuration"""
        return {
            'bg': cls.BG_PRIMARY,
            'fg': cls.FG_PRIMARY,
            'font': (cls.FONT_FAMILY, cls.FONT_SIZE_HEADING, 'bold')
        }

    @classmethod
    def get_frame_style(cls):
        """Get frame style configuration"""
        return {
            'bg': cls.BG_PRIMARY,
            'relief': 'flat',
            'borderwidth': 0
        }

    @classmethod
    def get_card_style(cls):
        """Get card/panel style configuration"""
        return {
            'bg': cls.BG_SECONDARY,
            'relief': 'flat',
            'borderwidth': 0
        }
