"""
Google Sheets Banding Tools

This module provides MCP tools for banding (alternating row colors) operations.
"""

import logging
import asyncio
from typing import Optional

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _parse_a1_range, _parse_hex_color

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("add_banding", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_banding(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    header_color: Optional[str] = None,
    first_band_color: Optional[str] = None,
    second_band_color: Optional[str] = None,
    footer_color: Optional[str] = None,
) -> str:
    """
    Adds alternating row colors (banding) to a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to apply banding (e.g., "A1:E100"). Required.
        header_color (Optional[str]): Hex color for header row (e.g., "#4285F4").
        first_band_color (Optional[str]): Hex color for odd rows (e.g., "#FFFFFF").
        second_band_color (Optional[str]): Hex color for even rows (e.g., "#E8F0FE").
        footer_color (Optional[str]): Hex color for footer row.

    Returns:
        str: Confirmation message with the banded range ID.
    """
    logger.info(
        f"[add_banding] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}"
    )

    # Get sheet metadata and parse range
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])
    grid_range = _parse_a1_range(range_name, sheets)

    banded_range = {"range": grid_range}

    # Build row properties
    row_properties = {}
    if header_color:
        header_color_parsed = _parse_hex_color(header_color)
        if header_color_parsed:
            row_properties["headerColor"] = header_color_parsed

    if first_band_color:
        first_band_color_parsed = _parse_hex_color(first_band_color)
        if first_band_color_parsed:
            row_properties["firstBandColor"] = first_band_color_parsed

    if second_band_color:
        second_band_color_parsed = _parse_hex_color(second_band_color)
        if second_band_color_parsed:
            row_properties["secondBandColor"] = second_band_color_parsed

    if footer_color:
        footer_color_parsed = _parse_hex_color(footer_color)
        if footer_color_parsed:
            row_properties["footerColor"] = footer_color_parsed

    if row_properties:
        banded_range["rowProperties"] = row_properties
    else:
        # Default banding colors
        banded_range["rowProperties"] = {
            "firstBandColor": {"red": 1, "green": 1, "blue": 1},  # White
            "secondBandColor": {"red": 0.9, "green": 0.9, "blue": 0.9},  # Light gray
        }

    request_body = {
        "requests": [
            {
                "addBanding": {
                    "bandedRange": banded_range,
                }
            }
        ]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract banded range ID from response
    replies = response.get("replies", [])
    banded_range_id = None
    if replies and "addBanding" in replies[0]:
        banded_range_id = replies[0]["addBanding"]["bandedRange"].get("bandedRangeId")

    id_desc = f" (ID: {banded_range_id})" if banded_range_id else ""
    return (
        f"Added banding to range '{range_name}'{id_desc} "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("update_banding", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_banding(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    banded_range_id: int,
    range_name: Optional[str] = None,
    header_color: Optional[str] = None,
    first_band_color: Optional[str] = None,
    second_band_color: Optional[str] = None,
    footer_color: Optional[str] = None,
) -> str:
    """
    Updates an existing banded range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        banded_range_id (int): The ID of the banded range to update. Required.
        range_name (Optional[str]): New A1-style range.
        header_color (Optional[str]): New hex color for header row.
        first_band_color (Optional[str]): New hex color for odd rows.
        second_band_color (Optional[str]): New hex color for even rows.
        footer_color (Optional[str]): New hex color for footer row.

    Returns:
        str: Confirmation message of the updated banding.
    """
    logger.info(
        f"[update_banding] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Banded Range ID: {banded_range_id}"
    )

    if banded_range_id is None:
        raise UserInputError("banded_range_id parameter is required.")

    has_updates = any([
        range_name is not None,
        header_color is not None,
        first_band_color is not None,
        second_band_color is not None,
        footer_color is not None,
    ])
    if not has_updates:
        raise UserInputError("Provide at least one property to update.")

    banded_range = {"bandedRangeId": banded_range_id}
    fields = []

    if range_name is not None:
        metadata = await asyncio.to_thread(
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title))",
            )
            .execute
        )
        sheets = metadata.get("sheets", [])
        grid_range = _parse_a1_range(range_name, sheets)
        banded_range["range"] = grid_range
        fields.append("range")

    row_properties = {}
    if header_color is not None:
        header_color_parsed = _parse_hex_color(header_color)
        if header_color_parsed:
            row_properties["headerColor"] = header_color_parsed
            fields.append("rowProperties.headerColor")

    if first_band_color is not None:
        first_band_color_parsed = _parse_hex_color(first_band_color)
        if first_band_color_parsed:
            row_properties["firstBandColor"] = first_band_color_parsed
            fields.append("rowProperties.firstBandColor")

    if second_band_color is not None:
        second_band_color_parsed = _parse_hex_color(second_band_color)
        if second_band_color_parsed:
            row_properties["secondBandColor"] = second_band_color_parsed
            fields.append("rowProperties.secondBandColor")

    if footer_color is not None:
        footer_color_parsed = _parse_hex_color(footer_color)
        if footer_color_parsed:
            row_properties["footerColor"] = footer_color_parsed
            fields.append("rowProperties.footerColor")

    if row_properties:
        banded_range["rowProperties"] = row_properties

    request_body = {
        "requests": [
            {
                "updateBanding": {
                    "bandedRange": banded_range,
                    "fields": ",".join(fields),
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    return (
        f"Updated banding (ID: {banded_range_id}) in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: updated {', '.join(fields)}."
    )


@server.tool()
@handle_http_errors("delete_banding", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_banding(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    banded_range_id: int,
) -> str:
    """
    Removes banding from a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        banded_range_id (int): The ID of the banded range to delete. Required.

    Returns:
        str: Confirmation message of the removed banding.
    """
    logger.info(
        f"[delete_banding] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Banded Range ID: {banded_range_id}"
    )

    if banded_range_id is None:
        raise UserInputError("banded_range_id parameter is required.")

    request_body = {
        "requests": [
            {
                "deleteBanding": {
                    "bandedRangeId": banded_range_id,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    return (
        f"Deleted banding (ID: {banded_range_id}) from spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )
