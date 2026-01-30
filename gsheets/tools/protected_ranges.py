"""
Google Sheets Protected Ranges Tools

This module provides MCP tools for protected range CRUD operations.
"""

import logging
import asyncio
import json
from typing import List, Optional, Union

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from gsheets.sheets_helpers import _parse_a1_range

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("add_protected_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_protected_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    description: Optional[str] = None,
    warning_only: bool = False,
    editors: Optional[Union[str, List[str]]] = None,
) -> str:
    """
    Protects a range from editing.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to protect (e.g., "Sheet1!A1:D10"). Required.
        description (Optional[str]): Description of the protected range.
        warning_only (bool): If True, shows warning but allows edits. Defaults to False.
        editors (Optional[Union[str, List[str]]]): List of email addresses allowed to edit. Can be JSON string.

    Returns:
        str: Confirmation message with the protected range ID.
    """
    logger.info(
        f"[add_protected_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Range: {range_name}"
    )

    # Parse editors if it's a JSON string
    if isinstance(editors, str):
        try:
            editors = json.loads(editors)
        except json.JSONDecodeError:
            # Might be a single email
            editors = [editors]

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

    protected_range = {
        "range": grid_range,
        "warningOnly": warning_only,
    }

    if description:
        protected_range["description"] = description

    if editors:
        protected_range["editors"] = {"users": editors}

    request_body = {
        "requests": [
            {
                "addProtectedRange": {
                    "protectedRange": protected_range,
                }
            }
        ]
    }

    response = await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    # Extract protected range ID from response
    replies = response.get("replies", [])
    protected_range_id = None
    if replies and "addProtectedRange" in replies[0]:
        protected_range_id = replies[0]["addProtectedRange"]["protectedRange"].get("protectedRangeId")

    id_desc = f" (ID: {protected_range_id})" if protected_range_id else ""
    warning_desc = " (warning only)" if warning_only else ""
    return (
        f"Protected range '{range_name}'{id_desc}{warning_desc} "
        f"in spreadsheet {spreadsheet_id} for {user_google_email}."
    )


@server.tool()
@handle_http_errors("update_protected_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_protected_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    protected_range_id: int,
    range_name: Optional[str] = None,
    description: Optional[str] = None,
    warning_only: Optional[bool] = None,
    editors: Optional[Union[str, List[str]]] = None,
) -> str:
    """
    Updates an existing protected range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        protected_range_id (int): The ID of the protected range to update. Required.
        range_name (Optional[str]): New A1-style range.
        description (Optional[str]): New description.
        warning_only (Optional[bool]): If True, shows warning but allows edits.
        editors (Optional[Union[str, List[str]]]): New list of editor email addresses.

    Returns:
        str: Confirmation message of the updated protected range.
    """
    logger.info(
        f"[update_protected_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Protected Range ID: {protected_range_id}"
    )

    if protected_range_id is None:
        raise UserInputError("protected_range_id parameter is required.")

    has_updates = any([
        range_name is not None,
        description is not None,
        warning_only is not None,
        editors is not None,
    ])
    if not has_updates:
        raise UserInputError("Provide at least one property to update.")

    # Parse editors if it's a JSON string
    if isinstance(editors, str):
        try:
            editors = json.loads(editors)
        except json.JSONDecodeError:
            editors = [editors]

    protected_range = {"protectedRangeId": protected_range_id}
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
        protected_range["range"] = grid_range
        fields.append("range")

    if description is not None:
        protected_range["description"] = description
        fields.append("description")

    if warning_only is not None:
        protected_range["warningOnly"] = warning_only
        fields.append("warningOnly")

    if editors is not None:
        protected_range["editors"] = {"users": editors}
        fields.append("editors")

    request_body = {
        "requests": [
            {
                "updateProtectedRange": {
                    "protectedRange": protected_range,
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
        f"Updated protected range (ID: {protected_range_id}) in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: updated {', '.join(fields)}."
    )


@server.tool()
@handle_http_errors("delete_protected_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_protected_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    protected_range_id: int,
) -> str:
    """
    Removes protection from a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        protected_range_id (int): The ID of the protected range to delete. Required.

    Returns:
        str: Confirmation message of the removed protection.
    """
    logger.info(
        f"[delete_protected_range] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
        f"Protected Range ID: {protected_range_id}"
    )

    if protected_range_id is None:
        raise UserInputError("protected_range_id parameter is required.")

    request_body = {
        "requests": [
            {
                "deleteProtectedRange": {
                    "protectedRangeId": protected_range_id,
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
        f"Deleted protected range (ID: {protected_range_id}) from spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )
