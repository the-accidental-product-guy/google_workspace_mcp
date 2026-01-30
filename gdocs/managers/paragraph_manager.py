"""
Paragraph Manager

This module provides high-level paragraph formatting operations for Google Docs,
handling complex multi-step paragraph styling and list management.
"""

import logging
import asyncio
from typing import Any, Dict, List, Tuple, Optional

from gdocs.docs_helpers import (
    create_update_paragraph_style_request,
    create_delete_paragraph_bullets_request,
    create_bullet_list_request,
)

logger = logging.getLogger(__name__)


class ParagraphManager:
    """
    High-level manager for Google Docs paragraph operations.

    Handles complex paragraph formatting including:
    - Multi-range paragraph style updates
    - List type conversions
    - Bulk paragraph formatting
    """

    def __init__(self, service):
        """
        Initialize the paragraph manager.

        Args:
            service: Google Docs API service instance
        """
        self.service = service

    async def update_paragraph_styles(
        self,
        document_id: str,
        ranges: List[Tuple[int, int]],
        style_options: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Apply paragraph style updates to multiple ranges.

        Args:
            document_id: ID of the document to update
            ranges: List of (start_index, end_index) tuples
            style_options: Dictionary of style options:
                - alignment: "START", "CENTER", "END", "JUSTIFIED"
                - line_spacing: float multiplier (1.0, 1.5, 2.0)
                - space_above: points
                - space_below: points
                - indent_first_line: points
                - indent_start: points
                - indent_end: points
                - named_style_type: "NORMAL_TEXT", "HEADING_1", etc.

        Returns:
            Tuple of (success, message, metadata)
        """
        logger.info(f"Updating paragraph styles for {len(ranges)} range(s)")

        if not ranges:
            return False, "No ranges provided", {}

        try:
            requests = []
            for start_idx, end_idx in ranges:
                request = create_update_paragraph_style_request(
                    start_index=start_idx,
                    end_index=end_idx,
                    alignment=style_options.get("alignment"),
                    line_spacing=style_options.get("line_spacing"),
                    space_above=style_options.get("space_above"),
                    space_below=style_options.get("space_below"),
                    indent_first_line=style_options.get("indent_first_line"),
                    indent_start=style_options.get("indent_start"),
                    indent_end=style_options.get("indent_end"),
                    named_style_type=style_options.get("named_style_type"),
                )
                requests.append(request)

            await asyncio.to_thread(
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute
            )

            metadata = {
                "ranges_updated": len(ranges),
                "style_options": list(style_options.keys()),
            }

            return True, f"Successfully updated {len(ranges)} paragraph range(s)", metadata

        except Exception as e:
            logger.error(f"Failed to update paragraph styles: {str(e)}")
            return False, f"Failed to update paragraph styles: {str(e)}", {}

    async def convert_to_list(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        list_type: str = "UNORDERED",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Convert paragraphs to a bullet or numbered list.

        Args:
            document_id: ID of the document to update
            start_index: Start of text range
            end_index: End of text range
            list_type: "UNORDERED" for bullets, "ORDERED" for numbers

        Returns:
            Tuple of (success, message, metadata)
        """
        logger.info(
            f"Converting range {start_index}-{end_index} to {list_type} list"
        )

        if list_type not in ["UNORDERED", "ORDERED"]:
            return False, f"Invalid list type: {list_type}", {}

        try:
            requests = [create_bullet_list_request(start_index, end_index, list_type)]

            await asyncio.to_thread(
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute
            )

            metadata = {
                "start_index": start_index,
                "end_index": end_index,
                "list_type": list_type,
            }

            return True, f"Converted range to {list_type.lower()} list", metadata

        except Exception as e:
            logger.error(f"Failed to convert to list: {str(e)}")
            return False, f"Failed to convert to list: {str(e)}", {}

    async def remove_list_formatting(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Remove bullet/numbered list formatting from paragraphs.

        Args:
            document_id: ID of the document to update
            start_index: Start of text range
            end_index: End of text range

        Returns:
            Tuple of (success, message, metadata)
        """
        logger.info(f"Removing list formatting from range {start_index}-{end_index}")

        try:
            requests = [create_delete_paragraph_bullets_request(start_index, end_index)]

            await asyncio.to_thread(
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute
            )

            metadata = {
                "start_index": start_index,
                "end_index": end_index,
            }

            return True, "Removed list formatting", metadata

        except Exception as e:
            logger.error(f"Failed to remove list formatting: {str(e)}")
            return False, f"Failed to remove list formatting: {str(e)}", {}

    async def apply_heading_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        heading_level: int,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Apply heading style to paragraphs.

        Args:
            document_id: ID of the document to update
            start_index: Start of text range
            end_index: End of text range
            heading_level: 1-6 for headings, 0 for normal text

        Returns:
            Tuple of (success, message, metadata)
        """
        if heading_level == 0:
            style_type = "NORMAL_TEXT"
        elif 1 <= heading_level <= 6:
            style_type = f"HEADING_{heading_level}"
        else:
            return False, f"Invalid heading level: {heading_level}. Use 0-6.", {}

        logger.info(f"Applying {style_type} to range {start_index}-{end_index}")

        try:
            requests = [
                create_update_paragraph_style_request(
                    start_index=start_index,
                    end_index=end_index,
                    named_style_type=style_type,
                )
            ]

            await asyncio.to_thread(
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute
            )

            metadata = {
                "start_index": start_index,
                "end_index": end_index,
                "style_type": style_type,
            }

            return True, f"Applied {style_type} style", metadata

        except Exception as e:
            logger.error(f"Failed to apply heading style: {str(e)}")
            return False, f"Failed to apply heading style: {str(e)}", {}
