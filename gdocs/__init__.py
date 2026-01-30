"""
Google Docs MCP Package

This package provides MCP tools for interacting with Google Docs API,
organized into domain-specific modules.
"""

# Import all tools from the modular tools package
from gdocs.tools import *

# Also expose helper modules for direct use if needed
from gdocs import docs_helpers
from gdocs import docs_structure
from gdocs import docs_tables
from gdocs import managers
