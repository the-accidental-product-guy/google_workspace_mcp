#!/usr/bin/env python3
"""
Setup script for storing Google OAuth credentials in macOS Keychain.

This script securely stores your OAuth Client ID and Client Secret in
the macOS Keychain, so they don't need to be in config files or environment
variables.

Usage:
    python3 setup_keychain.py [--service SERVICE_NAME]

Examples:
    # Store credentials with default service name
    python3 setup_keychain.py

    # Store credentials for a specific project
    python3 setup_keychain.py --service google-mcp-sd-project

    # Delete stored credentials
    python3 setup_keychain.py --delete

    # Show stored credentials info (not the actual secrets)
    python3 setup_keychain.py --show
"""

import argparse
import getpass
import sys
import os
import json

# Key for storing OAuth client credentials in Keychain
CLIENT_CREDENTIALS_KEY = "__oauth_client_credentials__"
DEFAULT_SERVICE_NAME = "google-workspace-mcp"


def get_client_credentials(keyring_module, service_name):
    """Retrieve OAuth client credentials from Keychain."""
    try:
        data = keyring_module.get_password(service_name, CLIENT_CREDENTIALS_KEY)
        if data:
            creds = json.loads(data)
            if creds.get("client_id") and creds.get("client_secret"):
                return creds
    except Exception:
        pass
    return None


def store_client_credentials(keyring_module, service_name, client_id, client_secret):
    """Store OAuth client credentials in Keychain."""
    try:
        data = json.dumps({
            "client_id": client_id,
            "client_secret": client_secret
        })
        keyring_module.set_password(service_name, CLIENT_CREDENTIALS_KEY, data)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def delete_client_credentials(keyring_module, service_name):
    """Delete OAuth client credentials from Keychain."""
    try:
        keyring_module.delete_password(service_name, CLIENT_CREDENTIALS_KEY)
        return True
    except Exception:
        return True  # Already deleted or doesn't exist


def main():
    parser = argparse.ArgumentParser(
        description="Store Google OAuth credentials in macOS Keychain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--service",
        default=os.getenv("GOOGLE_MCP_KEYCHAIN_SERVICE", DEFAULT_SERVICE_NAME),
        help="Keychain service name for credential isolation (default: google-workspace-mcp)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete stored credentials from Keychain"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show info about stored credentials (not the actual secrets)"
    )
    parser.add_argument(
        "--client-id",
        help="OAuth Client ID (will prompt if not provided)"
    )
    parser.add_argument(
        "--client-secret",
        help="OAuth Client Secret (will prompt securely if not provided)"
    )

    args = parser.parse_args()

    # Import keyring
    try:
        import keyring
        import keyring.errors
    except ImportError:
        print("Error: keyring library not installed.")
        print("Install with: python3 -m pip install keyring")
        sys.exit(1)

    # Check keyring backend
    backend = keyring.get_keyring()
    print(f"Keyring backend: {type(backend).__name__}")

    if "fail" in type(backend).__name__.lower():
        print("Error: No working keyring backend found.")
        print("On macOS, this should use the system Keychain automatically.")
        sys.exit(1)

    service_name = args.service
    print(f"Service name: {service_name}")
    print()

    if args.show:
        # Show stored credentials info
        creds = get_client_credentials(keyring, service_name)
        if creds:
            client_id = creds.get("client_id", "")
            # Mask most of the client ID for security
            if len(client_id) > 20:
                masked_id = client_id[:10] + "..." + client_id[-20:]
            else:
                masked_id = client_id[:5] + "..."
            print(f"✓ Client credentials found in Keychain")
            print(f"  Client ID: {masked_id}")
            print(f"  Client Secret: ******* (stored securely)")
        else:
            print("✗ No client credentials found in Keychain")
        return

    if args.delete:
        # Delete stored credentials
        confirm = input(f"Delete credentials from Keychain service '{service_name}'? [y/N]: ")
        if confirm.lower() == 'y':
            if delete_client_credentials(keyring, service_name):
                print("✓ Credentials deleted from Keychain")
            else:
                print("✗ Failed to delete credentials")
                sys.exit(1)
        else:
            print("Cancelled")
        return

    # Store new credentials
    print("This script will store your Google OAuth credentials in macOS Keychain.")
    print("The credentials will be encrypted and protected by your login password.")
    print()

    # Get existing credentials to show if updating
    existing = get_client_credentials(keyring, service_name)
    if existing:
        print("⚠ Existing credentials found. They will be replaced.")
        print()

    # Get Client ID
    client_id = args.client_id
    if not client_id:
        client_id = input("Enter OAuth Client ID: ").strip()

    if not client_id:
        print("Error: Client ID is required")
        sys.exit(1)

    if not client_id.endswith(".apps.googleusercontent.com"):
        print("Warning: Client ID doesn't look like a Google OAuth client ID")
        print("         (expected format: xxxxxx.apps.googleusercontent.com)")
        confirm = input("Continue anyway? [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled")
            sys.exit(1)

    # Get Client Secret
    client_secret = args.client_secret
    if not client_secret:
        client_secret = getpass.getpass("Enter OAuth Client Secret: ").strip()

    if not client_secret:
        print("Error: Client Secret is required")
        sys.exit(1)

    # Store credentials
    print()
    print("Storing credentials in Keychain...")

    if store_client_credentials(keyring, service_name, client_id, client_secret):
        print()
        print("✓ Credentials stored successfully in macOS Keychain!")
        print()
        print("You can now use this MCP server with Keychain storage.")
        print()
        print("Your .mcp.json should look like this:")
        print()
        print('''{
  "mcpServers": {
    "google-workspace": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/the-accidental-product-guy/google_workspace_mcp",
        "workspace-mcp"
      ],
      "env": {
        "GOOGLE_MCP_CREDENTIAL_BACKEND": "keychain",
        "GOOGLE_MCP_KEYCHAIN_SERVICE": "''' + service_name + '''"
      }
    }
  }
}''')
        print()
        print("Note: No OAuth credentials in the config file - all stored securely in Keychain!")
    else:
        print("✗ Failed to store credentials in Keychain")
        sys.exit(1)


if __name__ == "__main__":
    main()
