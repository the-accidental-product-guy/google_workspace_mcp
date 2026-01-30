"""
Google Sheets Data Tools

This module provides MCP tools for reading and writing cell values.
"""

import logging
import asyncio
import json
from typing import List, Optional, Union

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import (
    _a1_range_for_values,
    _fetch_detailed_sheet_errors,
    _format_sheet_error_section,
    _values_contain_sheets_errors,
)

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("read_sheet_values", is_read_only=True, service_type="sheets")
@require_google_service("sheets", "sheets_read")
async def read_sheet_values(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str = "A1:Z1000",
) -> str:
    """
    Reads values from a specific range in a Google Sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): The range to read (e.g., "Sheet1!A1:D10", "A1:D10"). Defaults to "A1:Z1000".

    Returns:
        str: The formatted values from the specified range.
    """
    logger.info(
        f"[read_sheet_values] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}"
    )

    result = await asyncio.to_thread(
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute
    )

    values = result.get("values", [])
    if not values:
        return f"No data found in range '{range_name}' for {user_google_email}."

    detailed_errors_section = ""
    if _values_contain_sheets_errors(values):
        resolved_range = result.get("range", range_name)
        detailed_range = _a1_range_for_values(resolved_range, values) or resolved_range
        try:
            errors = await _fetch_detailed_sheet_errors(
                service, spreadsheet_id, detailed_range
            )
            detailed_errors_section = _format_sheet_error_section(
                errors=errors, range_label=detailed_range
            )
        except Exception as exc:
            logger.warning(
                "[read_sheet_values] Failed fetching detailed error messages for range '%s': %s",
                detailed_range,
                exc,
            )

    # Format the output as a readable table
    formatted_rows = []
    for i, row in enumerate(values, 1):
        # Pad row with empty strings to show structure
        padded_row = row + [""] * max(0, len(values[0]) - len(row)) if values else row
        formatted_rows.append(f"Row {i:2d}: {padded_row}")

    text_output = (
        f"Successfully read {len(values)} rows from range '{range_name}' in spreadsheet {spreadsheet_id} for {user_google_email}:\n"
        + "\n".join(formatted_rows[:50])  # Limit to first 50 rows for readability
        + (f"\n... and {len(values) - 50} more rows" if len(values) > 50 else "")
    )

    logger.info(f"Successfully read {len(values)} rows for {user_google_email}.")
    return text_output + detailed_errors_section


@server.tool()
@handle_http_errors("modify_sheet_values", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def modify_sheet_values(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    values: Optional[Union[str, List[List[str]]]] = None,
    value_input_option: str = "USER_ENTERED",
    clear_values: bool = False,
) -> str:
    """
    Modifies values in a specific range of a Google Sheet - can write, update, or clear values.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): The range to modify (e.g., "Sheet1!A1:D10", "A1:D10"). Required.
        values (Optional[Union[str, List[List[str]]]]): 2D array of values to write/update. Can be a JSON string or Python list. Required unless clear_values=True.
        value_input_option (str): How to interpret input values ("RAW" or "USER_ENTERED"). Defaults to "USER_ENTERED".
        clear_values (bool): If True, clears the range instead of writing values. Defaults to False.

    Returns:
        str: Confirmation message of the successful modification operation.
    """
    operation = "clear" if clear_values else "write"
    logger.info(
        f"[modify_sheet_values] Invoked. Operation: {operation}, Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}"
    )

    # Parse values if it's a JSON string (MCP passes parameters as JSON strings)
    if values is not None and isinstance(values, str):
        try:
            parsed_values = json.loads(values)
            if not isinstance(parsed_values, list):
                raise ValueError(
                    f"Values must be a list, got {type(parsed_values).__name__}"
                )
            # Validate it's a list of lists
            for i, row in enumerate(parsed_values):
                if not isinstance(row, list):
                    raise ValueError(
                        f"Row {i} must be a list, got {type(row).__name__}"
                    )
            values = parsed_values
            logger.info(
                f"[modify_sheet_values] Parsed JSON string to Python list with {len(values)} rows"
            )
        except json.JSONDecodeError as e:
            raise UserInputError(f"Invalid JSON format for values: {e}")
        except ValueError as e:
            raise UserInputError(f"Invalid values structure: {e}")

    if not clear_values and not values:
        raise UserInputError(
            "Either 'values' must be provided or 'clear_values' must be True."
        )

    if clear_values:
        result = await asyncio.to_thread(
            service.spreadsheets()
            .values()
            .clear(spreadsheetId=spreadsheet_id, range=range_name)
            .execute
        )

        cleared_range = result.get("clearedRange", range_name)
        text_output = f"Successfully cleared range '{cleared_range}' in spreadsheet {spreadsheet_id} for {user_google_email}."
        logger.info(
            f"Successfully cleared range '{cleared_range}' for {user_google_email}."
        )
    else:
        body = {"values": values}

        result = await asyncio.to_thread(
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                # NOTE: This increases response payload/shape by including `updatedData`, but lets
                # us detect Sheets error tokens (e.g. "#VALUE!", "#REF!") without an extra read.
                includeValuesInResponse=True,
                responseValueRenderOption="FORMATTED_VALUE",
                body=body,
            )
            .execute
        )

        updated_cells = result.get("updatedCells", 0)
        updated_rows = result.get("updatedRows", 0)
        updated_columns = result.get("updatedColumns", 0)

        detailed_errors_section = ""
        updated_data = result.get("updatedData") or {}
        updated_values = updated_data.get("values", []) or []
        if updated_values and _values_contain_sheets_errors(updated_values):
            updated_range = result.get("updatedRange", range_name)
            detailed_range = (
                _a1_range_for_values(updated_range, updated_values) or updated_range
            )
            try:
                errors = await _fetch_detailed_sheet_errors(
                    service, spreadsheet_id, detailed_range
                )
                detailed_errors_section = _format_sheet_error_section(
                    errors=errors, range_label=detailed_range
                )
            except Exception as exc:
                logger.warning(
                    "[modify_sheet_values] Failed fetching detailed error messages for range '%s': %s",
                    detailed_range,
                    exc,
                )

        text_output = (
            f"Successfully updated range '{range_name}' in spreadsheet {spreadsheet_id} for {user_google_email}. "
            f"Updated: {updated_cells} cells, {updated_rows} rows, {updated_columns} columns."
        )
        text_output += detailed_errors_section
        logger.info(
            f"Successfully updated {updated_cells} cells for {user_google_email}."
        )

    return text_output
