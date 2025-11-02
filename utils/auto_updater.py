"""
Auto-updater module for checking and applying updates from GitHub
"""
import subprocess
import logging
import sys
from pathlib import Path
from utils.version_manager import VersionManager

logger = logging.getLogger(__name__)

# Windows-specific flag to hide console windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


class AutoUpdater:
    """Handles automatic updates from GitHub repository"""

    def __init__(self, repo_url="https://github.com/braukStauter/Sweatbox-Scenario-Generator--SSG-.git", branch="main"):
        self.repo_url = repo_url
        self.branch = branch
        self.is_git_repo = self._check_git_repo()
        self.version_manager = VersionManager()
        self.old_version = None
        self.new_version = None

    def _check_git_repo(self):
        """Check if current directory is a git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to check git repository status: {e}")
            return False

    def check_for_updates(self, progress_callback=None, progress_value_callback=None):
        """
        Check if updates are available from remote repository

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
            progress_value_callback: Optional callback function(value: int) for progress bar

        Returns:
            tuple: (has_updates: bool, message: str)
        """
        if not self.is_git_repo:
            return False, "Not a git repository"

        try:
            if progress_callback:
                progress_callback("Fetching latest updates...")
            if progress_value_callback:
                progress_value_callback(20)

            # Fetch latest changes from remote
            result = subprocess.run(
                ["git", "fetch", "origin", self.branch],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode != 0:
                # Check if it's an authentication error
                stderr = result.stderr.lower()
                if "authentication" in stderr or "permission denied" in stderr or "403" in stderr or "401" in stderr:
                    logger.info("Unable to fetch updates - repository requires authentication")
                    return False, "Authentication required"
                else:
                    logger.error(f"Git fetch failed: {result.stderr}")
                    return False, f"Failed to fetch updates: {result.stderr}"

            if progress_callback:
                progress_callback("Checking for changes...")
            if progress_value_callback:
                progress_value_callback(40)

            # Compare local and remote commits
            local_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            ).stdout.strip()

            remote_commit = subprocess.run(
                ["git", "rev-parse", f"origin/{self.branch}"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            ).stdout.strip()

            if local_commit == remote_commit:
                logger.info("Application is up to date")
                if progress_value_callback:
                    progress_value_callback(50)
                return False, "Up to date"
            else:
                logger.info(f"Updates available: {local_commit[:7]} -> {remote_commit[:7]}")
                if progress_value_callback:
                    progress_value_callback(50)
                return True, "Updates available"

        except subprocess.TimeoutExpired:
            logger.error("Update check timed out")
            return False, "Check timed out"
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False, f"Error: {str(e)}"

    def apply_updates(self, progress_callback=None, progress_value_callback=None):
        """
        Apply updates from remote repository

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
            progress_value_callback: Optional callback function(value: int) for progress bar

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.is_git_repo:
            return False, "Not a git repository"

        try:
            # Store current version before update
            self.old_version = self.version_manager.get_current_version()
            logger.info(f"Current version before update: {self.old_version}")

            if progress_callback:
                progress_callback("Checking working tree status...")
            if progress_value_callback:
                progress_value_callback(55)

            # Check for local changes
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )

            if status_result.stdout.strip():
                # There are local changes - stash them
                logger.info("Local changes detected, stashing...")
                if progress_callback:
                    progress_callback("Saving local changes...")
                if progress_value_callback:
                    progress_value_callback(60)

                stash_result = subprocess.run(
                    ["git", "stash", "push", "-m", "Auto-stash before update"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=CREATE_NO_WINDOW
                )

                if stash_result.returncode != 0:
                    logger.error(f"Failed to stash changes: {stash_result.stderr}")
                    return False, "Failed to save local changes"

            if progress_callback:
                progress_callback("Applying updates...")
            if progress_value_callback:
                progress_value_callback(65)

            # Pull latest changes
            pull_result = subprocess.run(
                ["git", "pull", "origin", self.branch, "--ff-only"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW
            )

            if pull_result.returncode != 0:
                logger.error(f"Git pull failed: {pull_result.stderr}")
                return False, f"Failed to apply updates: {pull_result.stderr}"

            # Get new version after update
            # Need to reload the module to get updated version
            import importlib
            import version as version_module
            importlib.reload(version_module)
            self.new_version = version_module.__version__

            logger.info(f"Updates applied successfully: {self.old_version} → {self.new_version}")

            if progress_callback:
                if self.old_version != self.new_version:
                    progress_callback(f"Updated to v{self.new_version}!")
                else:
                    progress_callback("Updates applied successfully!")

            if progress_value_callback:
                progress_value_callback(75)

            return True, "Updates applied successfully"

        except subprocess.TimeoutExpired:
            logger.error("Update application timed out")
            return False, "Update timed out"
        except Exception as e:
            logger.error(f"Error applying updates: {e}")
            return False, f"Error: {str(e)}"

    def get_version_change(self):
        """
        Get version change information from last update

        Returns:
            tuple: (old_version, new_version) or (None, None) if no update occurred
        """
        return self.old_version, self.new_version

    def update_if_available(self, progress_callback=None, progress_value_callback=None):
        """
        Check for and apply updates if available

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
            progress_value_callback: Optional callback function(value: int) for progress bar

        Returns:
            tuple: (updated: bool, message: str)
        """
        if not self.is_git_repo:
            logger.info("Not a git repository, skipping update check")
            if progress_callback:
                progress_callback("Ready!")
            if progress_value_callback:
                progress_value_callback(75)
            return False, "Not a git repository"

        try:
            # Check for updates
            has_updates, check_message = self.check_for_updates(progress_callback, progress_value_callback)

            if not has_updates:
                if progress_callback:
                    progress_callback("Application is up to date")
                if progress_value_callback:
                    progress_value_callback(75)
                return False, check_message

            # Apply updates
            success, update_message = self.apply_updates(progress_callback, progress_value_callback)

            return success, update_message

        except Exception as e:
            logger.error(f"Error during auto-update: {e}")
            if progress_callback:
                progress_callback("Update failed, continuing...")
            if progress_value_callback:
                progress_value_callback(75)
            return False, f"Error: {str(e)}"
