"""
Google Sheets MCP Tools

This module provides MCP tools for interacting with Google Sheets API.
"""

import logging
import asyncio
import json
import copy
from typing import List, Optional, Union

from auth.service_decorator import require_google_service
from core.server import server
from core.utils import handle_http_errors, UserInputError
from core.comments import create_comment_tools
from gsheets.sheets_helpers import (
    CONDITION_TYPES,
    _a1_range_for_values,
    _build_boolean_rule,
    _build_gradient_rule,
    _fetch_detailed_sheet_errors,
    _fetch_sheets_with_rules,
    _format_conditional_rules_section,
    _format_sheet_error_section,
    _parse_a1_range,
    _parse_condition_values,
    _parse_gradient_points,
    _parse_hex_color,
    _select_sheet,
    _values_contain_sheets_errors,
)

# Configure module logger
logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("list_spreadsheets", is_read_only=True, service_type="sheets")
@require_google_service("drive", "drive_read")
async def list_spreadsheets(
    service,
    user_google_email: str,
    max_results: int = 25,
) -> str:
    """
    Lists spreadsheets from Google Drive that the user has access to.

    Args:
        user_google_email (str): The user's Google email address. Required.
        max_results (int): Maximum number of spreadsheets to return. Defaults to 25.

    Returns:
        str: A formatted list of spreadsheet files (name, ID, modified time).
    """
    logger.info(f"[list_spreadsheets] Invoked. Email: '{user_google_email}'")

    files_response = await asyncio.to_thread(
        service.files()
        .list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=max_results,
            fields="files(id,name,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute
    )

    files = files_response.get("files", [])
    if not files:
        return f"No spreadsheets found for {user_google_email}."

    spreadsheets_list = [
        f'- "{file["name"]}" (ID: {file["id"]}) | Modified: {file.get("modifiedTime", "Unknown")} | Link: {file.get("webViewLink", "No link")}'
        for file in files
    ]

    text_output = (
        f"Successfully listed {len(files)} spreadsheets for {user_google_email}:\n"
        + "\n".join(spreadsheets_list)
    )

    logger.info(
        f"Successfully listed {len(files)} spreadsheets for {user_google_email}."
    )
    return text_output


@server.tool()
@handle_http_errors("get_spreadsheet_info", is_read_only=True, service_type="sheets")
@require_google_service("sheets", "sheets_read")
async def get_spreadsheet_info(
    service,
    user_google_email: str,
    spreadsheet_id: str,
) -> str:
    """
    Gets information about a specific spreadsheet including its sheets.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet to get info for. Required.

    Returns:
        str: Formatted spreadsheet information including title, locale, and sheets list.
    """
    logger.info(
        f"[get_spreadsheet_info] Invoked. Email: '{user_google_email}', Spreadsheet ID: {spreadsheet_id}"
    )

    spreadsheet = await asyncio.to_thread(
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="spreadsheetId,properties(title,locale),sheets(properties(title,sheetId,gridProperties(rowCount,columnCount)),conditionalFormats)",
        )
        .execute
    )

    properties = spreadsheet.get("properties", {})
    title = properties.get("title", "Unknown")
    locale = properties.get("locale", "Unknown")
    sheets = spreadsheet.get("sheets", [])

    sheet_titles = {}
    for sheet in sheets:
        sheet_props = sheet.get("properties", {})
        sid = sheet_props.get("sheetId")
        if sid is not None:
            sheet_titles[sid] = sheet_props.get("title", f"Sheet {sid}")

    sheets_info = []
    for sheet in sheets:
        sheet_props = sheet.get("properties", {})
        sheet_name = sheet_props.get("title", "Unknown")
        sheet_id = sheet_props.get("sheetId", "Unknown")
        grid_props = sheet_props.get("gridProperties", {})
        rows = grid_props.get("rowCount", "Unknown")
        cols = grid_props.get("columnCount", "Unknown")
        rules = sheet.get("conditionalFormats", []) or []

        sheets_info.append(
            f'  - "{sheet_name}" (ID: {sheet_id}) | Size: {rows}x{cols} | Conditional formats: {len(rules)}'
        )
        if rules:
            sheets_info.append(
                _format_conditional_rules_section(
                    sheet_name, rules, sheet_titles, indent="    "
                )
            )

    sheets_section = "\n".join(sheets_info) if sheets_info else "  No sheets found"
    text_output = "\n".join(
        [
            f'Spreadsheet: "{title}" (ID: {spreadsheet_id}) | Locale: {locale}',
            f"Sheets ({len(sheets)}):",
            sheets_section,
        ]
    )

    logger.info(
        f"Successfully retrieved info for spreadsheet {spreadsheet_id} for {user_google_email}."
    )
    return text_output


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


