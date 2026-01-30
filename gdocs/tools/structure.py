"""
Google Docs Structure Operations

This module provides MCP tools for document structure operations including
sections, page breaks, footnotes, and document-level styling.
"""

import logging
import asyncio
from typing import Any, Optional

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_insert_text_request,
    create_insert_table_request,
    create_insert_page_break_request,
    create_bullet_list_request,
    create_insert_section_break_request,
    create_update_document_style_request,
    create_insert_footnote_request,
)
from gdocs.managers import ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("insert_doc_elements", service_type="docs")
@require_google_service("docs", "docs_write")
async def insert_doc_elements(
    service: Any,
    user_google_email: str,
    document_id: str,
    element_type: str,
    index: int,
    rows: int = None,
    columns: int = None,
    list_type: str = None,
    text: str = None,
) -> str:
    """
    Inserts structural elements like tables, lists, or page breaks into a Google Doc.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        element_type: Type of element to insert ("table", "list", "page_break")
        index: Position to insert element (0-based)
        rows: Number of rows for table (required for table)
        columns: Number of columns for table (required for table)
        list_type: Type of list ("UNORDERED", "ORDERED") (required for list)
        text: Initial text content for list items

    Returns:
        str: Confirmation message with insertion details
    """
    logger.info(
        f"[insert_doc_elements] Doc={document_id}, type={element_type}, index={index}"
    )

    # Handle the special case where we can't insert at the first section break
    if index == 0:
        logger.debug("Adjusting index from 0 to 1 to avoid first section break")
        index = 1

    requests = []

    if element_type == "table":
        if not rows or not columns:
            return "Error: 'rows' and 'columns' parameters are required for table insertion."

        requests.append(create_insert_table_request(index, rows, columns))
        description = f"table ({rows}x{columns})"

    elif element_type == "list":
        if not list_type:
            return "Error: 'list_type' parameter is required for list insertion ('UNORDERED' or 'ORDERED')."

        if not text:
            text = "List item"

        requests.extend(
            [
                create_insert_text_request(index, text + "\n"),
                create_bullet_list_request(index, index + len(text), list_type),
            ]
        )
        description = f"{list_type.lower()} list"

    elif element_type == "page_break":
        requests.append(create_insert_page_break_request(index))
        description = "page break"

    else:
        return f"Error: Unsupported element type '{element_type}'. Supported types: 'table', 'list', 'page_break'."

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted {description} at index {index} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("insert_section_break", service_type="docs")
@require_google_service("docs", "docs_write")
async def insert_section_break(
    service: Any,
    user_google_email: str,
    document_id: str,
    index: int,
    section_type: str = "NEXT_PAGE",
) -> str:
    """
    Inserts a section break at the specified position.

    Section breaks allow different formatting for different parts of the document
    (e.g., different headers/footers, column layouts, margins per section).

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        index: Position to insert section break (use inspect_doc_structure to find)
        section_type: Type of section break:
            - "NEXT_PAGE": Section starts on next page (default)
            - "CONTINUOUS": Section continues on same page

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[insert_section_break] Doc={document_id}, index={index}, type={section_type}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index(index, "Index")
    if not is_valid:
        return f"Error: {error_msg}"

    valid_types = ["NEXT_PAGE", "CONTINUOUS"]
    if section_type not in valid_types:
        return f"Error: section_type must be one of {valid_types}"

    # Adjust index if at document start
    actual_index = 1 if index == 0 else index

    requests = [create_insert_section_break_request(actual_index, section_type)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted {section_type} section break at index {index} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("update_document_style", service_type="docs")
@require_google_service("docs", "docs_write")
async def update_document_style(
    service: Any,
    user_google_email: str,
    document_id: str,
    margin_top: float = None,
    margin_bottom: float = None,
    margin_left: float = None,
    margin_right: float = None,
    page_width: float = None,
    page_height: float = None,
    use_first_page_header_footer: bool = None,
    use_even_page_header_footer: bool = None,
) -> str:
    """
    Updates document-level styling (margins, page size, header/footer settings).

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        margin_top: Top margin in points (72 points = 1 inch)
        margin_bottom: Bottom margin in points
        margin_left: Left margin in points
        margin_right: Right margin in points
        page_width: Page width in points (e.g., 612 for Letter, 595 for A4)
        page_height: Page height in points (e.g., 792 for Letter, 842 for A4)
        use_first_page_header_footer: Enable different first page header/footer
        use_even_page_header_footer: Enable different even/odd page headers/footers

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[update_document_style] Doc={document_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    # Check that at least one option is provided
    if not any([
        margin_top is not None, margin_bottom is not None,
        margin_left is not None, margin_right is not None,
        page_width is not None, page_height is not None,
        use_first_page_header_footer is not None,
        use_even_page_header_footer is not None
    ]):
        return "Error: At least one document style option must be provided"

    requests = [create_update_document_style_request(
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        margin_left=margin_left,
        margin_right=margin_right,
        page_width=page_width,
        page_height=page_height,
        use_first_page_header_footer=use_first_page_header_footer,
        use_even_page_header_footer=use_even_page_header_footer,
    )]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # Build description of changes
    changes = []
    if margin_top is not None:
        changes.append(f"margin_top={margin_top}pt")
    if margin_bottom is not None:
        changes.append(f"margin_bottom={margin_bottom}pt")
    if margin_left is not None:
        changes.append(f"margin_left={margin_left}pt")
    if margin_right is not None:
        changes.append(f"margin_right={margin_right}pt")
    if page_width is not None:
        changes.append(f"page_width={page_width}pt")
    if page_height is not None:
        changes.append(f"page_height={page_height}pt")
    if use_first_page_header_footer is not None:
        changes.append(f"first_page_header_footer={use_first_page_header_footer}")
    if use_even_page_header_footer is not None:
        changes.append(f"even_page_header_footer={use_even_page_header_footer}")

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Updated document style ({', '.join(changes)}) for document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("insert_footnote", service_type="docs")
@require_google_service("docs", "docs_write")
async def insert_footnote(
    service: Any,
    user_google_email: str,
    document_id: str,
    index: int,
    footnote_text: str = "",
) -> str:
    """
    Inserts a footnote reference at the specified position.

    The footnote number is automatically generated and the footnote text
    appears at the bottom of the page.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        index: Position to insert footnote reference (use inspect_doc_structure)
        footnote_text: Optional initial text for the footnote body

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[insert_footnote] Doc={document_id}, index={index}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index(index, "Index")
    if not is_valid:
        return f"Error: {error_msg}"

    # Adjust index if at document start
    actual_index = 1 if index == 0 else index

    requests = [create_insert_footnote_request(actual_index)]

    result = await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    # If footnote text provided, we need to add it to the footnote body
    # The footnote ID is returned in the response
    if footnote_text and "replies" in result and result["replies"]:
        for reply in result["replies"]:
            if "createFootnote" in reply:
                footnote_id = reply["createFootnote"].get("footnoteId")
                if footnote_id:
                    # Insert text into the footnote
                    text_requests = [{
                        "insertText": {
                            "location": {
                                "segmentId": footnote_id,
                                "index": 0
                            },
                            "text": footnote_text
                        }
                    }]
                    await asyncio.to_thread(
                        service.documents()
                        .batchUpdate(documentId=document_id, body={"requests": text_requests})
                        .execute
                    )
                break

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    text_info = f" with text '{footnote_text[:50]}...'" if len(footnote_text) > 50 else f" with text '{footnote_text}'" if footnote_text else ""
    return f"Inserted footnote at index {index}{text_info} in document {document_id}. Link: {link}"
