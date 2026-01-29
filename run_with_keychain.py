#!/usr/bin/env python3
"""
Wrapper script that reads OAuth credentials from Keychain and runs the MCP server.

This solves the issue where uvx's isolated environment can't access Keychain directly.
The script reads credentials from Keychain, sets them as environment variables,
and then executes the MCP server.

Usage in .mcp.json:
{
  "mcpServers": {
    "google-workspace": {
      "command": "python3",
      "args": ["/path/to/run_with_keychain.py"],
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

    # Set credentials as environment variables for the MCP server
    env = os.environ.copy()
    env["GOOGLE_OAUTH_CLIENT_ID"] = client_id
    env["GOOGLE_OAUTH_CLIENT_SECRET"] = client_secret

    # Keep the keychain backend setting for token storage
    env["GOOGLE_MCP_CREDENTIAL_BACKEND"] = "keychain"
    env["GOOGLE_MCP_KEYCHAIN_SERVICE"] = service_name

    # Find uvx path
    uvx_path = os.path.expanduser("~/.local/bin/uvx")
    if not os.path.exists(uvx_path):
        # Try to find uvx in PATH
        import shutil
        uvx_path = shutil.which("uvx")

    if not uvx_path:
        print("Error: uvx not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        sys.exit(1)

    # Run the MCP server with credentials in environment
    cmd = [
        uvx_path,
        "--from", "git+https://github.com/the-accidental-product-guy/google_workspace_mcp",
        "workspace-mcp"
    ]

    # Execute, replacing this process
    os.execve(uvx_path, cmd, env)


if __name__ == "__main__":
    main()
