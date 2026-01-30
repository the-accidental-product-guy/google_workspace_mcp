"""
Google Sheets Dimension Tools

This module provides MCP tools for row/column operations:
insert, delete, move, auto-resize, and dimension groups.
"""

import logging
import asyncio
from typing import Optional

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _select_sheet

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("insert_dimension", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def insert_dimension(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    sheet_name: Optional[str] = None,
    inherit_from_before: bool = True,
) -> str:
    """
    Inserts rows or columns at a specified position.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to insert: ROWS or COLUMNS. Required.
        start_index (int): Starting index (0-based, inclusive). Row 1 = index 0, Column A = index 0. Required.
        end_index (int): Ending index (0-based, exclusive). To insert 3 rows at row 5: start=4, end=7. Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.
        inherit_from_before (bool): If True, inherits formatting from row/column before. Defaults to True.

    Returns:
        str: Confirmation message of the successful insert operation.
    """
    logger.info(
        f"[insert_dimension] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "inheritFromBefore": inherit_from_before,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Successfully inserted {count} {dim_label} at index {start_index} "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("delete_dimension", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_dimension(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Deletes rows or columns at a specified range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to delete: ROWS or COLUMNS. Required.
        start_index (int): Starting index (0-based, inclusive). Row 1 = index 0, Column A = index 0. Required.
        end_index (int): Ending index (0-based, exclusive). To delete rows 2-4: start=1, end=4. Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation message of the successful delete operation.
    """
    logger.info(
        f"[delete_dimension] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Successfully deleted {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("move_dimension", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def move_dimension(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    source_start_index: int,
    source_end_index: int,
    destination_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Moves rows or columns to a new position within the same sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to move: ROWS or COLUMNS. Required.
        source_start_index (int): Starting index of rows/columns to move (0-based, inclusive). Required.
        source_end_index (int): Ending index of rows/columns to move (0-based, exclusive). Required.
        destination_index (int): Index where the rows/columns should be moved to (0-based). Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation message of the successful move operation.
    """
    logger.info(
        f"[move_dimension] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Source: {source_start_index}-{source_end_index}, Dest: {destination_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if source_start_index < 0:
        raise UserInputError("source_start_index must be a non-negative integer.")
    if source_end_index <= source_start_index:
        raise UserInputError("source_end_index must be greater than source_start_index.")
    if destination_index < 0:
        raise UserInputError("destination_index must be a non-negative integer.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "moveDimension": {
                    "source": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": source_start_index,
                        "endIndex": source_end_index,
                    },
                    "destinationIndex": destination_index,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = source_end_index - source_start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Successfully moved {count} {dim_label} from index {source_start_index}-{source_end_index - 1} "
        f"to index {destination_index} in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("auto_resize_dimension", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def auto_resize_dimension(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Auto-resizes rows or columns to fit their content.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to auto-resize: ROWS or COLUMNS. Required.
        start_index (int): Starting index (0-based, inclusive). Required.
        end_index (int): Ending index (0-based, exclusive). Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation message of the successful auto-resize operation.
    """
    logger.info(
        f"[auto_resize_dimension] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Successfully auto-resized {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("add_dimension_group", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_dimension_group(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Groups rows or columns, allowing them to be collapsed/expanded.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to group: ROWS or COLUMNS. Required.
        start_index (int): Starting index (0-based, inclusive). Row 1 = index 0, Column A = index 0. Required.
        end_index (int): Ending index (0-based, exclusive). Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation message of the created group.
    """
    logger.info(
        f"[add_dimension_group] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "addDimensionGroup": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Grouped {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("delete_dimension_group", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_dimension_group(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Removes a row or column group (ungroups).

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to ungroup: ROWS or COLUMNS. Required.
        start_index (int): Starting index (0-based, inclusive). Required.
        end_index (int): Ending index (0-based, exclusive). Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation message of the removed group.
    """
    logger.info(
        f"[delete_dimension_group] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "deleteDimensionGroup": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    return (
        f"Ungrouped {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("update_dimension_group", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_dimension_group(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    collapsed: bool,
    sheet_name: Optional[str] = None,
    depth: int = 1,
) -> str:
    """
    Collapses or expands a row/column group.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension: ROWS or COLUMNS. Required.
        start_index (int): Starting index of the group (0-based, inclusive). Required.
        end_index (int): Ending index of the group (0-based, exclusive). Required.
        collapsed (bool): True to collapse the group, False to expand. Required.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.
        depth (int): The depth of the group (1 = outermost group, 2 = nested inside depth 1, etc.). Defaults to 1.

    Returns:
        str: Confirmation message of the group state change.
    """
    logger.info(
        f"[update_dimension_group] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Dimension: {dimension}, Range: {start_index}-{end_index}, Collapsed: {collapsed}"
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(f"dimension must be one of {sorted(allowed_dimensions)}.")

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")
    if depth < 1:
        raise UserInputError("depth must be >= 1 (1 = outermost group).")

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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "updateDimensionGroup": {
                    "dimensionGroup": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": normalized_dimension,
                            "startIndex": start_index,
                            "endIndex": end_index,
                        },
                        "depth": depth,
                        "collapsed": collapsed,
                    },
                    "fields": "collapsed",
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    count = end_index - start_index
    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    state = "collapsed" if collapsed else "expanded"
    return (
        f"{state.capitalize()} group of {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"in sheet '{sheet_title}' of spreadsheet {spreadsheet_id} for {user_google_email}."
    )
