"""
Google Docs Media Operations

This module provides MCP tools for image and positioned object operations.
"""

import logging
import asyncio
from typing import Any

from auth.service_decorator import require_google_service, require_multiple_services
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_insert_image_request,
    create_replace_image_request,
    create_delete_positioned_object_request,
)
from gdocs.managers import ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("insert_doc_image", service_type="docs")
@require_multiple_services(
    [
        {"service_type": "docs", "scopes": "docs_write", "param_name": "docs_service"},
        {
            "service_type": "drive",
            "scopes": "drive_read",
            "param_name": "drive_service",
        },
    ]
)
async def insert_doc_image(
    docs_service: Any,
    drive_service: Any,
    user_google_email: str,
    document_id: str,
    image_source: str,
    index: int,
    width: int = 0,
    height: int = 0,
) -> str:
    """
    Inserts an image into a Google Doc from Drive or a URL.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        image_source: Drive file ID or public image URL
        index: Position to insert image (0-based)
        width: Image width in points (optional)
        height: Image height in points (optional)

    Returns:
        str: Confirmation message with insertion details
    """
    logger.info(
        f"[insert_doc_image] Doc={document_id}, source={image_source}, index={index}"
    )

    # Handle the special case where we can't insert at the first section break
    if index == 0:
        logger.debug("Adjusting index from 0 to 1 to avoid first section break")
        index = 1

    # Determine if source is a Drive file ID or URL
    is_drive_file = not (
        image_source.startswith("http://") or image_source.startswith("https://")
    )

    if is_drive_file:
        # Verify Drive file exists and get metadata
        try:
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(
                    fileId=image_source,
                    fields="id, name, mimeType",
                    supportsAllDrives=True,
                )
                .execute
            )
            mime_type = file_metadata.get("mimeType", "")
            if not mime_type.startswith("image/"):
                return f"Error: File {image_source} is not an image (MIME type: {mime_type})."

            image_uri = f"https://drive.google.com/uc?id={image_source}"
            source_description = f"Drive file {file_metadata.get('name', image_source)}"
        except Exception as e:
            return f"Error: Could not access Drive file {image_source}: {str(e)}"
    else:
        image_uri = image_source
        source_description = "URL image"

    requests = [create_insert_image_request(index, image_uri, width, height)]

    await asyncio.to_thread(
        docs_service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    size_info = ""
    if width or height:
        size_info = f" (size: {width or 'auto'}x{height or 'auto'} points)"

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted {source_description}{size_info} at index {index} in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("replace_image", service_type="docs")
@require_google_service("docs", "docs_write")
async def replace_image(
    service: Any,
    user_google_email: str,
    document_id: str,
    image_object_id: str,
    new_uri: str,
) -> str:
    """
    Replaces an existing image in the document with a new image.

    The new image will maintain the same position and sizing as the original.
    Use inspect_doc_structure to find inline object IDs.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        image_object_id: ID of the inline image object to replace
        new_uri: URI of the new image (public URL or Drive link)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[replace_image] Doc={document_id}, object_id={image_object_id}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not image_object_id:
        return "Error: image_object_id is required"

    if not new_uri:
        return "Error: new_uri is required"

    requests = [create_replace_image_request(image_object_id, new_uri)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Replaced image '{image_object_id}' with new image in document {document_id}. Link: {link}"


@server.tool()
@handle_http_errors("delete_positioned_object", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_positioned_object(
    service: Any,
    user_google_email: str,
    document_id: str,
    object_id: str,
) -> str:
    """
    Deletes a positioned object (floating image, drawing, etc.) from the document.

    Positioned objects are elements that "float" relative to text, as opposed to
    inline objects. Use inspect_doc_structure to find positioned object IDs.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        object_id: ID of the positioned object to delete

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[delete_positioned_object] Doc={document_id}, object_id={object_id}"
    )

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if not object_id:
        return "Error: object_id is required"

    requests = [create_delete_positioned_object_request(object_id)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted positioned object '{object_id}' from document {document_id}. Link: {link}"
