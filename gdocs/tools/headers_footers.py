"""
Google Docs Headers and Footers Operations

This module provides MCP tools for managing document headers and footers.
"""

import logging
import asyncio
from typing import Any

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_delete_header_request,
    create_delete_footer_request,
)
from gdocs.managers import HeaderFooterManager, ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("update_doc_headers_footers", service_type="docs")
@require_google_service("docs", "docs_write")
async def update_doc_headers_footers(
    service: Any,
    user_google_email: str,
    document_id: str,
    section_type: str,
    content: str,
    header_footer_type: str = "DEFAULT",
) -> str:
    """
    Updates headers or footers in a Google Doc.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        section_type: Type of section to update ("header" or "footer")
        content: Text content for the header/footer
        header_footer_type: Type of header/footer ("DEFAULT", "FIRST_PAGE_ONLY", "EVEN_PAGE")

    Returns:
        str: Confirmation message with update details
    """
    logger.info(f"[update_doc_headers_footers] Doc={document_id}, type={section_type}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_header_footer_params(
        section_type, header_footer_type
    )
    if not is_valid:
        return f"Error: {error_msg}"

    is_valid, error_msg = validator.validate_text_content(content)
    if not is_valid:
        return f"Error: {error_msg}"

    header_footer_manager = HeaderFooterManager(service)

    success, message = await header_footer_manager.update_header_footer_content(
        document_id, section_type, content, header_footer_type
    )

    if success:
        link = f"https://docs.google.com/document/d/{document_id}/edit"
        return f"{message}. Link: {link}"
    else:
        return f"Error: {message}"


@server.tool()
@handle_http_errors("delete_header", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_header(
    service: Any,
    user_google_email: str,
    document_id: str,
    header_id: str = None,
) -> str:
    """
    Deletes a header from the document.

    If header_id is not provided, attempts to delete the default header.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        header_id: Specific header ID to delete (optional - use inspect_doc_structure to find)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[delete_header] Doc={document_id}, header_id={header_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    # If no header_id provided, get the default header from document
    if not header_id:
        doc = await asyncio.to_thread(
            service.documents().get(documentId=document_id).execute
        )
        document_style = doc.get("documentStyle", {})
        header_id = document_style.get("defaultHeaderId")

        if not header_id:
            return "Error: No default header found in document. Provide a specific header_id or the document has no headers."

    requests = [create_delete_header_request(header_id)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted header '{header_id}' from document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("delete_footer", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_footer(
    service: Any,
    user_google_email: str,
    document_id: str,
    footer_id: str = None,
) -> str:
    """
    Deletes a footer from the document.

    If footer_id is not provided, attempts to delete the default footer.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        footer_id: Specific footer ID to delete (optional - use inspect_doc_structure to find)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(f"[delete_footer] Doc={document_id}, footer_id={footer_id}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    # If no footer_id provided, get the default footer from document
    if not footer_id:
        doc = await asyncio.to_thread(
            service.documents().get(documentId=document_id).execute
        )
        document_style = doc.get("documentStyle", {})
        footer_id = document_style.get("defaultFooterId")

        if not footer_id:
            return "Error: No default footer found in document. Provide a specific footer_id or the document has no footers."

    requests = [create_delete_footer_request(footer_id)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted footer '{footer_id}' from document {document_id}. Link: {link}"
