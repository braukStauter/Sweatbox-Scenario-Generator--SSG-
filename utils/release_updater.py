"""
GitHub Release-based updater for standalone executables
Downloads and installs updates from GitHub Releases
"""
import requests
import logging
import zipfile
import shutil
import subprocess
import sys
from pathlib import Path
from packaging import version as version_parser

logger = logging.getLogger(__name__)


class ReleaseUpdater:
    """Handles updates from GitHub Releases for standalone executables"""

    def __init__(self, repo_owner="braukStauter", repo_name="Sweatbox-Scenario-Generator--SSG-"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        # Changed to /releases to get all releases (including pre-releases)
        # /releases/latest excludes pre-releases by default
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"

        # Cleanup old temp files on startup
        self._cleanup_old_temp_files()

    def _cleanup_old_temp_files(self):
        """Clean up any leftover temp files from previous failed updates"""
        try:
            # Clean up temp_update directory
            temp_dir = Path('temp_update')
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info("Cleaned up old temp_update directory")

            # Clean up any old updater scripts
            for updater_file in Path.cwd().glob('updater*.py'):
                try:
                    updater_file.unlink()
                    logger.info(f"Cleaned up old updater script: {updater_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete {updater_file}: {e}")

        except Exception as e:
            logger.warning(f"Failed to cleanup old temp files: {e}")

    def get_current_version(self):
        """Get the current installed version"""
        try:
            import version
            return version.__version__
        except:
            return "0.0.0"

    def check_for_updates(self, progress_callback=None, progress_value_callback=None):
        """
        Check if updates are available from GitHub Releases

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
            progress_value_callback: Optional callback function(value: int) for progress bar

        Returns:
            tuple: (has_updates: bool, message: str, latest_version: str or None)
        """
        try:
            if progress_callback:
                progress_callback("Checking for updates...")
            if progress_value_callback:
                progress_value_callback(20)

            # Fetch all releases from GitHub (including pre-releases)
            logger.info(f"Checking for updates at {self.api_url}")
            response = requests.get(self.api_url, timeout=10)

            if response.status_code == 404:
                logger.info("No releases found on GitHub")
                return False, "No releases available", None

            if response.status_code != 200:
                logger.error(f"GitHub API returned status {response.status_code}")
                return False, f"Failed to check for updates (HTTP {response.status_code})", None

            releases = response.json()

            # Filter out draft releases and get the latest release (including pre-releases)
            valid_releases = [r for r in releases if not r.get('draft', False)]

            if not valid_releases:
                logger.info("No releases found on GitHub")
                return False, "No releases available", None

            # Get the most recent release (first in the list, sorted by date)
            release_data = valid_releases[0]
            latest_version = release_data.get('tag_name', '').lstrip('v')

            if not latest_version:
                logger.warning("No version tag found in release")
                return False, "Invalid release data", None

            current_version = self.get_current_version()

            if progress_callback:
                progress_callback(f"Current: v{current_version}, Latest: v{latest_version}")
            if progress_value_callback:
                progress_value_callback(40)

            # Compare versions
            try:
                if version_parser.parse(latest_version) > version_parser.parse(current_version):
                    logger.info(f"Update available: v{current_version} → v{latest_version}")
                    return True, "Update available", latest_version
                else:
                    logger.info("Application is up to date")
                    return False, "Up to date", None
            except Exception as e:
                logger.error(f"Version comparison failed: {e}")
                return False, "Version check failed", None

        except requests.Timeout:
            logger.error("Update check timed out")
            return False, "Check timed out", None
        except requests.RequestException as e:
            logger.error(f"Network error during update check: {e}")
            return False, f"Network error: {str(e)}", None
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False, f"Error: {str(e)}", None

    def download_update(self, latest_version, progress_callback=None, progress_value_callback=None):
        """
        Download the latest update from GitHub Releases

        Args:
            latest_version: Version to download
            progress_callback: Optional callback for status messages
            progress_value_callback: Optional callback for progress bar

        Returns:
            tuple: (success: bool, download_path: Path or None, message: str)
        """
        try:
            if progress_callback:
                progress_callback("Fetching release information...")
            if progress_value_callback:
                progress_value_callback(50)

            # Get release info
            response = requests.get(self.api_url, timeout=10)
            if response.status_code != 200:
                return False, None, "Failed to fetch release information"

            releases = response.json()

            # Filter out draft releases and get the latest release
            valid_releases = [r for r in releases if not r.get('draft', False)]
            if not valid_releases:
                return False, None, "No releases available"

            release_data = valid_releases[0]
            assets = release_data.get('assets', [])

            # Find the distribution ZIP file
            zip_asset = None
            for asset in assets:
                if asset['name'].endswith('.zip') and 'Distribution' in asset['name']:
                    zip_asset = asset
                    break

            if not zip_asset:
                logger.error("No distribution ZIP found in release assets")
                return False, None, "No distribution package found"

            download_url = zip_asset['browser_download_url']
            file_size = zip_asset.get('size', 0)

            if progress_callback:
                progress_callback(f"Downloading update ({file_size // (1024*1024)} MB)...")
            if progress_value_callback:
                progress_value_callback(55)

            # Download the file
            logger.info(f"Downloading update from {download_url}")
            response = requests.get(download_url, stream=True, timeout=30)

            if response.status_code != 200:
                return False, None, f"Download failed (HTTP {response.status_code})"

            # Save to temp file
            temp_dir = Path('temp_update')
            temp_dir.mkdir(exist_ok=True)
            zip_path = temp_dir / f"SSG_Update_v{latest_version}.zip"

            with open(zip_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if file_size > 0 and progress_value_callback:
                            progress = 55 + int((downloaded / file_size) * 15)
                            progress_value_callback(min(progress, 70))

            if progress_callback:
                progress_callback("Download complete")
            if progress_value_callback:
                progress_value_callback(70)

            logger.info(f"Update downloaded to {zip_path}")
            return True, zip_path, "Download successful"

        except Exception as e:
            logger.error(f"Error downloading update: {e}")
            # Cleanup partial download
            try:
                if 'zip_path' in locals() and zip_path and zip_path.exists():
                    zip_path.unlink()
                    logger.info(f"Cleaned up partial download: {zip_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup partial download: {cleanup_error}")
            return False, None, f"Download error: {str(e)}"

    def apply_update(self, zip_path, latest_version, progress_callback=None, progress_value_callback=None):
        """
        Apply the downloaded update by launching an updater script

        Args:
            zip_path: Path to downloaded update ZIP
            latest_version: Version string of the update
            progress_callback: Optional callback for status messages
            progress_value_callback: Optional callback for progress bar

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            if progress_callback:
                progress_callback("Preparing to install update...")
            if progress_value_callback:
                progress_value_callback(75)

            # Extract update files
            extract_dir = zip_path.parent / 'extracted'
            extract_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Create updater script
            updater_script = self._create_updater_script(extract_dir, latest_version)

            if progress_callback:
                progress_callback("Restarting to apply update...")
            if progress_value_callback:
                progress_value_callback(80)

            # Launch updater script and exit
            logger.info("Launching updater script")
            subprocess.Popen([sys.executable, str(updater_script)],
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)

            return True, "Update will be applied on restart"

        except Exception as e:
            logger.error(f"Error applying update: {e}")
            return False, f"Update failed: {str(e)}"

    def _create_updater_script(self, extract_dir, latest_version):
        """Create a script to replace files after the app exits"""
        import uuid
        updater_path = Path(f'updater_{uuid.uuid4().hex[:8]}.py')

        script_content = f'''
import time
import shutil
import sys
import os
from pathlib import Path

# Wait for main app to exit
time.sleep(2)

try:
    # Source directory (extracted update)
    source = Path(r"{extract_dir.absolute()}") / "SSG_Distribution"

    # Target directory (current installation)
    target = Path.cwd()

    # Validate source directory exists
    if not source.exists():
        print(f"ERROR: Expected directory not found: {{source}}")
        print("The update package appears to be corrupted.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Copy updated files
    if source.exists():
        for item in source.iterdir():
            dest = target / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir() and item.name != "airport_data":
                # Don't overwrite airport_data
                shutil.copytree(item, dest, dirs_exist_ok=True)

        # Create version.py with the updated version
        # This is necessary because version.py is gitignored and won't be in the distribution
        version_file = target / "version.py"
        version_content = """\\"""
Auto-generated version file
Generated during update process
\\"""

__version__ = "{latest_version}"
__commit__ = "release"
__build__ = "0"
"""
        with open(version_file, 'w') as f:
            f.write(version_content.format(latest_version="{latest_version}"))

        # Cleanup
        shutil.rmtree(source.parent)

    # Restart application
    import subprocess
    exe_path = target / "SSG.exe"
    if exe_path.exists():
        subprocess.Popen([str(exe_path)])
    else:
        print("ERROR: SSG.exe not found after update!")
        print("The update may be corrupted. Please reinstall the application.")
        input("Press Enter to exit...")

except Exception as e:
    print(f"Update failed: {{e}}")
    input("Press Enter to exit...")

# Clean up updater script
try:
    os.remove(__file__)
except:
    pass
'''

        with open(updater_path, 'w') as f:
            f.write(script_content)

        return updater_path

    def update_if_available(self, progress_callback=None, progress_value_callback=None):
        """
        Check for and apply updates if available

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
            progress_value_callback: Optional callback function(value: int) for progress bar

        Returns:
            tuple: (updated: bool, message: str, requires_restart: bool)
        """
        # Check if updates are disabled via flag file
        if Path('.no_auto_update').exists():
            logger.info("Auto-update disabled via .no_auto_update flag file")
            if progress_callback:
                progress_callback("Auto-update disabled")
            if progress_value_callback:
                progress_value_callback(75)
            return False, "Auto-update disabled", False

        try:
            # Check for updates
            has_updates, check_message, latest_version = self.check_for_updates(
                progress_callback, progress_value_callback
            )

            if not has_updates:
                if progress_callback:
                    progress_callback("Application is up to date")
                if progress_value_callback:
                    progress_value_callback(75)
                return False, check_message, False

            # Download update
            success, zip_path, download_message = self.download_update(
                latest_version, progress_callback, progress_value_callback
            )

            if not success:
                return False, download_message, False

            # Apply update
            success, apply_message = self.apply_update(
                zip_path, latest_version, progress_callback, progress_value_callback
            )

            return success, apply_message, success

        except Exception as e:
            logger.error(f"Error during auto-update: {e}")
            if progress_callback:
                progress_callback("Update failed, continuing...")
            if progress_value_callback:
                progress_value_callback(75)
            return False, f"Error: {str(e)}", False
