"""
Google Docs Formatting Operations

This module provides MCP tools for paragraph and text formatting operations.
"""

import logging
import asyncio
from typing import Any, Optional

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_update_paragraph_style_request,
    create_delete_paragraph_bullets_request,
)
from gdocs.managers import ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("update_paragraph_style", service_type="docs")
@require_google_service("docs", "docs_write")
async def update_paragraph_style(
    service: Any,
    user_google_email: str,
    document_id: str,
    start_index: int,
    end_index: int,
    alignment: str = None,
    line_spacing: float = None,
    space_above: float = None,
    space_below: float = None,
    indent_first_line: float = None,
    indent_start: float = None,
    indent_end: float = None,
    heading_id: str = None,
    named_style_type: str = None,
) -> str:
    """
    Updates paragraph styling (alignment, spacing, indentation, headings).

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        start_index: Start position of paragraph(s) to style
        end_index: End position of paragraph(s) to style
        alignment: Text alignment ("START", "CENTER", "END", "JUSTIFIED")
        line_spacing: Line spacing multiplier (e.g., 1.0, 1.5, 2.0)
        space_above: Space before paragraph in points
        space_below: Space after paragraph in points
        indent_first_line: First line indent in points
        indent_start: Left/start indent in points
        indent_end: Right/end indent in points
        heading_id: Heading ID for linking (advanced)
        named_style_type: Named style ("NORMAL_TEXT", "TITLE", "SUBTITLE", "HEADING_1" through "HEADING_6")

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[update_paragraph_style] Doc={document_id}, range={start_index}-{end_index}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index_range(start_index, end_index)
    if not is_valid:
        return f"Error: {error_msg}"

    # Check that at least one style option is provided
    if not any([
        alignment, line_spacing, space_above, space_below,
        indent_first_line, indent_start, indent_end,
        heading_id, named_style_type
    ]):
        return "Error: At least one paragraph style option must be provided"

    # Validate alignment if provided
    valid_alignments = ["START", "CENTER", "END", "JUSTIFIED"]
    if alignment and alignment not in valid_alignments:
        return f"Error: alignment must be one of {valid_alignments}"

    # Validate named_style_type if provided
    valid_styles = [
        "NORMAL_TEXT", "TITLE", "SUBTITLE",
        "HEADING_1", "HEADING_2", "HEADING_3",
        "HEADING_4", "HEADING_5", "HEADING_6"
    ]
    if named_style_type and named_style_type not in valid_styles:
        return f"Error: named_style_type must be one of {valid_styles}"

    requests = [create_update_paragraph_style_request(
        start_index=start_index,
        end_index=end_index,
        alignment=alignment,
        line_spacing=line_spacing,
        space_above=space_above,
        space_below=space_below,
        indent_first_line=indent_first_line,
        indent_start=indent_start,
        indent_end=indent_end,
        heading_id=heading_id,
        named_style_type=named_style_type,
    )]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Build description of changes
    changes = []
    if alignment:
        changes.append(f"alignment={alignment}")
    if line_spacing:
        changes.append(f"line_spacing={line_spacing}")
    if space_above is not None:
        changes.append(f"space_above={space_above}pt")
    if space_below is not None:
        changes.append(f"space_below={space_below}pt")
    if indent_first_line is not None:
        changes.append(f"first_line_indent={indent_first_line}pt")
    if indent_start is not None:
        changes.append(f"left_indent={indent_start}pt")
    if indent_end is not None:
        changes.append(f"right_indent={indent_end}pt")
    if named_style_type:
        changes.append(f"style={named_style_type}")

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Updated paragraph style ({', '.join(changes)}) for range {start_index}-{end_index} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("remove_paragraph_bullets", service_type="docs")
@require_google_service("docs", "docs_write")
async def remove_paragraph_bullets(
    service: Any,
    user_google_email: str,
    document_id: str,
    start_index: int,
    end_index: int,
) -> str:
    """
    Removes bullet or numbered list formatting from paragraphs.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        start_index: Start position of paragraph(s)
        end_index: End position of paragraph(s)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[remove_paragraph_bullets] Doc={document_id}, range={start_index}-{end_index}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index_range(start_index, end_index)
    if not is_valid:
        return f"Error: {error_msg}"

    requests = [create_delete_paragraph_bullets_request(start_index, end_index)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Removed bullet/list formatting from range {start_index}-{end_index} in document {document_id}. Link: {link}"
