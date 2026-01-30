"""
Google Sheets Sheet-level Tools

This module provides MCP tools for sheet (tab) level operations:
create, delete, duplicate, and update sheet properties.
"""

import logging
import asyncio
from typing import Optional

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _parse_hex_color

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("create_sheet", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def create_sheet(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    sheet_name: str,
) -> str:
    """
    Creates a new sheet within an existing spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        sheet_name (str): The name of the new sheet. Required.

    Returns:
        str: Confirmation message of the successful sheet creation.
    """
    logger.info(
        f"[create_sheet] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Sheet: {sheet_name}"
    )

    request_body = {"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]

    text_output = f"Successfully created sheet '{sheet_name}' (ID: {sheet_id}) in spreadsheet {spreadsheet_id} for {user_google_email}."

    logger.info(
        f"Successfully created sheet for {user_google_email}. Sheet ID: {sheet_id}"
    )
    return text_output


@server.tool()
@handle_http_errors("delete_sheet", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_sheet(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    sheet_id: Optional[int] = None,
) -> str:
    """
    Deletes a sheet (tab) from a spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        sheet_name (Optional[str]): Name of the sheet to delete. Either sheet_name or sheet_id must be provided.
        sheet_id (Optional[int]): ID of the sheet to delete. Either sheet_name or sheet_id must be provided.

    Returns:
        str: Confirmation message of the successful sheet deletion.
    """
    logger.info(
        f"[delete_sheet] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Sheet name: {sheet_name}, Sheet ID: {sheet_id}"
    )

    if sheet_name is None and sheet_id is None:
        raise UserInputError("Either sheet_name or sheet_id must be provided.")

    # Get sheet metadata to find sheet ID if only name provided
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])

    if not sheets:
        raise UserInputError("Spreadsheet has no sheets.")

    target_sheet_id = sheet_id
    target_sheet_name = sheet_name

    if sheet_name is not None:
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("title") == sheet_name:
                target_sheet_id = props.get("sheetId")
                break
        if target_sheet_id is None:
            available_titles = [s.get("properties", {}).get("title", "Untitled") for s in sheets]
            raise UserInputError(
                f"Sheet '{sheet_name}' not found. Available sheets: {', '.join(available_titles)}."
            )
    else:
        # Find sheet name for confirmation message
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("sheetId") == sheet_id:
                target_sheet_name = props.get("title", f"Sheet {sheet_id}")
                break
        if target_sheet_name is None:
            raise UserInputError(f"Sheet with ID {sheet_id} not found.")

    # Check we're not deleting the only sheet
    if len(sheets) == 1:
        raise UserInputError("Cannot delete the only sheet in a spreadsheet.")

    request_body = {"requests": [{"deleteSheet": {"sheetId": target_sheet_id}}]}

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    return (
        f"Successfully deleted sheet '{target_sheet_name}' (ID: {target_sheet_id}) "
        f"from spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("duplicate_sheet", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def duplicate_sheet(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    source_sheet_name: Optional[str] = None,
    source_sheet_id: Optional[int] = None,
    new_sheet_name: Optional[str] = None,
    insert_sheet_index: Optional[int] = None,
) -> str:
    """
    Duplicates a sheet within the same spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        source_sheet_name (Optional[str]): Name of the sheet to duplicate. Either source_sheet_name or source_sheet_id must be provided.
        source_sheet_id (Optional[int]): ID of the sheet to duplicate. Either source_sheet_name or source_sheet_id must be provided.
        new_sheet_name (Optional[str]): Name for the new duplicated sheet. If not provided, Sheets will auto-name it.
        insert_sheet_index (Optional[int]): Position to insert the new sheet (0-based). If not provided, inserts at the end.

    Returns:
        str: Confirmation message with the new sheet's name and ID.
    """
    logger.info(
        f"[duplicate_sheet] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Source name: {source_sheet_name}, Source ID: {source_sheet_id}, New name: {new_sheet_name}"
    )

    if source_sheet_name is None and source_sheet_id is None:
        raise UserInputError("Either source_sheet_name or source_sheet_id must be provided.")

    # Get sheet metadata
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])

    if not sheets:
        raise UserInputError("Spreadsheet has no sheets.")

    target_sheet_id = source_sheet_id

    if source_sheet_name is not None:
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("title") == source_sheet_name:
                target_sheet_id = props.get("sheetId")
                break
        if target_sheet_id is None:
            available_titles = [s.get("properties", {}).get("title", "Untitled") for s in sheets]
            raise UserInputError(
                f"Sheet '{source_sheet_name}' not found. Available sheets: {', '.join(available_titles)}."
            )

    duplicate_request = {"sourceSheetId": target_sheet_id}
    if new_sheet_name is not None:
        duplicate_request["newSheetName"] = new_sheet_name
    if insert_sheet_index is not None:
        duplicate_request["insertSheetIndex"] = insert_sheet_index

    request_body = {"requests": [{"duplicateSheet": duplicate_request}]}

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract new sheet info from response
    replies = response.get("replies", [])
    if replies and "duplicateSheet" in replies[0]:
        new_props = replies[0]["duplicateSheet"]["properties"]
        new_id = new_props.get("sheetId")
        new_name = new_props.get("title")
    else:
        new_id = "unknown"
        new_name = new_sheet_name or "Copy"

    source_desc = source_sheet_name or f"Sheet ID {source_sheet_id}"
    return (
        f"Successfully duplicated sheet '{source_desc}' to '{new_name}' (ID: {new_id}) "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("update_sheet_properties", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_sheet_properties(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    sheet_id: Optional[int] = None,
    new_title: Optional[str] = None,
    tab_color: Optional[str] = None,
    frozen_row_count: Optional[int] = None,
    frozen_column_count: Optional[int] = None,
    hidden: Optional[bool] = None,
    right_to_left: Optional[bool] = None,
) -> str:
    """
    Updates properties of a sheet such as title, tab color, frozen rows/columns, visibility.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        sheet_name (Optional[str]): Current name of the sheet to update. Either sheet_name or sheet_id must be provided.
        sheet_id (Optional[int]): ID of the sheet to update. Either sheet_name or sheet_id must be provided.
        new_title (Optional[str]): New name for the sheet.
        tab_color (Optional[str]): Hex color for the sheet tab (e.g., "#FF0000" for red).
        frozen_row_count (Optional[int]): Number of rows to freeze at the top (0 to unfreeze).
        frozen_column_count (Optional[int]): Number of columns to freeze on the left (0 to unfreeze).
        hidden (Optional[bool]): Whether to hide the sheet.
        right_to_left (Optional[bool]): Whether the sheet is right-to-left.

    Returns:
        str: Confirmation message of the updated properties.
    """
    logger.info(
        f"[update_sheet_properties] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Sheet name: {sheet_name}, Sheet ID: {sheet_id}"
    )

    if sheet_name is None and sheet_id is None:
        raise UserInputError("Either sheet_name or sheet_id must be provided.")

    has_updates = any([
        new_title is not None,
        tab_color is not None,
        frozen_row_count is not None,
        frozen_column_count is not None,
        hidden is not None,
        right_to_left is not None,
    ])
    if not has_updates:
        raise UserInputError(
            "Provide at least one property to update: new_title, tab_color, "
            "frozen_row_count, frozen_column_count, hidden, or right_to_left."
        )

    # Get sheet metadata
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])

    if not sheets:
        raise UserInputError("Spreadsheet has no sheets.")

    target_sheet_id = sheet_id
    target_sheet_name = sheet_name

    if sheet_name is not None:
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("title") == sheet_name:
                target_sheet_id = props.get("sheetId")
                break
        if target_sheet_id is None:
            available_titles = [s.get("properties", {}).get("title", "Untitled") for s in sheets]
            raise UserInputError(
                f"Sheet '{sheet_name}' not found. Available sheets: {', '.join(available_titles)}."
            )
    else:
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("sheetId") == sheet_id:
                target_sheet_name = props.get("title", f"Sheet {sheet_id}")
                break
        if target_sheet_name is None:
            raise UserInputError(f"Sheet with ID {sheet_id} not found.")

    # Build properties and fields to update
    properties = {"sheetId": target_sheet_id}
    fields = ["sheetId"]
    update_summary = []

    if new_title is not None:
        properties["title"] = new_title
        fields.append("title")
        update_summary.append(f"title='{new_title}'")

    if tab_color is not None:
        tab_color_parsed = _parse_hex_color(tab_color)
        if tab_color_parsed:
            properties["tabColor"] = tab_color_parsed
            fields.append("tabColor")
            update_summary.append(f"tab color={tab_color}")

    if hidden is not None:
        properties["hidden"] = hidden
        fields.append("hidden")
        update_summary.append(f"hidden={hidden}")

    if right_to_left is not None:
        properties["rightToLeft"] = right_to_left
        fields.append("rightToLeft")
        update_summary.append(f"rightToLeft={right_to_left}")

    # Grid properties need nested structure
    grid_properties = {}
    grid_fields = []
    if frozen_row_count is not None:
        if frozen_row_count < 0:
            raise UserInputError("frozen_row_count must be non-negative.")
        grid_properties["frozenRowCount"] = frozen_row_count
        grid_fields.append("gridProperties.frozenRowCount")
        update_summary.append(f"frozen rows={frozen_row_count}")

    if frozen_column_count is not None:
        if frozen_column_count < 0:
            raise UserInputError("frozen_column_count must be non-negative.")
        grid_properties["frozenColumnCount"] = frozen_column_count
        grid_fields.append("gridProperties.frozenColumnCount")
        update_summary.append(f"frozen columns={frozen_column_count}")

    if grid_properties:
        properties["gridProperties"] = grid_properties
        fields.extend(grid_fields)

    request_body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": properties,
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
        f"Successfully updated sheet '{target_sheet_name}' (ID: {target_sheet_id}) "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}: {', '.join(update_summary)}."
    )