@server.tool()
@handle_http_errors("format_sheet_range", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def format_sheet_range(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    number_format_type: Optional[str] = None,
    number_format_pattern: Optional[str] = None,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strikethrough: Optional[bool] = None,
    font_size: Optional[int] = None,
    font_family: Optional[str] = None,
    horizontal_alignment: Optional[str] = None,
    vertical_alignment: Optional[str] = None,
    wrap_strategy: Optional[str] = None,
    border_style: Optional[str] = None,
    border_color: Optional[str] = None,
    border_sides: Optional[str] = None,
) -> str:
    """
    Applies formatting to a range: background/text color, font styling, and number/date formats.

    Colors accept hex strings (#RRGGBB). Number formats follow Sheets types
    (e.g., NUMBER, NUMBER_WITH_GROUPING, CURRENCY, DATE, TIME, DATE_TIME,
    PERCENT, TEXT, SCIENTIFIC). If no sheet name is provided, the first sheet
    is used.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range (optionally with sheet name). Required.
        background_color (Optional[str]): Hex background color (e.g., "#FFEECC").
        text_color (Optional[str]): Hex text color (e.g., "#000000").
        number_format_type (Optional[str]): Sheets number format type (e.g., "DATE").
        number_format_pattern (Optional[str]): Optional custom pattern for the number format.
        bold (Optional[bool]): Whether to make text bold.
        italic (Optional[bool]): Whether to make text italic.
        underline (Optional[bool]): Whether to underline text.
        strikethrough (Optional[bool]): Whether to strikethrough text.
        font_size (Optional[int]): Font size in points (e.g., 10, 12, 14).
        font_family (Optional[str]): Font family name (e.g., "Arial", "Times New Roman").
        horizontal_alignment (Optional[str]): Horizontal alignment: LEFT, CENTER, RIGHT.
        vertical_alignment (Optional[str]): Vertical alignment: TOP, MIDDLE, BOTTOM.
        wrap_strategy (Optional[str]): Text wrap strategy: WRAP, OVERFLOW_CELL, CLIP.
        border_style (Optional[str]): Border line style: SOLID, DASHED, DOTTED, DOUBLE, SOLID_MEDIUM, SOLID_THICK, NONE.
        border_color (Optional[str]): Hex border color (e.g., "#000000"). Defaults to black.
        border_sides (Optional[str]): Comma-separated sides to apply border: "top,bottom,left,right". Defaults to all sides.

    Returns:
        str: Confirmation of the applied formatting.
    """
    logger.info(
        "[format_sheet_range] Invoked. Email: '%s', Spreadsheet: %s, Range: %s",
        user_google_email,
        spreadsheet_id,
        range_name,
    )

    has_font_formatting = any([
        bold is not None,
        italic is not None,
        underline is not None,
        strikethrough is not None,
        font_size is not None,
        font_family is not None,
    ])
    has_alignment = horizontal_alignment is not None or vertical_alignment is not None
    has_wrapping = wrap_strategy is not None
    has_borders = border_style is not None

    if not any([background_color, text_color, number_format_type, has_font_formatting,
                has_alignment, has_wrapping, has_borders]):
        raise UserInputError(
            "Provide at least one formatting option: background_color, text_color, "
            "number_format_type, font styling (bold, italic, underline, strikethrough, "
            "font_size, font_family), alignment (horizontal_alignment, vertical_alignment), "
            "wrap_strategy, or borders (border_style)."
        )

    bg_color_parsed = _parse_hex_color(background_color)
    text_color_parsed = _parse_hex_color(text_color)

    number_format = None
    if number_format_type:
        allowed_number_formats = {
            "NUMBER",
            "NUMBER_WITH_GROUPING",
            "CURRENCY",
            "PERCENT",
            "SCIENTIFIC",
            "DATE",
            "TIME",
            "DATE_TIME",
            "TEXT",
        }
        normalized_type = number_format_type.upper()
        if normalized_type not in allowed_number_formats:
            raise UserInputError(
                f"number_format_type must be one of {sorted(allowed_number_formats)}."
            )
        number_format = {"type": normalized_type}
        if number_format_pattern:
            number_format["pattern"] = number_format_pattern

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

    user_entered_format = {}
    fields = []
    if bg_color_parsed:
        user_entered_format["backgroundColor"] = bg_color_parsed
        fields.append("userEnteredFormat.backgroundColor")

    # Build textFormat with all font properties
    text_format = {}
    if text_color_parsed:
        text_format["foregroundColor"] = text_color_parsed
        fields.append("userEnteredFormat.textFormat.foregroundColor")
    if bold is not None:
        text_format["bold"] = bold
        fields.append("userEnteredFormat.textFormat.bold")
    if italic is not None:
        text_format["italic"] = italic
        fields.append("userEnteredFormat.textFormat.italic")
    if underline is not None:
        text_format["underline"] = underline
        fields.append("userEnteredFormat.textFormat.underline")
    if strikethrough is not None:
        text_format["strikethrough"] = strikethrough
        fields.append("userEnteredFormat.textFormat.strikethrough")
    if font_size is not None:
        if font_size < 1:
            raise UserInputError("font_size must be a positive integer.")
        text_format["fontSize"] = font_size
        fields.append("userEnteredFormat.textFormat.fontSize")
    if font_family is not None:
        text_format["fontFamily"] = font_family
        fields.append("userEnteredFormat.textFormat.fontFamily")

    if text_format:
        user_entered_format["textFormat"] = text_format

    if number_format:
        user_entered_format["numberFormat"] = number_format
        fields.append("userEnteredFormat.numberFormat")

    # Handle horizontal alignment
    if horizontal_alignment is not None:
        allowed_h_align = {"LEFT", "CENTER", "RIGHT"}
        normalized_h = horizontal_alignment.upper()
        if normalized_h not in allowed_h_align:
            raise UserInputError(
                f"horizontal_alignment must be one of {sorted(allowed_h_align)}."
            )
        user_entered_format["horizontalAlignment"] = normalized_h
        fields.append("userEnteredFormat.horizontalAlignment")

    # Handle vertical alignment
    if vertical_alignment is not None:
        allowed_v_align = {"TOP", "MIDDLE", "BOTTOM"}
        normalized_v = vertical_alignment.upper()
        if normalized_v not in allowed_v_align:
            raise UserInputError(
                f"vertical_alignment must be one of {sorted(allowed_v_align)}."
            )
        user_entered_format["verticalAlignment"] = normalized_v
        fields.append("userEnteredFormat.verticalAlignment")

    # Handle text wrapping
    if wrap_strategy is not None:
        allowed_wrap = {"WRAP", "OVERFLOW_CELL", "CLIP"}
        normalized_wrap = wrap_strategy.upper()
        if normalized_wrap not in allowed_wrap:
            raise UserInputError(
                f"wrap_strategy must be one of {sorted(allowed_wrap)}."
            )
        user_entered_format["wrapStrategy"] = normalized_wrap
        fields.append("userEnteredFormat.wrapStrategy")

    # Handle borders
    if border_style is not None:
        allowed_border_styles = {
            "SOLID", "DASHED", "DOTTED", "DOUBLE",
            "SOLID_MEDIUM", "SOLID_THICK", "NONE"
        }
        normalized_border = border_style.upper()
        if normalized_border not in allowed_border_styles:
            raise UserInputError(
                f"border_style must be one of {sorted(allowed_border_styles)}."
            )

        # Parse border color (default to black)
        border_color_parsed = _parse_hex_color(border_color) if border_color else {
            "red": 0, "green": 0, "blue": 0
        }

        # Determine which sides to apply borders
        if border_sides:
            sides = [s.strip().lower() for s in border_sides.split(",")]
            allowed_sides = {"top", "bottom", "left", "right"}
            invalid_sides = set(sides) - allowed_sides
            if invalid_sides:
                raise UserInputError(
                    f"Invalid border_sides: {invalid_sides}. Must be: {sorted(allowed_sides)}."
                )
        else:
            sides = ["top", "bottom", "left", "right"]

        border_spec = {"style": normalized_border, "color": border_color_parsed}
        borders = {}
        for side in sides:
            borders[side] = border_spec
            fields.append(f"userEnteredFormat.borders.{side}")

        user_entered_format["borders"] = borders

    if not user_entered_format:
        raise UserInputError(
            "No formatting applied. Verify provided colors, font options, or number format."
        )

    request_body = {
        "requests": [
            {
                "repeatCell": {
                    "range": grid_range,
                    "cell": {"userEnteredFormat": user_entered_format},
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

    applied_parts = []
    if bg_color_parsed:
        applied_parts.append(f"background {background_color}")
    if text_color_parsed:
        applied_parts.append(f"text color {text_color}")

    # Summarize font formatting
    font_parts = []
    if bold is not None:
        font_parts.append("bold" if bold else "not bold")
    if italic is not None:
        font_parts.append("italic" if italic else "not italic")
    if underline is not None:
        font_parts.append("underline" if underline else "no underline")
    if strikethrough is not None:
        font_parts.append("strikethrough" if strikethrough else "no strikethrough")
    if font_size is not None:
        font_parts.append(f"{font_size}pt")
    if font_family is not None:
        font_parts.append(f"font '{font_family}'")
    if font_parts:
        applied_parts.append(f"font: {', '.join(font_parts)}")

    if number_format:
        nf_desc = number_format["type"]
        if number_format_pattern:
            nf_desc += f" (pattern: {number_format_pattern})"
        applied_parts.append(f"format {nf_desc}")

    # Summarize alignment
    if horizontal_alignment:
        applied_parts.append(f"h-align: {horizontal_alignment.upper()}")
    if vertical_alignment:
        applied_parts.append(f"v-align: {vertical_alignment.upper()}")

    # Summarize wrapping
    if wrap_strategy:
        applied_parts.append(f"wrap: {wrap_strategy.upper()}")

    # Summarize borders
    if border_style:
        border_desc = border_style.upper()
        if border_color:
            border_desc += f" {border_color}"
        if border_sides:
            border_desc += f" ({border_sides})"
        else:
            border_desc += " (all sides)"
        applied_parts.append(f"borders: {border_desc}")

    summary = ", ".join(applied_parts)
    return (
        f"Applied formatting to range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}: {summary}."
    )


@server.tool()
@handle_http_errors("merge_cells", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def merge_cells(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    merge_type: Optional[str] = None,
    unmerge: bool = False,
) -> str:
    """
    Merges or unmerges cells in a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range to merge/unmerge (e.g., "A1:C3" or "Sheet1!A1:C3").
        merge_type (Optional[str]): How to merge: MERGE_ALL (single cell), MERGE_COLUMNS (merge each column), MERGE_ROWS (merge each row). Defaults to MERGE_ALL.
        unmerge (bool): If True, unmerges cells in the range instead of merging.

    Returns:
        str: Confirmation of the merge/unmerge operation.
    """
    logger.info(
        "[merge_cells] Invoked. Email: '%s', Spreadsheet: %s, Range: %s, Unmerge: %s",
        user_google_email,
        spreadsheet_id,
        range_name,
        unmerge,
    )

    # Get sheet metadata for parsing range
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

    if unmerge:
        request_body = {
            "requests": [{"unmergeCells": {"range": grid_range}}]
        }
        action = "Unmerged"
    else:
        # Validate merge_type
        allowed_merge_types = {"MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS"}
        if merge_type is None:
            merge_type = "MERGE_ALL"
        else:
            merge_type = merge_type.upper()
            if merge_type not in allowed_merge_types:
                raise UserInputError(
                    f"merge_type must be one of {sorted(allowed_merge_types)}."
                )

        request_body = {
            "requests": [
                {
                    "mergeCells": {
                        "range": grid_range,
                        "mergeType": merge_type,
                    }
                }
            ]
        }
        action = f"Merged ({merge_type})"

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    return (
        f"{action} cells in range '{range_name}' in spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("resize_dimensions", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def resize_dimensions(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    dimension: str,
    start_index: int,
    end_index: int,
    pixel_size: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Sets the height of rows or width of columns in a sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        dimension (str): Which dimension to resize: ROWS (for row height) or COLUMNS (for column width).
        start_index (int): Starting row/column index (0-based). Row 1 = index 0, Column A = index 0.
        end_index (int): Ending row/column index (exclusive). To resize row 1 only: start=0, end=1.
        pixel_size (int): Size in pixels. Typical row height: 21. Typical column width: 100.
        sheet_name (Optional[str]): Name of the sheet. Defaults to first sheet if not specified.

    Returns:
        str: Confirmation of the resize operation.
    """
    logger.info(
        "[resize_dimensions] Invoked. Email: '%s', Spreadsheet: %s, Dimension: %s, "
        "Range: %d-%d, Size: %d px",
        user_google_email,
        spreadsheet_id,
        dimension,
        start_index,
        end_index,
        pixel_size,
    )

    # Validate dimension
    allowed_dimensions = {"ROWS", "COLUMNS"}
    normalized_dimension = dimension.upper()
    if normalized_dimension not in allowed_dimensions:
        raise UserInputError(
            f"dimension must be one of {sorted(allowed_dimensions)}."
        )

    # Validate indices
    if start_index < 0:
        raise UserInputError("start_index must be a non-negative integer.")
    if end_index <= start_index:
        raise UserInputError("end_index must be greater than start_index.")
    if pixel_size < 1:
        raise UserInputError("pixel_size must be a positive integer.")

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

    # Find the sheet ID
    sheet_id = None
    if sheet_name:
        for sheet in sheets:
            props = sheet.get("properties", {})
            if props.get("title") == sheet_name:
                sheet_id = props.get("sheetId")
                break
        if sheet_id is None:
            raise UserInputError(f"Sheet '{sheet_name}' not found in spreadsheet.")
    else:
        # Use first sheet
        if sheets:
            sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)
        else:
            sheet_id = 0

    request_body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": normalized_dimension,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "properties": {"pixelSize": pixel_size},
                    "fields": "pixelSize",
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    dim_label = "rows" if normalized_dimension == "ROWS" else "columns"
    count = end_index - start_index
    sheet_desc = f"sheet '{sheet_name}'" if sheet_name else "first sheet"

    return (
        f"Resized {count} {dim_label} (index {start_index} to {end_index - 1}) "
        f"to {pixel_size}px in {sheet_desc} of spreadsheet {spreadsheet_id} "
        f"for {user_google_email}."
    )


@server.tool()
@handle_http_errors("add_conditional_formatting", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def add_conditional_formatting(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    range_name: str,
    condition_type: str,
    condition_values: Optional[Union[str, List[Union[str, int, float]]]] = None,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    rule_index: Optional[int] = None,
    gradient_points: Optional[Union[str, List[dict]]] = None,
) -> str:
    """
    Adds a conditional formatting rule to a range.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (str): A1-style range (optionally with sheet name). Required.
        condition_type (str): Sheets condition type (e.g., NUMBER_GREATER, TEXT_CONTAINS, DATE_BEFORE, CUSTOM_FORMULA).
        condition_values (Optional[Union[str, List[Union[str, int, float]]]]): Values for the condition; accepts a list or a JSON string representing a list. Depends on condition_type.
        background_color (Optional[str]): Hex background color to apply when condition matches.
        text_color (Optional[str]): Hex text color to apply when condition matches.
        rule_index (Optional[int]): Optional position to insert the rule (0-based) within the sheet's rules.
        gradient_points (Optional[Union[str, List[dict]]]): List (or JSON list) of gradient points for a color scale. If provided, a gradient rule is created and boolean parameters are ignored.

    Returns:
        str: Confirmation of the added rule.
    """
    logger.info(
        "[add_conditional_formatting] Invoked. Email: '%s', Spreadsheet: %s, Range: %s, Type: %s, Values: %s",
        user_google_email,
        spreadsheet_id,
        range_name,
        condition_type,
        condition_values,
    )

    if rule_index is not None and (not isinstance(rule_index, int) or rule_index < 0):
        raise UserInputError("rule_index must be a non-negative integer when provided.")

    condition_values_list = _parse_condition_values(condition_values)
    gradient_points_list = _parse_gradient_points(gradient_points)

    sheets, sheet_titles = await _fetch_sheets_with_rules(service, spreadsheet_id)
    grid_range = _parse_a1_range(range_name, sheets)

    target_sheet = None
    for sheet in sheets:
        if sheet.get("properties", {}).get("sheetId") == grid_range.get("sheetId"):
            target_sheet = sheet
            break
    if target_sheet is None:
        raise UserInputError(
            "Target sheet not found while adding conditional formatting."
        )

    current_rules = target_sheet.get("conditionalFormats", []) or []

    insert_at = rule_index if rule_index is not None else len(current_rules)
    if insert_at > len(current_rules):
        raise UserInputError(
            f"rule_index {insert_at} is out of range for sheet '{target_sheet.get('properties', {}).get('title', 'Unknown')}' "
            f"(current count: {len(current_rules)})."
        )

    if gradient_points_list:
        new_rule = _build_gradient_rule([grid_range], gradient_points_list)
        rule_desc = "gradient"
        values_desc = ""
        applied_parts = [f"gradient points {len(gradient_points_list)}"]
    else:
        rule, cond_type_normalized = _build_boolean_rule(
            [grid_range],
            condition_type,
            condition_values_list,
            background_color,
            text_color,
        )
        new_rule = rule
        rule_desc = cond_type_normalized
        values_desc = ""
        if condition_values_list:
            values_desc = f" with values {condition_values_list}"
        applied_parts = []
        if background_color:
            applied_parts.append(f"background {background_color}")
        if text_color:
            applied_parts.append(f"text {text_color}")

    new_rules_state = copy.deepcopy(current_rules)
    new_rules_state.insert(insert_at, new_rule)

    add_rule_request = {"rule": new_rule}
    if rule_index is not None:
        add_rule_request["index"] = rule_index

    request_body = {"requests": [{"addConditionalFormatRule": add_rule_request}]}

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    format_desc = ", ".join(applied_parts) if applied_parts else "format applied"

    sheet_title = target_sheet.get("properties", {}).get("title", "Unknown")
    state_text = _format_conditional_rules_section(
        sheet_title, new_rules_state, sheet_titles, indent=""
    )

    return "\n".join(
        [
            f"Added conditional format on '{range_name}' in spreadsheet {spreadsheet_id} "
            f"for {user_google_email}: {rule_desc}{values_desc}; format: {format_desc}.",
            state_text,
        ]
    )


@server.tool()
@handle_http_errors("update_conditional_formatting", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def update_conditional_formatting(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    rule_index: int,
    range_name: Optional[str] = None,
    condition_type: Optional[str] = None,
    condition_values: Optional[Union[str, List[Union[str, int, float]]]] = None,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    sheet_name: Optional[str] = None,
    gradient_points: Optional[Union[str, List[dict]]] = None,
) -> str:
    """
    Updates an existing conditional formatting rule by index on a sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        range_name (Optional[str]): A1-style range to apply the updated rule (optionally with sheet name). If omitted, existing ranges are preserved.
        rule_index (int): Index of the rule to update (0-based).
        condition_type (Optional[str]): Sheets condition type. If omitted, the existing rule's type is preserved.
        condition_values (Optional[Union[str, List[Union[str, int, float]]]]): Values for the condition.
        background_color (Optional[str]): Hex background color when condition matches.
        text_color (Optional[str]): Hex text color when condition matches.
        sheet_name (Optional[str]): Sheet name to locate the rule when range_name is omitted. Defaults to first sheet.
        gradient_points (Optional[Union[str, List[dict]]]): If provided, updates the rule to a gradient color scale using these points.

    Returns:
        str: Confirmation of the updated rule and the current rule state.
    """
    logger.info(
        "[update_conditional_formatting] Invoked. Email: '%s', Spreadsheet: %s, Range: %s, Rule Index: %s",
        user_google_email,
        spreadsheet_id,
        range_name,
        rule_index,
    )

    if not isinstance(rule_index, int) or rule_index < 0:
        raise UserInputError("rule_index must be a non-negative integer.")

    condition_values_list = _parse_condition_values(condition_values)
    gradient_points_list = _parse_gradient_points(gradient_points)

    sheets, sheet_titles = await _fetch_sheets_with_rules(service, spreadsheet_id)

    target_sheet = None
    grid_range = None
    if range_name:
        grid_range = _parse_a1_range(range_name, sheets)
        for sheet in sheets:
            if sheet.get("properties", {}).get("sheetId") == grid_range.get("sheetId"):
                target_sheet = sheet
                break
    else:
        target_sheet = _select_sheet(sheets, sheet_name)

    if target_sheet is None:
        raise UserInputError(
            "Target sheet not found while updating conditional formatting."
        )

    sheet_props = target_sheet.get("properties", {})
    sheet_id = sheet_props.get("sheetId")
    sheet_title = sheet_props.get("title", f"Sheet {sheet_id}")

    rules = target_sheet.get("conditionalFormats", []) or []
    if rule_index >= len(rules):
        raise UserInputError(
            f"rule_index {rule_index} is out of range for sheet '{sheet_title}' (current count: {len(rules)})."
        )

    existing_rule = rules[rule_index]
    ranges_to_use = existing_rule.get("ranges", [])
    if range_name:
        ranges_to_use = [grid_range]
    if not ranges_to_use:
        ranges_to_use = [{"sheetId": sheet_id}]

    new_rule = None
    rule_desc = ""
    values_desc = ""
    format_desc = ""

    if gradient_points_list is not None:
        new_rule = _build_gradient_rule(ranges_to_use, gradient_points_list)
        rule_desc = "gradient"
        format_desc = f"gradient points {len(gradient_points_list)}"
    elif "gradientRule" in existing_rule:
        if any([background_color, text_color, condition_type, condition_values_list]):
            raise UserInputError(
                "Existing rule is a gradient rule. Provide gradient_points to update it, or omit formatting/condition parameters to keep it unchanged."
            )
        new_rule = {
            "ranges": ranges_to_use,
            "gradientRule": existing_rule.get("gradientRule", {}),
        }
        rule_desc = "gradient"
        format_desc = "gradient (unchanged)"
    else:
        existing_boolean = existing_rule.get("booleanRule", {})
        existing_condition = existing_boolean.get("condition", {})
        existing_format = copy.deepcopy(existing_boolean.get("format", {}))

        cond_type = (condition_type or existing_condition.get("type", "")).upper()
        if not cond_type:
            raise UserInputError("condition_type is required for boolean rules.")
        if cond_type not in CONDITION_TYPES:
            raise UserInputError(
                f"condition_type must be one of {sorted(CONDITION_TYPES)}."
            )

        if condition_values_list is not None:
            cond_values = [
                {"userEnteredValue": str(val)} for val in condition_values_list
            ]
        else:
            cond_values = existing_condition.get("values")

        new_format = copy.deepcopy(existing_format) if existing_format else {}
        if background_color is not None:
            bg_color_parsed = _parse_hex_color(background_color)
            if bg_color_parsed:
                new_format["backgroundColor"] = bg_color_parsed
            elif "backgroundColor" in new_format:
                del new_format["backgroundColor"]
        if text_color is not None:
            text_color_parsed = _parse_hex_color(text_color)
            text_format = copy.deepcopy(new_format.get("textFormat", {}))
            if text_color_parsed:
                text_format["foregroundColor"] = text_color_parsed
            elif "foregroundColor" in text_format:
                del text_format["foregroundColor"]
            if text_format:
                new_format["textFormat"] = text_format
            elif "textFormat" in new_format:
                del new_format["textFormat"]

        if not new_format:
            raise UserInputError("At least one format option must remain on the rule.")

        new_rule = {
            "ranges": ranges_to_use,
            "booleanRule": {
                "condition": {"type": cond_type},
                "format": new_format,
            },
        }
        if cond_values:
            new_rule["booleanRule"]["condition"]["values"] = cond_values

        rule_desc = cond_type
        if condition_values_list:
            values_desc = f" with values {condition_values_list}"
        format_parts = []
        if "backgroundColor" in new_format:
            format_parts.append("background updated")
        if "textFormat" in new_format and new_format["textFormat"].get(
            "foregroundColor"
        ):
            format_parts.append("text color updated")
        format_desc = ", ".join(format_parts) if format_parts else "format preserved"

    new_rules_state = copy.deepcopy(rules)
    new_rules_state[rule_index] = new_rule

    request_body = {
        "requests": [
            {
                "updateConditionalFormatRule": {
                    "index": rule_index,
                    "sheetId": sheet_id,
                    "rule": new_rule,
                }
            }
        ]
    }

    await asyncio.to_thread(
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute
    )

    state_text = _format_conditional_rules_section(
        sheet_title, new_rules_state, sheet_titles, indent=""
    )

    return "\n".join(
        [
            f"Updated conditional format at index {rule_index} on sheet '{sheet_title}' in spreadsheet {spreadsheet_id} "
            f"for {user_google_email}: {rule_desc}{values_desc}; format: {format_desc}.",
            state_text,
        ]
    )


@server.tool()
@handle_http_errors("delete_conditional_formatting", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def delete_conditional_formatting(
    service,
    user_google_email: str,
    spreadsheet_id: str,
    rule_index: int,
    sheet_name: Optional[str] = None,
) -> str:
    """
    Deletes an existing conditional formatting rule by index on a sheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        spreadsheet_id (str): The ID of the spreadsheet. Required.
        rule_index (int): Index of the rule to delete (0-based).
        sheet_name (Optional[str]): Name of the sheet that contains the rule. Defaults to the first sheet if not provided.

    Returns:
        str: Confirmation of the deletion and the current rule state.
    """
    logger.info(
        "[delete_conditional_formatting] Invoked. Email: '%s', Spreadsheet: %s, Sheet: %s, Rule Index: %s",
        user_google_email,
        spreadsheet_id,
        sheet_name,
        rule_index,
    )

    if not isinstance(rule_index, int) or rule_index < 0:
        raise UserInputError("rule_index must be a non-negative integer.")

    sheets, sheet_titles = await _fetch_sheets_with_rules(service, spreadsheet_id)
    target_sheet = _select_sheet(sheets, sheet_name)

    sheet_props = target_sheet.get("properties", {})
    sheet_id = sheet_props.get("sheetId")
    target_sheet_name = sheet_props.get("title", f"Sheet {sheet_id}")
    rules = target_sheet.get("conditionalFormats", []) or []
    if rule_index >= len(rules):
        raise UserInputError(
            f"rule_index {rule_index} is out of range for sheet '{target_sheet_name}' (current count: {len(rules)})."
        )

    new_rules_state = copy.deepcopy(rules)
    del new_rules_state[rule_index]

    request_body = {
        "requests": [
            {
                "deleteConditionalFormatRule": {
                    "index": rule_index,
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

    state_text = _format_conditional_rules_section(
        target_sheet_name, new_rules_state, sheet_titles, indent=""
    )

    return "\n".join(
        [
            f"Deleted conditional format at index {rule_index} on sheet '{target_sheet_name}' in spreadsheet {spreadsheet_id} for {user_google_email}.",
            state_text,
        ]
    )


@server.tool()
@handle_http_errors("create_spreadsheet", service_type="sheets")
@require_google_service("sheets", "sheets_write")
async def create_spreadsheet(
    service,
    user_google_email: str,
    title: str,
    sheet_names: Optional[List[str]] = None,
) -> str:
    """
    Creates a new Google Spreadsheet.

    Args:
        user_google_email (str): The user's Google email address. Required.
        title (str): The title of the new spreadsheet. Required.
        sheet_names (Optional[List[str]]): List of sheet names to create. If not provided, creates one sheet with default name.

    Returns:
        str: Information about the newly created spreadsheet including ID, URL, and locale.
    """
    logger.info(
        f"[create_spreadsheet] Invoked. Email: '{user_google_email}', Title: {title}"
    )

    spreadsheet_body = {"properties": {"title": title}}

    if sheet_names:
        spreadsheet_body["sheets"] = [
            {"properties": {"title": sheet_name}} for sheet_name in sheet_names
        ]

    spreadsheet = await asyncio.to_thread(
        service.spreadsheets()
        .create(
            body=spreadsheet_body,
            fields="spreadsheetId,spreadsheetUrl,properties(title,locale)",
        )
        .execute
    )

    properties = spreadsheet.get("properties", {})
    spreadsheet_id = spreadsheet.get("spreadsheetId")
    spreadsheet_url = spreadsheet.get("spreadsheetUrl")
    locale = properties.get("locale", "Unknown")

    text_output = (
        f"Successfully created spreadsheet '{title}' for {user_google_email}. "
        f"ID: {spreadsheet_id} | URL: {spreadsheet_url} | Locale: {locale}"
    )

    logger.info(
        f"Successfully created spreadsheet for {user_google_email}. ID: {spreadsheet_id}"
    )
    return text_output


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
    from gsheets.sheets_helpers import _grid_range_to_a1

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

    request_body = {
        "requests": [
            {
                "autoFill": {
                    "sourceAndDestination": {
                        "source": source_grid_range,
                        "dimension": "ROWS",  # Will auto-detect actual fill direction
                        "fillLength": (
                            dest_grid_range.get("endRowIndex", 0)
                            - source_grid_range.get("endRowIndex", 0)
                        ),
                    },
                    "useAlternateSeries": use_alternate_series,
                }
            }
        ]
    }

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


# Create comment management tools for sheets
_comment_tools = create_comment_tools("spreadsheet", "spreadsheet_id")

# Extract and register the functions
read_sheet_comments = _comment_tools["read_comments"]
create_sheet_comment = _comment_tools["create_comment"]
reply_to_sheet_comment = _comment_tools["reply_to_comment"]
resolve_sheet_comment = _comment_tools["resolve_comment"]
