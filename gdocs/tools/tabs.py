"""
Google Docs Document Tabs Operations

This module provides MCP tools for managing document tabs (multi-tab documents).
Document tabs allow a single Google Doc to contain multiple tab pages.
"""

import logging
import asyncio
import json
from typing import Any, Optional

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_add_document_tab_request,
    create_delete_tab_request,
    create_update_tab_properties_request,
)
from gdocs.managers import ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("add_document_tab", service_type="docs")
@require_google_service("docs", "docs_write")
async def add_document_tab(
    service: Any,
    user_google_email: str,
    document_id: str,
    title: str,
    parent_tab_id: str = None,
    insert_index: int = None,
) -> str:
    """
    Creates a new tab in the document.

    Document tabs allow organizing content into multiple pages within a single document.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        title: Title for the new tab
        parent_tab_id: ID of parent tab for nested tabs (optional)
        insert_index: Position to insert the tab (optional, defaults to end)

    Returns:
        str: Confirmation message with the created tab ID
    """
    logger.info(
        f"[add_document_tab] Doc={document_id}, title={title}, parent={parent_tab_id}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not title or not title.strip():
        return "Error: Tab title cannot be empty"

    # Build tab properties - all optional fields go inside tabProperties
    tab_properties = {"title": title}
    if parent_tab_id:
        tab_properties["parentTabId"] = parent_tab_id
    if insert_index is not None:
        tab_properties["index"] = insert_index

    requests = [create_add_document_tab_request(tab_properties)]

    result = await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Extract the created tab ID from the response
    tab_id = None
    if "replies" in result and result["replies"]:
        for reply in result["replies"]:
            if "addDocumentTab" in reply:
                tab_id = reply["addDocumentTab"].get("tabId")
                break

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    id_info = f" (ID: {tab_id})" if tab_id else ""
    parent_info = f" under parent '{parent_tab_id}'" if parent_tab_id else ""
    return f"Created tab '{title}'{id_info}{parent_info} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("delete_document_tab", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_document_tab(
    service: Any,
    user_google_email: str,
    document_id: str,
    tab_id: str,
) -> str:
    """
    Deletes a tab from the document.

    Note: You cannot delete the last remaining tab in a document.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        tab_id: ID of the tab to delete (use list_document_tabs to find IDs)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[delete_document_tab] Doc={document_id}, tab_id={tab_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not tab_id:
        return "Error: tab_id is required"

    requests = [create_delete_tab_request(tab_id)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted tab '{tab_id}' from document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("update_tab_properties", service_type="docs")
@require_google_service("docs", "docs_write")
async def update_tab_properties(
    service: Any,
    user_google_email: str,
    document_id: str,
    tab_id: str,
    title: str = None,
) -> str:
    """
    Updates the properties of a document tab.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        tab_id: ID of the tab to update
        title: New title for the tab (optional)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[update_tab_properties] Doc={document_id}, tab_id={tab_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not tab_id:
        return "Error: tab_id is required"

    if title is None:
        return "Error: At least one property (title) must be provided"

    # Build properties to update
    properties = {}
    if title is not None:
        properties["title"] = title

    requests = [create_update_tab_properties_request(tab_id, properties)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Build description of changes
    changes = []
    if title is not None:
        changes.append(f"title='{title}'")

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Updated tab '{tab_id}' ({', '.join(changes)}) in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("list_document_tabs", is_read_only=True, service_type="docs")
@require_google_service("docs", "docs_read")
async def list_document_tabs(
    service: Any,
    user_google_email: str,
    document_id: str,
) -> str:
    """
    Lists all tabs in the document with their properties.

    Returns information about each tab including:
    - Tab ID
    - Title
    - Parent tab ID (for nested tabs)
    - Position index

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to query

    Returns:
        str: JSON list of all tabs with their details
    """
    logger.info(f"[list_document_tabs] Doc={document_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    doc = await asyncio.to_thread(
        service.documents()
        .get(documentId=document_id, includeTabsContent=True)
        .execute
    )

    tabs = doc.get("tabs", [])

    if not tabs:
        link = f"https://docs.google.com/document/d/{document_id}/edit"
        return f"No tabs found in document {document_id}. Link: {link}"

    def process_tabs(tab_list, parent_id=None, level=0):
        """Recursively process tabs and their children."""
        result = []
        for idx, tab in enumerate(tab_list):
            props = tab.get("tabProperties", {})
            tab_info = {
                "tabId": props.get("tabId"),
                "title": props.get("title", "Untitled"),
                "index": props.get("index", idx),
                "parentTabId": parent_id,
                "nestingLevel": level,
            }
            result.append(tab_info)

            # Process child tabs
            child_tabs = tab.get("childTabs", [])
            if child_tabs:
                result.extend(process_tabs(child_tabs, props.get("tabId"), level + 1))

        return result

    tabs_info = process_tabs(tabs)

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Found {len(tabs_info)} tab(s) in document {document_id}:\n\n{json.dumps(tabs_info, indent=2)}\n\nLink: {link}"
