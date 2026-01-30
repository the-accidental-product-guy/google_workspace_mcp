"""
Google Sheets Named Ranges Tools

This module provides MCP tools for named range CRUD operations.
"""

import logging
import asyncio
from typing import Optional

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _parse_a1_range, _grid_range_to_a1

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("add_named_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_named_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    name: str,
    range_name: str,
) -> str:
    """
    Creates a named range in the spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        name (str): Name for the named range (must be unique, no spaces). Required.
        range_name (str): A1-style range (e.g., "Sheet1!A1:D100"). Required.

    Returns:
        str: Confirmation message with the named range ID.
    """
    logger.info(
        f"[add_named_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Name: {name}, Range: {range_name}"
    )

    if not name:
        raise UserInputError("name parameter is required.")
    if " " in name:
        raise UserInputError("Named range name cannot contain spaces.")

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

    request_body = {
        "requests": [
            {
                "addNamedRange": {
                    "namedRange": {
                        "name": name,
                        "range": grid_range,
                    }
                }
            }
        ]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract named range ID from response
    replies = response.get("replies", [])
    named_range_id = None
    if replies and "addNamedRange" in replies[0]:
        named_range_id = replies[0]["addNamedRange"]["namedRange"].get("namedRangeId")

    id_desc = f" (ID: {named_range_id})" if named_range_id else ""
    return (
        f"Created named range '{name}'{id_desc} for range '{range_name}' "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("update_named_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_named_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    named_range_id: str,
    new_name: Optional[str] = None,
    new_range: Optional[str] = None,
) -> str:
    """
    Updates an existing named range's name or range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        named_range_id (str): The ID of the named range to update. Required.
        new_name (Optional[str]): New name for the named range.
        new_range (Optional[str]): New A1-style range (e.g., "Sheet1!A1:E100").

    Returns:
        str: Confirmation message of the updated named range.
    """
    logger.info(
        f"[update_named_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Named Range ID: {named_range_id}"
    )

    if not named_range_id:
        raise UserInputError("named_range_id parameter is required.")

    if new_name is None and new_range is None:
        raise UserInputError("Provide at least one of new_name or new_range to update.")

    if new_name and " " in new_name:
        raise UserInputError("Named range name cannot contain spaces.")

    # Build the update
    named_range = {"namedRangeId": named_range_id}
    fields = []

    if new_name is not None:
        named_range["name"] = new_name
        fields.append("name")

    if new_range is not None:
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
        grid_range = _parse_a1_range(new_range, sheets)
        named_range["range"] = grid_range
        fields.append("range")

    request_body = {
        "requests": [
            {
                "updateNamedRange": {
                    "namedRange": named_range,
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

    update_desc = []
    if new_name:
        update_desc.append(f"name='{new_name}'")
    if new_range:
        update_desc.append(f"range='{new_range}'")

    return (
        f"Updated named range (ID: {named_range_id}) in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: {', '.join(update_desc)}."
    )


@server.tool()
@handle_http_errors("delete_named_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_named_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    named_range_id: str,
) -> str:
    """
    Deletes a named range by its ID.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        named_range_id (str): The ID of the named range to delete. Required.

    Returns:
        str: Confirmation message of the deleted named range.
    """
    logger.info(
        f"[delete_named_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Named Range ID: {named_range_id}"
    )

    if not named_range_id:
        raise UserInputError("named_range_id parameter is required.")

    request_body = {
        "requests": [
            {
                "deleteNamedRange": {
                    "namedRangeId": named_range_id,
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
        f"Deleted named range (ID: {named_range_id}) from spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("list_named_ranges", is_read_only=True, service_type="sheets")
@require_google_service("sheets", "sheets_read")
async def list_named_ranges(
    service,
    user_google_email: str,
    spreadsheet_id: str,
) -> str:
    """
    Lists all named ranges in a spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.

    Returns:
        str: Formatted list of named ranges with their IDs and ranges.
    """
    logger.info(
        f"[list_named_ranges] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}"
    )

    # Get spreadsheet with named ranges
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="namedRanges(namedRangeId,name,range),sheets(properties(sheetId,title))",
        )
        .execute
    )

    named_ranges = metadata.get("namedRanges", [])
    sheets = metadata.get("sheets", [])

    # Build sheet ID to title mapping
    sheet_titles = {}
    for sheet in sheets:
        props = sheet.get("properties", {})
        sid = props.get("sheetId")
        if sid is not None:
            sheet_titles[sid] = props.get("title", f"Sheet {sid}")

    if not named_ranges:
        return f"No named ranges found in spreadsheet {spreadsheet_id} for {user_google_email}."

    # Format the output
    ranges_list = []
    for nr in named_ranges:
        nr_id = nr.get("namedRangeId", "unknown")
        nr_name = nr.get("name", "unnamed")
        nr_range = nr.get("range", {})
        range_a1 = _grid_range_to_a1(nr_range, sheet_titles)
        ranges_list.append(f'- "{nr_name}" (ID: {nr_id}) -> {range_a1}')

    return (
        f"Named ranges in spreadsheet {spreadsheet_id} for {user_google_email} ({len(named_ranges)}):\n"
        + "\n".join(ranges_list)
    )
