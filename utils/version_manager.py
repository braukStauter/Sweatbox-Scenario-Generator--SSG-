"""
Version management and tracking utilities
"""
import subprocess
import logging
import sys
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Windows-specific flag to hide console windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


class VersionManager:
    """Manages application version information and tracking"""

    def __init__(self):
        self.version_file = Path("version.py")

    def get_current_version(self) -> str:
        """
        Get the current application version

        Returns:
            Version string (e.g., "1.0.0")
        """
        try:
            # Import version module (works both for source and compiled exe)
            import version
            return version.__version__
        except ImportError:
            # Module not found
            logger.debug("version module not found")
            return "0.0.0"
        except Exception as e:
            logger.error(f"Failed to get version: {e}")
            return "0.0.0"

    def get_git_version(self) -> Optional[str]:
        """
        Get version from git tags

        Returns:
            Version string from git tag or None
        """
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                tag = result.stdout.strip()
                # Remove 'v' prefix if present
                return tag.lstrip('v')

            return None

        except Exception as e:
            logger.debug(f"No git tag found: {e}")
            return None

    def get_commit_hash(self) -> Optional[str]:
        """
        Get current git commit hash (short)

        Returns:
            Short commit hash or None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                return result.stdout.strip()

            return None

        except Exception as e:
            logger.debug(f"Failed to get commit hash: {e}")
            return None

    def get_commit_count(self) -> int:
        """
        Get total number of commits

        Returns:
            Number of commits or 0
        """
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                return int(result.stdout.strip())

            return 0

        except Exception as e:
            logger.debug(f"Failed to get commit count: {e}")
            return 0

    def get_version_info(self) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Get comprehensive version information

        Returns:
            Tuple of (version, commit_hash, build_number)
        """
        version = self.get_current_version()
        commit_hash = self.get_commit_hash()
        git_version = self.get_git_version()

        # Use git version if available, otherwise use version.py
        if git_version:
            version = git_version

        return version, commit_hash, str(self.get_commit_count()) if self.get_commit_count() > 0 else None

    def get_display_version(self) -> str:
        """
        Get formatted version string for display

        Returns:
            Formatted version string (e.g., "v1.0.0 (build 123)")
        """
        # First try to get version from version.py module (works for both source and compiled exe)
        try:
            import version
            import importlib
            importlib.reload(version)

            parts = [f"v{version.__version__}"]

            if hasattr(version, '__build__') and version.__build__ and version.__build__ != "0":
                parts.append(f"(build {version.__build__})")
            elif hasattr(version, '__commit__') and version.__commit__ and version.__commit__ != "unknown":
                parts.append(f"({version.__commit__})")

            return " ".join(parts)
        except ImportError:
            # version module not found, fall back to git
            logger.debug("version module not found, using git-based version")
        except Exception as e:
            logger.debug(f"Could not read from version module: {e}")

        # Fallback to git-based version info (for development)
        version_str, commit_hash, build_number = self.get_version_info()

        parts = [f"v{version_str}"]

        if build_number:
            parts.append(f"(build {build_number})")
        elif commit_hash:
            parts.append(f"({commit_hash})")

        return " ".join(parts)

    def check_version_changed(self, old_commit: str, new_commit: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if version changed between two commits

        Args:
            old_commit: Previous commit hash
            new_commit: New commit hash

        Returns:
            Tuple of (changed: bool, old_version: str, new_version: str)
        """
        try:
            # Get version from old commit
            old_version_result = subprocess.run(
                ["git", "show", f"{old_commit}:version.py"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW
            )

            old_version = "unknown"
            if old_version_result.returncode == 0:
                # Parse version from file content
                for line in old_version_result.stdout.split('\n'):
                    if line.startswith('__version__'):
                        old_version = line.split('=')[1].strip().strip('"\'')
                        break

            # Get current version
            new_version = self.get_current_version()

            return old_version != new_version, old_version, new_version

        except Exception as e:
            logger.error(f"Failed to check version change: {e}")
            return False, None, None

    def get_changelog_since_version(self, old_version: str) -> list:
        """
        Get changelog entries since a specific version

        Args:
            old_version: Previous version string

        Returns:
            List of commit messages
        """
        try:
            # Get commits since the old version tag
            result = subprocess.run(
                ["git", "log", f"v{old_version}..HEAD", "--oneline", "--no-merges"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                commits = result.stdout.strip().split('\n')
                return [commit for commit in commits if commit]

            return []

        except Exception as e:
            logger.error(f"Failed to get changelog: {e}")
            return []

    def get_recent_commits(self, count: int = 5) -> list:
        """
        Get recent commit messages

        Args:
            count: Number of commits to retrieve

        Returns:
            List of commit messages
        """
        try:
            result = subprocess.run(
                ["git", "log", f"-{count}", "--oneline", "--no-merges"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                commits = result.stdout.strip().split('\n')
                return [commit for commit in commits if commit]

            return []

        except Exception as e:
            logger.error(f"Failed to get recent commits: {e}")
            return []
