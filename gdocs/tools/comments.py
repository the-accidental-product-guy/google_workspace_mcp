"""
Google Docs Comment Operations

This module provides MCP tools for document comment operations.
These are generated using the shared comment tools factory.
"""

import logging

from core.comments import create_comment_tools

logger = logging.getLogger(__name__)

# Create comment management tools for documents using the shared factory
# This registers tools with server as: read_document_comments, create_document_comment, etc.
_comment_tools = create_comment_tools("document", "document_id")

# Extract and export the functions with consistent naming
# The actual MCP tool names are: read_document_comments, create_document_comment, etc.
read_doc_comments = _comment_tools["read_comments"]
create_doc_comment = _comment_tools["create_comment"]
reply_to_comment = _comment_tools["reply_to_comment"]
resolve_comment = _comment_tools["resolve_comment"]
