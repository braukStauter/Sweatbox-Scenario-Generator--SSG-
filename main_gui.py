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


# Global variable to store update info for notification after main window launches
pending_update_notification = None


def perform_startup_tasks(root, splash):
    """
    Perform startup tasks including update check in background thread

    Args:
        root: Root Tk window
        splash: SplashScreen instance
    """
    global pending_update_notification

    def update_task():
        global pending_update_notification
        try:
            # Initialize updater
            updater = AutoUpdater()

            # Set initial progress
            root.after(0, lambda: splash.update_status("Checking for updates...", 10))

            # Check for updates (but don't download/install automatically)
            has_update, latest_version = updater.check_for_update_notification()

            if has_update and latest_version:
                logger.info(f"Version mismatch detected: {latest_version}")
                root.after(0, lambda: splash.update_status("Version mismatch detected", 80))
                # Store the update info to show after main window launches
                pending_update_notification = latest_version
            else:
                logger.info("Version matches GitHub release")
                root.after(0, lambda: splash.update_status("Version matches GitHub release", 80))

            # Finish loading
            root.after(500, lambda: splash.update_status("Initializing components...", 90))
            root.after(1000, lambda: splash.update_status("Ready!", 100))
            root.after(1500, lambda: launch_main_window(root, splash))

        except Exception as e:
            logger.error(f"Error during startup: {e}")
            # Continue even if update check fails
            root.after(0, lambda: splash.update_status("Starting application...", 80))
            root.after(500, lambda: splash.update_status("Ready!", 100))
            root.after(1000, lambda: launch_main_window(root, splash))

    # Start update task in background thread
    update_thread = threading.Thread(target=update_task, daemon=True)
    update_thread.start()


def show_update_notification(latest_version):
    """
    Show a popup notification when version differs from GitHub release

    Args:
        latest_version: The version string of the GitHub release
    """
    import tkinter.messagebox as messagebox
    import webbrowser
    from utils.version_manager import VersionManager

    # Get current version for display
    vm = VersionManager()
    current_version = vm.get_current_version()

    response = messagebox.askquestion(
        "Version Mismatch",
        f"Your version (v{current_version}) differs from the latest GitHub release (v{latest_version}).\n\n"
        f"Would you like to visit the releases page?",
        icon='info'
    )

    if response == 'yes':
        webbrowser.open("https://github.com/braukStauter/Sweatbox-Scenario-Generator--SSG-/releases/latest")


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
    global pending_update_notification
    try:
        # Close splash screen
        splash.close()

        # Destroy hidden root
        root.destroy()

        # Create and show main window
        app = MainWindow()

        # Show update notification if there's a pending one
        if pending_update_notification:
            logger.info(f"Showing update notification for version {pending_update_notification}")
            # Schedule notification to appear 1 second after main window is shown
            app.after(1000, lambda: show_update_notification(pending_update_notification))

        app.mainloop()

    except Exception as e:
        logger.error(f"Error launching main window: {e}")
        logger.exception("Error launching main window")
        sys.exit(1)


if __name__ == "__main__":
    main()
