"""
Google Docs Content Operations

This module provides MCP tools for text content operations including
insertion, modification, find/replace, and batch updates.
"""

import logging
import asyncio
from typing import List, Dict, Any

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_insert_text_request,
    create_delete_range_request,
    create_format_text_request,
    create_find_replace_request,
    create_insert_person_request,
)
from gdocs.managers import ValidationManager, BatchOperationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("modify_doc_text", service_type="docs")
@require_google_service("docs", "docs_write")
async def modify_doc_text(
    service: Any,
    user_google_email: str,
    document_id: str,
    start_index: int,
    end_index: int = None,
    text: str = None,
    bold: bool = None,
    italic: bool = None,
    underline: bool = None,
    font_size: int = None,
    font_family: str = None,
    text_color: str = None,
    background_color: str = None,
) -> str:
    """
    Modifies text in a Google Doc - can insert/replace text and/or apply formatting in a single operation.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        start_index: Start position for operation (0-based)
        end_index: End position for text replacement/formatting (if not provided with text, text is inserted)
        text: New text to insert or replace with (optional - can format existing text without changing it)
        bold: Whether to make text bold (True/False/None to leave unchanged)
        italic: Whether to make text italic (True/False/None to leave unchanged)
        underline: Whether to underline text (True/False/None to leave unchanged)
        font_size: Font size in points
        font_family: Font family name (e.g., "Arial", "Times New Roman")
        text_color: Foreground text color (#RRGGBB)
        background_color: Background/highlight color (#RRGGBB)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[modify_doc_text] Doc={document_id}, start={start_index}, end={end_index}, text={text is not None}, "
        f"formatting={any([bold, italic, underline, font_size, font_family, text_color, background_color])}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if text is None and not any(
        [
            bold is not None,
            italic is not None,
            underline is not None,
            font_size,
            font_family,
            text_color,
            background_color,
        ]
    ):
        return "Error: Must provide either 'text' to insert/replace, or formatting parameters (bold, italic, underline, font_size, font_family, text_color, background_color)."

    if any(
        [
            bold is not None,
            italic is not None,
            underline is not None,
            font_size,
            font_family,
            text_color,
            background_color,
        ]
    ):
        is_valid, error_msg = validator.validate_text_formatting_params(
            bold,
            italic,
            underline,
            font_size,
            font_family,
            text_color,
            background_color,
        )
        if not is_valid:
            return f"Error: {error_msg}"

        if end_index is None:
            return "Error: 'end_index' is required when applying formatting."

        is_valid, error_msg = validator.validate_index_range(start_index, end_index)
        if not is_valid:
            return f"Error: {error_msg}"

    requests = []
    operations = []

    # Handle text insertion/replacement
    if text is not None:
        if end_index is not None and end_index > start_index:
            if start_index == 0:
                requests.append(create_insert_text_request(1, text))
                adjusted_end = end_index + len(text)
                requests.append(
                    create_delete_range_request(1 + len(text), adjusted_end)
                )
                operations.append(
                    f"Replaced text from index {start_index} to {end_index}"
                )
            else:
                requests.extend(
                    [
                        create_delete_range_request(start_index, end_index),
                        create_insert_text_request(start_index, text),
                    ]
                )
                operations.append(
                    f"Replaced text from index {start_index} to {end_index}"
                )
        else:
            actual_index = 1 if start_index == 0 else start_index
            requests.append(create_insert_text_request(actual_index, text))
            operations.append(f"Inserted text at index {start_index}")

    # Handle formatting
    if any(
        [
            bold is not None,
            italic is not None,
            underline is not None,
            font_size,
            font_family,
            text_color,
            background_color,
        ]
    ):
        format_start = start_index
        format_end = end_index

        if text is not None:
            if end_index is not None and end_index > start_index:
                format_end = start_index + len(text)
            else:
                actual_index = 1 if start_index == 0 else start_index
                format_start = actual_index
                format_end = actual_index + len(text)

        if format_start == 0:
            format_start = 1
        if format_end is not None and format_end <= format_start:
            format_end = format_start + 1

        requests.append(
            create_format_text_request(
                format_start,
                format_end,
                bold,
                italic,
                underline,
                font_size,
                font_family,
                text_color,
                background_color,
            )
        )

        format_details = []
        if bold is not None:
            format_details.append(f"bold={bold}")
        if italic is not None:
            format_details.append(f"italic={italic}")
        if underline is not None:
            format_details.append(f"underline={underline}")
        if font_size:
            format_details.append(f"font_size={font_size}")
        if font_family:
            format_details.append(f"font_family={font_family}")
        if text_color:
            format_details.append(f"text_color={text_color}")
        if background_color:
            format_details.append(f"background_color={background_color}")

        operations.append(
            f"Applied formatting ({', '.join(format_details)}) to range {format_start}-{format_end}"
        )

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    operation_summary = "; ".join(operations)
    text_info = f" Text length: {len(text)} characters." if text else ""
    return f"{operation_summary} in document {document_id}.{text_info} Link: {link}"


@server.tool()
@handle_http_errors("find_and_replace_doc", service_type="docs")
@require_google_service("docs", "docs_write")
async def find_and_replace_doc(
    service: Any,
    user_google_email: str,
    document_id: str,
    find_text: str,
    replace_text: str,
    match_case: bool = False,
) -> str:
    """
    Finds and replaces text throughout a Google Doc.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        find_text: Text to search for
        replace_text: Text to replace with
        match_case: Whether to match case exactly

    Returns:
        str: Confirmation message with replacement count
    """
    logger.info(
        f"[find_and_replace_doc] Doc={document_id}, find='{find_text}', replace='{replace_text}'"
    )

    requests = [create_find_replace_request(find_text, replace_text, match_case)]

    result = await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    replacements = 0
    if "replies" in result and result["replies"]:
        reply = result["replies"][0]
        if "replaceAllText" in reply:
            replacements = reply["replaceAllText"].get("occurrencesChanged", 0)

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Replaced {replacements} occurrence(s) of '{find_text}' with '{replace_text}' in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("batch_update_doc", service_type="docs")
@require_google_service("docs", "docs_write")
async def batch_update_doc(
    service: Any,
    user_google_email: str,
    document_id: str,
    operations: List[Dict[str, Any]],
) -> str:
    """
    Executes multiple document operations in a single atomic batch update.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        operations: List of operation dictionaries. Each operation should contain:
                   - type: Operation type ('insert_text', 'delete_text', 'replace_text', 'format_text', 'insert_table', 'insert_page_break')
                   - Additional parameters specific to each operation type

    Example operations:
        [
            {"type": "insert_text", "index": 1, "text": "Hello World"},
            {"type": "format_text", "start_index": 1, "end_index": 12, "bold": true},
            {"type": "insert_table", "index": 20, "rows": 2, "columns": 3}
        ]

    Returns:
        str: Confirmation message with batch operation results
    """
    logger.debug(f"[batch_update_doc] Doc={document_id}, operations={len(operations)}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_batch_operations(operations)
    if not is_valid:
        return f"Error: {error_msg}"

    batch_manager = BatchOperationManager(service)

    success, message, metadata = await batch_manager.execute_batch_operations(
        document_id, operations
    )

    if success:
        link = f"https://docs.google.com/document/d/{document_id}/edit"
        replies_count = metadata.get("replies_count", 0)
        return f"{message} on document {document_id}. API replies: {replies_count}. Link: {link}"
    else:
        return f"Error: {message}"


@server.tool()
@handle_http_errors("mention_person", service_type="docs")
@require_google_service("docs", "docs_write")
async def mention_person(
    service: Any,
    user_google_email: str,
    document_id: str,
    index: int,
    person_email: str,
) -> str:
    """
    Inserts an @ mention (person chip) in the document.

    This creates an interactive person chip that links to the mentioned person's
    Google profile and can trigger notifications.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        index: Position to insert the mention (use inspect_doc_structure to find safe index)
        person_email: Email address of the person to mention

    Returns:
        str: Confirmation message with insertion details
    """
    logger.info(
        f"[mention_person] Doc={document_id}, index={index}, person={person_email}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_index(index, "Index")
    if not is_valid:
        return f"Error: {error_msg}"

    # Adjust index if at document start
    actual_index = 1 if index == 0 else index

    requests = [create_insert_person_request(actual_index, person_email)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted mention of {person_email} at index {index} in document {document_id}. Link: {link}"
