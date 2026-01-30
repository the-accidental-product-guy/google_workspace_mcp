"""
Google Sheets Data Manipulation Tools

This module provides MCP tools for data manipulation:
sort, find/replace, delete duplicates, trim whitespace, copy/paste, cut/paste, auto-fill.
"""

import logging
import asyncio
import json
from typing import List, Optional, Union

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _parse_a1_range, _select_sheet

# Configure module logger
logger = logging.getLogger(__name__)

# Paste types for copy/paste operations
PASTE_TYPES = {
    "PASTE_NORMAL",
    "PASTE_VALUES",
    "PASTE_FORMAT",
    "PASTE_NO_BORDERS",
    "PASTE_FORMULA",
    "PASTE_DATA_VALIDATION",
    "PASTE_CONDITIONAL_FORMATTING",
}

PASTE_ORIENTATIONS = {"NORMAL", "TRANSPOSE"}


@server.tool()
@handle_http_errors("sort_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def sort_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    sort_specs: Union[str, List[dict]],
) -> str:
    """
    Sorts data in a range by one or more columns.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to sort (e.g., "A1:D100" or "Sheet1!A1:D100"). Required.
        sort_specs (Union[str, List[dict]]): Sort specifications as a list or JSON string.
            Each spec: {"column_index": 0, "order": "ASCENDING"} where column_index is
            0-based relative to the range (0 = first column of range), order is ASCENDING or DESCENDING. Required.

    Returns:
        str: Confirmation message of the successful sort operation.
    """
    logger.info(
        f"[sort_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}"
    )

    # Parse sort_specs if it's a JSON string
    if isinstance(sort_specs, str):
        try:
            sort_specs = json.loads(sort_specs)
        except json.JSONDecodeError as e:
            raise UserInputError(f"sort_specs must be valid JSON: {e}")

    if not isinstance(sort_specs, list) or not sort_specs:
        raise UserInputError("sort_specs must be a non-empty list of sort specifications.")

    # Validate and build sort specs
    sheets_sort_specs = []
    for i, spec in enumerate(sort_specs):
        if not isinstance(spec, dict):
            raise UserInputError(f"sort_specs[{i}] must be a dictionary.")

        col_idx = spec.get("column_index")
        if col_idx is None or not isinstance(col_idx, int) or col_idx < 0:
            raise UserInputError(f"sort_specs[{i}].column_index must be a non-negative integer.")

        order = spec.get("order", "ASCENDING").upper()
        if order not in {"ASCENDING", "DESCENDING"}:
            raise UserInputError(f"sort_specs[{i}].order must be ASCENDING or DESCENDING.")

        sheets_sort_specs.append({
            "dimensionIndex": col_idx,
            "sortOrder": order,
        })

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
    grid_range = _parse_a1_range(range_name, sheets)

    request_body = {
        "requests": [
            {
                "sortRange": {
                    "range": grid_range,
                    "sortSpecs": sheets_sort_specs,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    sort_desc = ", ".join(
        f"col {s['dimensionIndex']} {s['sortOrder']}" for s in sheets_sort_specs
    )
    return (
        f"Successfully sorted range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email} by: {sort_desc}."
    )


@server.tool()
@handle_http_errors("find_replace", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def find_replace(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    find: str,
    replacement: str,
    match_case: bool = False,
    match_entire_cell: bool = False,
    search_by_regex: bool = False,
    sheet_name: Optional[str] = None,
    range_name: Optional[str] = None,
    include_formulas: bool = False,
) -> str:
    """
    Finds and replaces text in a spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        find (str): The text to find. Required.
        replacement (str): The text to replace with. Required.
        match_case (bool): Whether to match case. Defaults to False.
        match_entire_cell (bool): Whether to match entire cell contents. Defaults to False.
        search_by_regex (bool): Whether to treat 'find' as a regex pattern. Defaults to False.
        sheet_name (Optional[str]): Limit search to this sheet. If not provided, searches all sheets.
        range_name (Optional[str]): Limit search to this A1 range. If provided, overrides sheet_name.
        include_formulas (bool): Whether to search within formulas. Defaults to False.

    Returns:
        str: Confirmation message with the number of replacements made.
    """
    logger.info(
        f"[find_replace] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Find: '{find}', Replace: '{replacement}'"
    )

    if not find:
        raise UserInputError("find parameter cannot be empty.")

    find_replace_request = {
        "find": find,
        "replacement": replacement,
        "matchCase": match_case,
        "matchEntireCell": match_entire_cell,
        "searchByRegex": search_by_regex,
        "includeFormulas": include_formulas,
    }

    # Determine scope
    if range_name:
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
        find_replace_request["range"] = grid_range
        scope_desc = f"range '{range_name}'"
    elif sheet_name:
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
        find_replace_request["sheetId"] = sheet_id
        scope_desc = f"sheet '{sheet_name}'"
    else:
        find_replace_request["allSheets"] = True
        scope_desc = "all sheets"

    request_body = {
        "requests": [{"findReplace": find_replace_request}]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract replacement count from response
    replies = response.get("replies", [])
    replacements = 0
    if replies and "findReplace" in replies[0]:
        replacements = replies[0]["findReplace"].get("occurrencesChanged", 0)

    return (
        f"Find/replace completed in {scope_desc} of spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: replaced {replacements} occurrences of '{find}' with '{replacement}'."
    )


@server.tool()
@handle_http_errors("delete_duplicates", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_duplicates(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    comparison_columns: Optional[Union[str, List[int]]] = None,
) -> str:
    """
    Removes duplicate rows from a range based on specified columns.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to check for duplicates (e.g., "A1:D100"). Required.
        comparison_columns (Optional[Union[str, List[int]]]): Column indexes (0-based, relative to range)
            to use for comparison. If not provided, all columns are compared. Can be a list or JSON string.

    Returns:
        str: Confirmation message with the number of duplicates removed.
    """
    logger.info(
        f"[delete_duplicates] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}"
    )

    # Parse comparison_columns if it's a JSON string
    if isinstance(comparison_columns, str):
        try:
            comparison_columns = json.loads(comparison_columns)
        except json.JSONDecodeError as e:
            raise UserInputError(f"comparison_columns must be valid JSON: {e}")

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

    delete_duplicates_request = {"range": grid_range}

    if comparison_columns is not None:
        if not isinstance(comparison_columns, list):
            raise UserInputError("comparison_columns must be a list of column indexes.")
        for i, col in enumerate(comparison_columns):
            if not isinstance(col, int) or col < 0:
                raise UserInputError(f"comparison_columns[{i}] must be a non-negative integer.")
        delete_duplicates_request["comparisonColumns"] = [
            {"dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1}
            for col in comparison_columns
        ]

    request_body = {
        "requests": [{"deleteDuplicates": delete_duplicates_request}]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract duplicate count from response
    replies = response.get("replies", [])
    duplicates_removed = 0
    if replies and "deleteDuplicates" in replies[0]:
        duplicates_removed = replies[0]["deleteDuplicates"].get("duplicatesRemovedCount", 0)

    cols_desc = f" (comparing columns {comparison_columns})" if comparison_columns else ""
    return (
        f"Delete duplicates completed in range '{range_name}'{cols_desc} of spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: removed {duplicates_removed} duplicate rows."
    )


@server.tool()
@handle_http_errors("trim_whitespace", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def trim_whitespace(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
) -> str:
    """
    Trims leading, trailing, and consecutive interior whitespace from cells in a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to trim whitespace (e.g., "A1:D100" or "Sheet1!A:A"). Required.

    Returns:
        str: Confirmation message with the number of cells modified.
    """
    logger.info(
        f"[trim_whitespace] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
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

    request_body = {
        "requests": [{"trimWhitespace": {"range": grid_range}}]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract cell count from response
    replies = response.get("replies", [])
    cells_changed = 0
    if replies and "trimWhitespace" in replies[0]:
        cells_changed = replies[0]["trimWhitespace"].get("cellsChangedCount", 0)

    return (
        f"Trim whitespace completed in range '{range_name}' of spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: modified {cells_changed} cells."
    )


@server.tool()
@handle_http_errors("copy_paste", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def copy_paste(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    source_range: str,
    destination_range: str,
    paste_type: str = "PASTE_NORMAL",
    paste_orientation: str = "NORMAL",
) -> str:
    """
    Copies a range of data to another location.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        source_range (str): A1-style source range (e.g., "Sheet1!A1:B10"). Required.
        destination_range (str): A1-style destination range. Required.
        paste_type (str): What to paste. Options:
            - PASTE_NORMAL: Paste everything (default)
            - PASTE_VALUES: Values only (no formulas)
            - PASTE_FORMAT: Formatting only
            - PASTE_NO_BORDERS: Everything except borders
            - PASTE_FORMULA: Formulas only
            - PASTE_DATA_VALIDATION: Data validation only
            - PASTE_CONDITIONAL_FORMATTING: Conditional formatting only
        paste_orientation (str): NORMAL or TRANSPOSE. Defaults to NORMAL.

    Returns:
        str: Confirmation message of the copy operation.
    """
    logger.info(
        f"[copy_paste] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Source: {source_range}, Dest: {destination_range}"
    )

    # Validate paste type
    normalized_paste_type = paste_type.upper()
    if normalized_paste_type not in PASTE_TYPES:
        raise UserInputError(f"paste_type must be one of {sorted(PASTE_TYPES)}.")

    # Validate paste orientation
    normalized_orientation = paste_orientation.upper()
    if normalized_orientation not in PASTE_ORIENTATIONS:
        raise UserInputError(f"paste_orientation must be one of {sorted(PASTE_ORIENTATIONS)}.")

    # Get sheet metadata and parse ranges
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])
    source_grid_range = _parse_a1_range(source_range, sheets)
    destination_grid_range = _parse_a1_range(destination_range, sheets)

    request_body = {
        "requests": [
            {
                "copyPaste": {
                    "source": source_grid_range,
                    "destination": destination_grid_range,
                    "pasteType": normalized_paste_type,
                    "pasteOrientation": normalized_orientation,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    orientation_desc = " (transposed)" if normalized_orientation == "TRANSPOSE" else ""
    return (
        f"Copied '{source_range}' to '{destination_range}'{orientation_desc} "
        f"with {normalized_paste_type} in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("cut_paste", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def cut_paste(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    source_range: str,
    destination_cell: str,
    paste_type: str = "PASTE_NORMAL",
) -> str:
    """
    Cuts (moves) a range of data to another location.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        source_range (str): A1-style source range to cut (e.g., "Sheet1!A1:B10"). Required.
        destination_cell (str): A1-style destination cell (top-left corner, e.g., "D1"). Required.
        paste_type (str): What to paste (PASTE_NORMAL, PASTE_VALUES, PASTE_FORMAT). Defaults to PASTE_NORMAL.

    Returns:
        str: Confirmation message of the cut/paste operation.
    """
    logger.info(
        f"[cut_paste] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Source: {source_range}, Dest: {destination_cell}"
    )

    # Validate paste type
    normalized_paste_type = paste_type.upper()
    if normalized_paste_type not in PASTE_TYPES:
        raise UserInputError(f"paste_type must be one of {sorted(PASTE_TYPES)}.")

    # Get sheet metadata and parse ranges
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])
    source_grid_range = _parse_a1_range(source_range, sheets)
    dest_grid_range = _parse_a1_range(destination_cell, sheets)

    # For cut/paste, destination is a coordinate (top-left cell)
    destination_coordinate = {
        "sheetId": dest_grid_range["sheetId"],
        "rowIndex": dest_grid_range.get("startRowIndex", 0),
        "columnIndex": dest_grid_range.get("startColumnIndex", 0),
    }

    request_body = {
        "requests": [
            {
                "cutPaste": {
                    "source": source_grid_range,
                    "destination": destination_coordinate,
                    "pasteType": normalized_paste_type,
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
        f"Cut '{source_range}' and pasted to '{destination_cell}' "
        f"with {normalized_paste_type} in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("auto_fill", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def auto_fill(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    source_range: str,
    destination_range: str,
    use_alternate_series: bool = False,
) -> str:
    """
    Auto-fills a range based on the pattern in the source range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        source_range (str): A1-style range containing the pattern (e.g., "A1:A2" with 1, 2). Required.
        destination_range (str): A1-style range to fill (must include source, e.g., "A1:A10"). Required.
        use_alternate_series (bool): If True, uses alternate series fill. Defaults to False.

    Returns:
        str: Confirmation message of the auto-fill operation.
    """
    logger.info(
        f"[auto_fill] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Source: {source_range}, Dest: {destination_range}"
    )

    # Get sheet metadata and parse ranges
    metadata = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute
    )
    sheets = metadata.get("sheets", [])
    source_grid_range = _parse_a1_range(source_range, sheets)
    dest_grid_range = _parse_a1_range(destination_range, sheets)

    # Determine fill direction based on range sizes
    source_rows = source_grid_range.get("endRowIndex", 0) - source_grid_range.get("startRowIndex", 0)
    source_cols = source_grid_range.get("endColumnIndex", 0) - source_grid_range.get("startColumnIndex", 0)
    dest_rows = dest_grid_range.get("endRowIndex", 0) - dest_grid_range.get("startRowIndex", 0)
    dest_cols = dest_grid_range.get("endColumnIndex", 0) - dest_grid_range.get("startColumnIndex", 0)

    if dest_cols > source_cols:
        dimension = "COLUMNS"
        fill_length = dest_cols - source_cols
    else:
        dimension = "ROWS"
        fill_length = dest_rows - source_rows

    request_body = {
        "requests": [
            {
                "autoFill": {
                    "sourceAndDestination": {
                        "source": source_grid_range,
                        "dimension": dimension,
                        "fillLength": fill_length,
                    },
                    "useAlternateSeries": use_alternate_series,
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
        f"Auto-filled from '{source_range}' to '{destination_range}' "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )
