"""
GUI entry point for vNAS Sweatbox Scenario Generator

This is the main entry point for the graphical user interface version
of the application.
"""
import tkinter as tk
import logging
import sys
from datetime import datetime
from pathlib import Path

from gui.splash_screen import SplashScreen
from gui.main_window import MainWindow

# Setup logging to both console and file
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"ssg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to: {log_file}")


def main():
    """Main entry point for GUI application"""
    try:
        # Create hidden root window
        root = tk.Tk()
        root.withdraw()

        # Show splash screen
        splash = SplashScreen(root)
        splash.update_status("Loading application...")

        # Simulate loading (give splash screen time to display)
        root.after(1000, lambda: splash.update_status("Initializing components..."))
        root.after(2000, lambda: splash.update_status("Ready!"))
        root.after(2500, lambda: launch_main_window(root, splash))

        root.mainloop()

    except KeyboardInterrupt:
        logger.info("\n\nCancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


def launch_main_window(root, splash):
    """Launch the main application window"""
    try:
        # Close splash screen
        splash.close()

        # Destroy hidden root
        root.destroy()

        # Create and show main window
        app = MainWindow()
        app.mainloop()

    except Exception as e:
        logger.error(f"Error launching main window: {e}")
        logger.exception("Error launching main window")
        sys.exit(1)


if __name__ == "__main__":
    main()
