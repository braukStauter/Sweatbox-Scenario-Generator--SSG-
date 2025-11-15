"""
Update checker module for checking updates from GitHub
"""
import requests
import logging
from pathlib import Path
from packaging import version as version_parser

logger = logging.getLogger(__name__)


def is_standalone_executable():
    """Check if running as a compiled executable (not in a git repo)"""
    return not Path('.git').exists()


class AutoUpdater:
    """Handles update checking from GitHub releases"""

    def __init__(self, repo_owner="braukStauter", repo_name="Sweatbox-Scenario-Generator--SSG-"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"

    def get_current_version(self):
        """Get the current installed version"""
        try:
            import version
            return version.__version__
        except:
            return "0.0.0"

    def check_for_update_notification(self):
        """
        Simple check for updates to show notification only (no automatic download/install)

        Returns:
            tuple: (has_update: bool, latest_version: str or None)
        """
        # Check if updates are disabled via flag file
        if Path('.no_auto_update').exists():
            logger.info("Update check disabled via .no_auto_update flag file")
            return False, None

        # Only check for release updates when running as standalone
        if not is_standalone_executable():
            logger.info("Running in development mode, skipping update check")
            return False, None

        try:
            logger.info(f"Checking for updates at {self.api_url}")
            response = requests.get(self.api_url, timeout=10)

            if response.status_code == 404:
                logger.info("No releases found on GitHub")
                return False, None

            if response.status_code != 200:
                logger.error(f"GitHub API returned status {response.status_code}")
                return False, None

            releases = response.json()

            # Filter out draft releases and get the latest release
            valid_releases = [r for r in releases if not r.get('draft', False)]

            if not valid_releases:
                logger.info("No releases found on GitHub")
                return False, None

            # Get the most recent release
            release_data = valid_releases[0]
            latest_version = release_data.get('tag_name', '').lstrip('v')

            if not latest_version:
                logger.warning("No version tag found in release")
                return False, None

            current_version = self.get_current_version()

            logger.info(f"Current version: {current_version}, Latest version: {latest_version}")

            # Compare versions
            try:
                if version_parser.parse(latest_version) != version_parser.parse(current_version):
                    logger.info(f"Version mismatch: v{current_version} (local) vs v{latest_version} (GitHub)")
                    return True, latest_version
                else:
                    logger.info("Application version matches GitHub release")
                    return False, None
            except Exception as e:
                logger.error(f"Version comparison failed: {e}")
                return False, None

        except requests.Timeout:
            logger.error("Update check timed out")
            return False, None
        except requests.RequestException as e:
            logger.error(f"Network error during update check: {e}")
            return False, None
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False, None
