"""
Keychain Credential Store for Google Workspace MCP

Uses macOS Keychain (via keyring library) instead of plain JSON files.
Tokens are encrypted and protected by your macOS login password.

Configuration via environment variables:
    GOOGLE_MCP_CREDENTIAL_BACKEND=keychain  # Enable Keychain storage
    GOOGLE_MCP_KEYCHAIN_SERVICE=my-service  # Custom service name for isolation

For multi-project isolation, use different service names per project:
    - "google-mcp-personal" for personal project
    - "google-mcp-work" for work project
"""

import os
import json
import logging
from typing import Optional, List
from datetime import datetime
from google.oauth2.credentials import Credentials

from .credential_store import CredentialStore

logger = logging.getLogger(__name__)

# Check for keyring availability
try:
    import keyring
    import keyring.errors
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    keyring = None

# Default service name - can be overridden per project
DEFAULT_SERVICE_NAME = "google-workspace-mcp"


class KeychainCredentialStore(CredentialStore):
    """
    Credential store using macOS Keychain (via keyring library).

    Security benefits over file-based storage:
        - Tokens encrypted with AES-256
        - Protected by macOS login password
        - Per-app access control (visible in Keychain Access app)
        - Tokens don't survive disk cloning to another machine

    Different projects can use different service names for account isolation.
    """

    def __init__(self, service_name: Optional[str] = None):
        """
        Initialize the Keychain credential store.

        Args:
            service_name: Keychain service identifier. If None, uses:
                1. GOOGLE_MCP_KEYCHAIN_SERVICE env var
                2. DEFAULT_SERVICE_NAME ("google-workspace-mcp")

        Raises:
            ImportError: If keyring library is not installed
            RuntimeError: If not running on a supported platform
        """
        if not KEYRING_AVAILABLE:
            raise ImportError(
                "keyring library not installed. Install with: pip install keyring"
            )

        # Verify we have a working keyring backend
        backend = keyring.get_keyring()
        if backend is None or "fail" in type(backend).__name__.lower():
            raise RuntimeError(
                f"No working keyring backend found. Current backend: {backend}. "
                "On macOS, ensure you're running with proper permissions."
            )

        if service_name is None:
            service_name = os.getenv(
                "GOOGLE_MCP_KEYCHAIN_SERVICE",
                DEFAULT_SERVICE_NAME
            )

        self.service_name = service_name
        self._user_list_key = "__registered_users__"  # Special key to track users

        logger.info(
            f"KeychainCredentialStore initialized with service: {service_name}, "
            f"backend: {type(backend).__name__}"
        )

    def _serialize_credentials(self, credentials: Credentials) -> str:
        """Serialize credentials to JSON string for Keychain storage."""
        creds_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else None,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
        return json.dumps(creds_data)

    def _deserialize_credentials(self, data: str) -> Credentials:
        """Deserialize JSON string from Keychain to Credentials object."""
        creds_data = json.loads(data)

        # Parse expiry if present
        expiry = None
        if creds_data.get("expiry"):
            try:
                expiry = datetime.fromisoformat(creds_data["expiry"])
                # Ensure timezone-naive datetime for Google auth library compatibility
                if expiry.tzinfo is not None:
                    expiry = expiry.replace(tzinfo=None)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse expiry time: {e}")

        return Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes"),
            expiry=expiry,
        )

    def get_credential(self, user_email: str) -> Optional[Credentials]:
        """
        Get credentials from macOS Keychain.

        Args:
            user_email: User's email address

        Returns:
            Google Credentials object or None if not found
        """
        try:
            data = keyring.get_password(self.service_name, user_email)

            if data is None:
                logger.debug(
                    f"No credentials in Keychain for {user_email} "
                    f"(service: {self.service_name})"
                )
                return None

            credentials = self._deserialize_credentials(data)
            logger.debug(
                f"Loaded credentials for {user_email} from Keychain "
                f"(service: {self.service_name})"
            )
            return credentials

        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding credentials for {user_email}: {e}. "
                "Credentials may be corrupted."
            )
            return None
        except Exception as e:
            logger.error(f"Error loading credentials for {user_email}: {e}")
            return None

    def store_credential(self, user_email: str, credentials: Credentials) -> bool:
        """
        Store credentials in macOS Keychain.

        Args:
            user_email: User's email address
            credentials: Google Credentials object to store

        Returns:
            True if successfully stored, False otherwise
        """
        try:
            data = self._serialize_credentials(credentials)
            keyring.set_password(self.service_name, user_email, data)

            # Update user list for list_users() functionality
            self._add_to_user_list(user_email)

            logger.info(
                f"Stored credentials for {user_email} in Keychain "
                f"(service: {self.service_name})"
            )
            return True

        except Exception as e:
            logger.error(f"Error storing credentials for {user_email}: {e}")
            return False

    def delete_credential(self, user_email: str) -> bool:
        """
        Delete credentials from macOS Keychain.

        Args:
            user_email: User's email address

        Returns:
            True if successfully deleted (or didn't exist), False on error
        """
        try:
            keyring.delete_password(self.service_name, user_email)
            self._remove_from_user_list(user_email)

            logger.info(
                f"Deleted credentials for {user_email} from Keychain "
                f"(service: {self.service_name})"
            )
            return True

        except keyring.errors.PasswordDeleteError:
            # Password didn't exist - that's fine
            logger.debug(
                f"No credentials to delete for {user_email} "
                f"(service: {self.service_name})"
            )
            self._remove_from_user_list(user_email)  # Clean up user list anyway
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials for {user_email}: {e}")
            return False

    def list_users(self) -> List[str]:
        """
        List all users with stored credentials.

        Note: Keychain doesn't support listing all entries for a service,
        so we maintain a separate list of registered users.

        Returns:
            List of user email addresses
        """
        try:
            data = keyring.get_password(self.service_name, self._user_list_key)
            if data:
                users = json.loads(data)
                # Validate that credentials still exist for listed users
                valid_users = [u for u in users if self._credential_exists(u)]
                if len(valid_users) != len(users):
                    # Clean up stale entries
                    self._save_user_list(valid_users)
                return valid_users
            return []
        except json.JSONDecodeError:
            logger.warning("User list corrupted, returning empty list")
            return []
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []

    def _credential_exists(self, user_email: str) -> bool:
        """Check if credentials exist for a user without fully loading them."""
        try:
            return keyring.get_password(self.service_name, user_email) is not None
        except Exception:
            return False

    def _add_to_user_list(self, user_email: str):
        """Add user to the tracked user list."""
        users = self.list_users()
        if user_email not in users:
            users.append(user_email)
            users.sort()
            self._save_user_list(users)

    def _remove_from_user_list(self, user_email: str):
        """Remove user from the tracked user list."""
        users = self.list_users()
        if user_email in users:
            users.remove(user_email)
            self._save_user_list(users)

    def _save_user_list(self, users: List[str]):
        """Save the user list to Keychain."""
        try:
            keyring.set_password(
                self.service_name,
                self._user_list_key,
                json.dumps(users)
            )
        except Exception as e:
            logger.error(f"Error saving user list: {e}")
