"""
Google Sheets Validation and Filter Tools

This module provides MCP tools for data validation and filter operations.
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

# Data validation condition types
DATA_VALIDATION_TYPES = {
    "ONE_OF_LIST",
    "ONE_OF_RANGE",
    "NUMBER_GREATER",
    "NUMBER_GREATER_THAN_EQ",
    "NUMBER_LESS",
    "NUMBER_LESS_THAN_EQ",
    "NUMBER_EQ",
    "NUMBER_NOT_EQ",
    "NUMBER_BETWEEN",
    "NUMBER_NOT_BETWEEN",
    "DATE_BEFORE",
    "DATE_AFTER",
    "DATE_ON_OR_BEFORE",
    "DATE_ON_OR_AFTER",
    "DATE_EQ",
    "DATE_NOT_EQ",
    "DATE_BETWEEN",
    "DATE_NOT_BETWEEN",
    "DATE_IS_VALID",
    "TEXT_CONTAINS",
    "TEXT_NOT_CONTAINS",
    "TEXT_STARTS_WITH",
    "TEXT_ENDS_WITH",
    "TEXT_EQ",
    "TEXT_IS_VALID_EMAIL",
    "TEXT_IS_VALID_URL",
    "CUSTOM_FORMULA",
    "BOOLEAN",
}


@server.tool()
@handle_http_errors("set_data_validation", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def set_data_validation(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    validation_type: str,
    values: Optional[Union[str, List[str]]] = None,
    formula: Optional[str] = None,
    input_message: Optional[str] = None,
    strict: bool = True,
    show_dropdown: bool = True,
) -> str:
    """
    Sets data validation rules on a range (e.g., dropdown lists, number constraints).

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to apply validation (e.g., "A1:A100"). Required.
        validation_type (str): Type of validation. Options:
            - ONE_OF_LIST: Dropdown from list of values (provide values parameter)
            - ONE_OF_RANGE: Dropdown from cell range (provide formula like "=Sheet1!$A$1:$A$10")
            - NUMBER_GREATER, NUMBER_LESS, NUMBER_EQ, NUMBER_BETWEEN, etc.
            - DATE_BEFORE, DATE_AFTER, DATE_EQ, DATE_BETWEEN, etc.
            - TEXT_CONTAINS, TEXT_STARTS_WITH, TEXT_IS_VALID_EMAIL, TEXT_IS_VALID_URL
            - CUSTOM_FORMULA: Custom validation formula (provide formula parameter)
            - BOOLEAN: Checkbox (true/false). Required.
        values (Optional[Union[str, List[str]]]): List of allowed values for ONE_OF_LIST, or
            values for comparison (e.g., ["100"] for NUMBER_GREATER). Can be JSON string.
        formula (Optional[str]): Formula for ONE_OF_RANGE or CUSTOM_FORMULA (e.g., "=Sheet1!$A$1:$A$10").
        input_message (Optional[str]): Help text shown when cell is selected.
        strict (bool): If True, rejects invalid input. If False, shows warning only. Defaults to True.
        show_dropdown (bool): If True, shows dropdown arrow for list validations. Defaults to True.

    Returns:
        str: Confirmation message of the applied validation.
    """
    logger.info(
        f"[set_data_validation] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}, Type: {validation_type}"
    )

    # Normalize and validate type
    normalized_type = validation_type.upper()
    if normalized_type not in DATA_VALIDATION_TYPES:
        raise UserInputError(
            f"validation_type must be one of {sorted(DATA_VALIDATION_TYPES)}."
        )

    # Parse values if it's a JSON string
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError:
            # It might be a single value, wrap in list
            values = [values]

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

    # Build condition based on type
    condition = {"type": normalized_type}

    if normalized_type == "ONE_OF_LIST":
        if not values:
            raise UserInputError("values parameter is required for ONE_OF_LIST validation.")
        condition["values"] = [{"userEnteredValue": str(v)} for v in values]
    elif normalized_type == "ONE_OF_RANGE":
        if not formula:
            raise UserInputError("formula parameter is required for ONE_OF_RANGE validation (e.g., '=Sheet1!$A$1:$A$10').")
        condition["values"] = [{"userEnteredValue": formula}]
    elif normalized_type == "CUSTOM_FORMULA":
        if not formula:
            raise UserInputError("formula parameter is required for CUSTOM_FORMULA validation.")
        condition["values"] = [{"userEnteredValue": formula}]
    elif normalized_type == "BOOLEAN":
        # Boolean (checkbox) doesn't need values
        pass
    elif values:
        # For other types, values are the comparison values
        condition["values"] = [{"userEnteredValue": str(v)} for v in values]

    # Build validation rule
    data_validation_rule = {
        "condition": condition,
        "strict": strict,
        "showCustomUi": show_dropdown,
    }

    if input_message:
        data_validation_rule["inputMessage"] = input_message

    request_body = {
        "requests": [
            {
                "setDataValidation": {
                    "range": grid_range,
                    "rule": data_validation_rule,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Build description of validation
    desc_parts = [normalized_type]
    if values and normalized_type == "ONE_OF_LIST":
        desc_parts.append(f"with {len(values)} options")
    elif formula:
        desc_parts.append(f"formula: {formula}")
    elif values:
        desc_parts.append(f"value(s): {values}")
    if not strict:
        desc_parts.append("(warning only)")

    return (
        f"Set data validation on range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: {' '.join(desc_parts)}."
    )


@server.tool()
@handle_http_errors("clear_data_validation", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def clear_data_validation(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
) -> str:
    """
    Clears data validation rules from a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to clear validation from (e.g., "A1:A100"). Required.

    Returns:
        str: Confirmation message of the cleared validation.
    """
    logger.info(
        f"[clear_data_validation] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
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

    # Setting rule to None clears validation
    request_body = {
        "requests": [
            {
                "setDataValidation": {
                    "range": grid_range,
                    # Omitting 'rule' clears validation
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
        f"Cleared data validation from range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("set_basic_filter", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def set_basic_filter(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
) -> str:
    """
    Sets a basic filter on a range, enabling filter dropdowns on the header row.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to apply the filter (e.g., "A1:E100" or "Sheet1!A1:E100"). Required.

    Returns:
        str: Confirmation message of the applied filter.
    """
    logger.info(
        f"[set_basic_filter] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
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
        "requests": [
            {
                "setBasicFilter": {
                    "filter": {
                        "range": grid_range,
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

    return (
        f"Set basic filter on range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("clear_basic_filter", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def clear_basic_filter(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Clears the basic filter from a sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        sheet_name (Optional[str]): Name of the sheet to clear filter from. Defaults to first sheet.

    Returns:
        str: Confirmation message of the cleared filter.
    """
    logger.info(
        f"[clear_basic_filter] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Sheet: {sheet_name}"
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
    target_sheet = _select_sheet(sheets, sheet_name)
    sheet_id = target_sheet.get("properties", {}).get("sheetId", 0)
    sheet_title = target_sheet.get("properties", {}).get("title", "Sheet")

    request_body = {
        "requests": [
            {
                "clearBasicFilter": {
                    "sheetId": sheet_id,
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
        f"Cleared basic filter from sheet '{sheet_title}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("add_filter_view", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_filter_view(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    title: str,
) -> str:
    """
    Creates a named filter view on a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range for the filter view (e.g., "A1:E100"). Required.
        title (str): Name for the filter view. Required.

    Returns:
        str: Confirmation message with the filter view ID.
    """
    logger.info(
        f"[add_filter_view] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}, Title: {title}"
    )

    if not title:
        raise UserInputError("title parameter is required for filter view.")

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
                "addFilterView": {
                    "filter": {
                        "title": title,
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

    # Extract filter view ID from response
    replies = response.get("replies", [])
    filter_view_id = None
    if replies and "addFilterView" in replies[0]:
        filter_view_id = replies[0]["addFilterView"]["filter"].get("filterViewId")

    id_desc = f" (ID: {filter_view_id})" if filter_view_id else ""
    return (
        f"Created filter view '{title}'{id_desc} on range '{range_name}' "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("delete_filter_view", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_filter_view(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    filter_view_id: int,
) -> str:
    """
    Deletes a filter view by its ID.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        filter_view_id (int): The ID of the filter view to delete. Required.

    Returns:
        str: Confirmation message of the deleted filter view.
    """
    logger.info(
        f"[delete_filter_view] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Filter View ID: {filter_view_id}"
    )

    if filter_view_id is None or not isinstance(filter_view_id, int):
        raise UserInputError("filter_view_id must be an integer.")

    request_body = {
        "requests": [
            {
                "deleteFilterView": {
                    "filterId": filter_view_id,
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
        f"Deleted filter view (ID: {filter_view_id}) from spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )
