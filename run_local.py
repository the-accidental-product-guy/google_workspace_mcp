#!/usr/bin/env python3
"""
Local development wrapper that runs the MCP server from local source code.

This script reads OAuth credentials from Keychain and runs main.py directly,
allowing you to test changes without pushing to GitHub.

Usage in .mcp.json:
{
  "mcpServers": {
    "google-workspace": {
      "command": "python3",
      "args": ["/path/to/run_local.py"],
      "env": {
        "GOOGLE_MCP_KEYCHAIN_SERVICE": "google-mcp-sd-project"
      }
    }
  }
}
"""

import os
import sys
import json
import subprocess

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SERVICE_NAME = "google-workspace-mcp"
CLIENT_CREDENTIALS_KEY = "__oauth_client_credentials__"


def get_credentials_from_keychain(service_name):
    """Read OAuth credentials from macOS Keychain."""
    try:
        import keyring
        data = keyring.get_password(service_name, CLIENT_CREDENTIALS_KEY)
        if data:
            return json.loads(data)
    except ImportError:
        print("Error: keyring not installed. Run: python3 -m pip install keyring", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading from Keychain: {e}", file=sys.stderr)
    return None


def main():
    # Get service name from environment
    service_name = os.getenv("GOOGLE_MCP_KEYCHAIN_SERVICE", DEFAULT_SERVICE_NAME)

    # Read credentials from Keychain
    creds = get_credentials_from_keychain(service_name)

    if not creds:
        print(f"Error: No credentials found in Keychain for service '{service_name}'", file=sys.stderr)
        print(f"Run: python3 setup_keychain.py --service {service_name}", file=sys.stderr)
        sys.exit(1)

    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")

    if not client_id or not client_secret:
        print("Error: Invalid credentials in Keychain (missing client_id or client_secret)", file=sys.stderr)
        sys.exit(1)

    # Set up environment with credentials
    env = os.environ.copy()
    env["GOOGLE_OAUTH_CLIENT_ID"] = client_id
    env["GOOGLE_OAUTH_CLIENT_SECRET"] = client_secret
    env["GOOGLE_MCP_CREDENTIAL_BACKEND"] = "keychain"
    env["GOOGLE_MCP_KEYCHAIN_SERVICE"] = service_name

    # Run main.py using uv to handle dependencies
    uv_path = os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv_path):
        import shutil
        uv_path = shutil.which("uv")

    if not uv_path:
        print("Error: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        sys.exit(1)

    # Use uv run to execute main.py with proper dependencies
    cmd = [
        uv_path, "run",
        "--directory", PROJECT_ROOT,
        "python", "main.py"
    ]

    # Replace current process with the MCP server
    os.execve(uv_path, cmd, env)


if __name__ == "__main__":
    main()
