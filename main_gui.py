"""
GUI entry point for vNAS Sweatbox Scenario Generator

This is the main entry point for the graphical user interface version
of the application.
"""
import tkinter as tk
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

from gui.splash_screen import SplashScreen
from gui.main_window import MainWindow
from utils.auto_updater import AutoUpdater

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


def perform_startup_tasks(root, splash):
    """
    Perform startup tasks including update check in background thread

    Args:
        root: Root Tk window
        splash: SplashScreen instance
    """
    def update_task():
        try:
            # Initialize updater
            updater = AutoUpdater()

            def progress_callback(message):
                # Update splash screen from background thread
                root.after(0, lambda m=message: splash.update_status(m))

            def progress_value_callback(value):
                # Update progress bar from background thread
                root.after(0, lambda v=value: splash.set_progress(v))

            # Set initial progress
            root.after(0, lambda: splash.update_status("Checking for updates...", 10))

            # Check and apply updates
            updated, message = updater.update_if_available(progress_callback, progress_value_callback)

            if updated:
                logger.info("Application updated successfully")
                # Get version change info
                old_version, new_version = updater.get_version_change()

                if old_version and new_version and old_version != new_version:
                    logger.info(f"Version changed: {old_version} → {new_version}")
                    root.after(0, lambda: splash.show_version_change(old_version, new_version))
                    root.after(0, lambda: splash.update_status(f"Updated to v{new_version}!", 80))
                else:
                    root.after(0, lambda: splash.update_status("Updated successfully!", 80))
                    root.after(0, lambda: splash.update_version_display())
            else:
                logger.info(f"Update check complete: {message}")
                root.after(0, lambda: splash.update_status("Application is up to date", 80))

            # Finish loading
            root.after(500, lambda: splash.update_status("Initializing components...", 90))
            root.after(1000, lambda: splash.update_status("Ready!", 100))
            root.after(1500, lambda: launch_main_window(root, splash))

        except Exception as e:
            logger.error(f"Error during startup: {e}")
            # Continue even if update fails
            root.after(0, lambda: splash.update_status("Starting application...", 80))
            root.after(500, lambda: splash.update_status("Ready!", 100))
            root.after(1000, lambda: launch_main_window(root, splash))

    # Start update task in background thread
    update_thread = threading.Thread(target=update_task, daemon=True)
    update_thread.start()


def main():
    """Main entry point for GUI application"""
    try:
        # Create hidden root window
        root = tk.Tk()
        root.withdraw()

        # Show splash screen
        splash = SplashScreen(root)
        splash.update_status("Starting...", 0)

        # Start background tasks after a brief delay to show splash
        root.after(100, lambda: perform_startup_tasks(root, splash))

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
