"""
Google Docs Named Ranges Operations

This module provides MCP tools for managing named ranges in Google Docs documents.
Named ranges allow you to identify and reference specific content regions by character indices.

Note: These tools are distinct from Google Sheets named ranges which reference cell ranges.
"""

import logging
import asyncio
import json
from typing import Any

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_named_range_request,
    create_delete_named_range_request,
    create_replace_named_range_content_request,
)
from gdocs.managers import ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("create_doc_named_range", service_type="docs")
@require_google_service("docs", "docs_write")
async def create_doc_named_range(
    service: Any,
    user_google_email: str,
    document_id: str,
    name: str,
    start_index: int,
    end_index: int,
) -> str:
    """
    Creates a named range in a Google Doc to identify a specific content region.

    Named ranges in Google Docs reference text by character indices (not cell ranges like Sheets).
    Use cases include:
    - Reference and update content by name instead of indices
    - Create bookmarks/anchors in the document
    - Build dynamic templates with replaceable placeholders

    Args:
        user_google_email: User's Google email address
        document_id: ID of the Google Doc to update
        name: Name for the range (names don't need to be unique)
        start_index: Start character position of the range
        end_index: End character position of the range (exclusive)

    Returns:
        str: Confirmation message with the created named range ID
    """
    logger.info(
        f"[create_doc_named_range] Doc={document_id}, name={name}, range={start_index}-{end_index}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index_range(start_index, end_index)
    if not is_valid:
        return f"Error: {error_msg}"

    if not name or not name.strip():
        return "Error: Named range name cannot be empty"

    requests = [create_named_range_request(name, start_index, end_index)]

    result = await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Extract the created named range ID from the response
    named_range_id = None
    if "replies" in result and result["replies"]:
        for reply in result["replies"]:
            if "createNamedRange" in reply:
                named_range_id = reply["createNamedRange"].get("namedRangeId")
                break

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    id_info = f" (ID: {named_range_id})" if named_range_id else ""
    return f"Created named range '{name}'{id_info} for range {start_index}-{end_index} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("delete_doc_named_range", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_doc_named_range(
    service: Any,
    user_google_email: str,
    document_id: str,
    named_range_id: str = None,
    name: str = None,
) -> str:
    """
    Deletes a named range from a Google Doc.

    You can specify either the named_range_id or the name to identify which range to delete.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the Google Doc to update
        named_range_id: ID of the named range to delete
        name: Name of the named range to delete (alternative to ID)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[delete_doc_named_range] Doc={document_id}, id={named_range_id}, name={name}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not named_range_id and not name:
        return "Error: Either named_range_id or name must be provided"

    requests = [create_delete_named_range_request(named_range_id, name)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    identifier = named_range_id or f"name '{name}'"
    return f"Deleted named range {identifier} from document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("replace_doc_named_range_content", service_type="docs")
@require_google_service("docs", "docs_write")
async def replace_doc_named_range_content(
    service: Any,
    user_google_email: str,
    document_id: str,
    text: str,
    named_range_id: str = None,
    name: str = None,
) -> str:
    """
    Replaces all content within a named range in a Google Doc with new text.

    This is useful for template processing - create named ranges for placeholders
    and then replace them with actual content.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the Google Doc to update
        text: New text to insert (replaces existing content)
        named_range_id: ID of the named range
        name: Name of the named range (alternative to ID)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[replace_doc_named_range_content] Doc={document_id}, id={named_range_id}, name={name}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not named_range_id and not name:
        return "Error: Either named_range_id or name must be provided"

    requests = [create_replace_named_range_content_request(text, named_range_id, name)]

    result = await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Get replacement count from response
    replacement_count = 0
    if "replies" in result and result["replies"]:
        for reply in result["replies"]:
            if "replaceNamedRangeContent" in reply:
                # The API doesn't return count, but we know at least one was replaced
                replacement_count = 1
                break

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    identifier = named_range_id or f"'{name}'"
    text_preview = text[:50] + "..." if len(text) > 50 else text
    return f"Replaced content in named range {identifier} with '{text_preview}' in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("list_doc_named_ranges", is_read_only=True, service_type="docs")
@require_google_service("docs", "docs_read")
async def list_doc_named_ranges(
    service: Any,
    user_google_email: str,
    document_id: str,
) -> str:
    """
    Lists all named ranges in a Google Doc.

    Named ranges in Google Docs reference text content by character indices,
    unlike Google Sheets named ranges which reference cell ranges.

    Returns information about each named range including:
    - Name
    - ID
    - Content ranges (start and end character indices)

    Args:
        user_google_email: User's Google email address
        document_id: ID of the Google Doc to query

    Returns:
        str: JSON list of all named ranges with their details
    """
    logger.info(f"[list_doc_named_ranges] Doc={document_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    doc = await asyncio.to_thread(
        service.documents().get(documentId=document_id).execute
    )

    named_ranges = doc.get("namedRanges", {})

    if not named_ranges:
        link = f"https://docs.google.com/document/d/{document_id}/edit"
        return f"No named ranges found in document {document_id}. Link: {link}"

    # Format the named ranges for output
    result = []
    for name, range_data in named_ranges.items():
        ranges_info = range_data.get("namedRanges", [])
        for nr in ranges_info:
            range_entry = {
                "name": name,
                "namedRangeId": nr.get("namedRangeId"),
                "ranges": []
            }
            for r in nr.get("ranges", []):
                range_entry["ranges"].append({
                    "startIndex": r.get("startIndex"),
                    "endIndex": r.get("endIndex"),
                    "segmentId": r.get("segmentId")
                })
            result.append(range_entry)

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Found {len(result)} named range(s) in document {document_id}:\n\n{json.dumps(result, indent=2)}\n\nLink: {link}"
