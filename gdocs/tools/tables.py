"""
Google Docs Table Operations

This module provides MCP tools for table operations including creation,
row/column manipulation, cell formatting, and merging.
"""

import logging
import asyncio
import json
from typing import List, Any, Optional

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from gdocs.docs_helpers import (
    create_insert_table_row_request,
    create_insert_table_column_request,
    create_delete_table_row_request,
    create_delete_table_column_request,
    create_update_table_cell_style_request,
    create_update_table_column_properties_request,
    create_update_table_row_style_request,
    create_merge_table_cells_request,
    create_unmerge_table_cells_request,
    create_pin_table_header_rows_request,
)
from gdocs.docs_structure import find_tables
from gdocs.managers import TableOperationManager, ValidationManager

logger = logging.getLogger(__name__)


@server.tool()
@handle_http_errors("create_table_with_data", service_type="docs")
@require_google_service("docs", "docs_write")
async def create_table_with_data(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_data: List[List[str]],
    index: int,
    bold_headers: bool = True,
) -> str:
    """
    Creates a table and populates it with data in one reliable operation.

    CRITICAL: YOU MUST CALL inspect_doc_structure FIRST TO GET THE INDEX!

    MANDATORY WORKFLOW - DO THESE STEPS IN ORDER:

    Step 1: ALWAYS call inspect_doc_structure first
    Step 2: Use the 'total_length' value from inspect_doc_structure as your index
    Step 3: Format data as 2D list: [["col1", "col2"], ["row1col1", "row1col2"]]
    Step 4: Call this function with the correct index and data

    EXAMPLE DATA FORMAT:
    table_data = [
        ["Header1", "Header2", "Header3"],    # Row 0 - headers
        ["Data1", "Data2", "Data3"],          # Row 1 - first data row
        ["Data4", "Data5", "Data6"]           # Row 2 - second data row
    ]

    CRITICAL INDEX REQUIREMENTS:
    - NEVER use index values like 1, 2, 10 without calling inspect_doc_structure first
    - ALWAYS get index from inspect_doc_structure 'total_length' field
    - Index must be a valid insertion point in the document

    DATA FORMAT REQUIREMENTS:
    - Must be 2D list of strings only
    - Each inner list = one table row
    - All rows MUST have same number of columns
    - Use empty strings "" for empty cells, never None
    - Use debug_table_structure after creation to verify results

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_data: 2D list of strings - EXACT format: [["col1", "col2"], ["row1col1", "row1col2"]]
        index: Document position (MANDATORY: get from inspect_doc_structure 'total_length')
        bold_headers: Whether to make first row bold (default: true)

    Returns:
        str: Confirmation with table details and link
    """
    logger.debug(f"[create_table_with_data] Doc={document_id}, index={index}")

    validator = ValidationManager()

    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"ERROR: {error_msg}"

    is_valid, error_msg = validator.validate_table_data(table_data)
    if not is_valid:
        return f"ERROR: {error_msg}"

    is_valid, error_msg = validator.validate_index(index, "Index")
    if not is_valid:
        return f"ERROR: {error_msg}"

    table_manager = TableOperationManager(service)

    success, message, metadata = await table_manager.create_and_populate_table(
        document_id, table_data, index, bold_headers
    )

    # Retry with adjusted index if at document boundary
    if not success and "must be less than the end index" in message:
        logger.debug(
            f"Index {index} is at document boundary, retrying with index {index - 1}"
        )
        success, message, metadata = await table_manager.create_and_populate_table(
            document_id, table_data, index - 1, bold_headers
        )

    if success:
        link = f"https://docs.google.com/document/d/{document_id}/edit"
        rows = metadata.get("rows", 0)
        columns = metadata.get("columns", 0)

        return (
            f"SUCCESS: {message}. Table: {rows}x{columns}, Index: {index}. Link: {link}"
        )
    else:
        return f"ERROR: {message}"


@server.tool()
@handle_http_errors("debug_table_structure", is_read_only=True, service_type="docs")
@require_google_service("docs", "docs_read")
async def debug_table_structure(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int = 0,
) -> str:
    """
    ESSENTIAL DEBUGGING TOOL - Use this whenever tables don't work as expected.

    USE THIS IMMEDIATELY WHEN:
    - Table population put data in wrong cells
    - You get "table not found" errors
    - Data appears concatenated in first cell
    - Need to understand existing table structure
    - Planning to use populate_existing_table

    WHAT THIS SHOWS YOU:
    - Exact table dimensions (rows x columns)
    - Each cell's position coordinates (row,col)
    - Current content in each cell
    - Insertion indices for each cell
    - Table boundaries and ranges

    HOW TO READ THE OUTPUT:
    - "dimensions": "2x3" = 2 rows, 3 columns
    - "position": "(0,0)" = first row, first column
    - "current_content": What's actually in each cell right now
    - "insertion_index": Where new text would be inserted in that cell

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to inspect
        table_index: Which table to debug (0 = first table, 1 = second table, etc.)

    Returns:
        str: Detailed JSON structure showing table layout, cell positions, and current content
    """
    logger.debug(
        f"[debug_table_structure] Doc={document_id}, table_index={table_index}"
    )

    doc = await asyncio.to_thread(
        service.documents().get(documentId=document_id).execute
    )

    tables = find_tables(doc)
    if table_index >= len(tables):
        return f"Error: Table index {table_index} not found. Document has {len(tables)} table(s)."

    table_info = tables[table_index]

    debug_info = {
        "table_index": table_index,
        "dimensions": f"{table_info['rows']}x{table_info['columns']}",
        "table_range": f"[{table_info['start_index']}-{table_info['end_index']}]",
        "cells": [],
    }

    for row_idx, row in enumerate(table_info["cells"]):
        row_info = []
        for col_idx, cell in enumerate(row):
            cell_debug = {
                "position": f"({row_idx},{col_idx})",
                "range": f"[{cell['start_index']}-{cell['end_index']}]",
                "insertion_index": cell.get("insertion_index", "N/A"),
                "current_content": repr(cell.get("content", "")),
                "content_elements_count": len(cell.get("content_elements", [])),
            }
            row_info.append(cell_debug)
        debug_info["cells"].append(row_info)

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Table structure debug for table {table_index}:\n\n{json.dumps(debug_info, indent=2)}\n\nLink: {link}"


async def _get_table_start_index(service: Any, document_id: str, table_index: int) -> tuple[bool, str, int]:
    """Helper to get table start index from document."""
    doc = await asyncio.to_thread(
        service.documents().get(documentId=document_id).execute
    )
    tables = find_tables(doc)

    if table_index >= len(tables):
        return False, f"Table index {table_index} not found. Document has {len(tables)} table(s).", 0

    return True, "", tables[table_index]["start_index"]


@server.tool()
@handle_http_errors("insert_table_row", service_type="docs")
@require_google_service("docs", "docs_write")
async def insert_table_row(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_index: int,
    insert_below: bool = True,
) -> str:
    """
    Inserts a new row into an existing table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_index: Row position reference (0-based)
        insert_below: If True, insert below the specified row; if False, insert above

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[insert_table_row] Doc={document_id}, table={table_index}, row={row_index}, below={insert_below}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_insert_table_row_request(table_start, row_index, insert_below)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    position = "below" if insert_below else "above"
    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted row {position} row {row_index} in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("insert_table_column", service_type="docs")
@require_google_service("docs", "docs_write")
async def insert_table_column(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    column_index: int,
    insert_right: bool = True,
) -> str:
    """
    Inserts a new column into an existing table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        column_index: Column position reference (0-based)
        insert_right: If True, insert to the right; if False, insert to the left

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[insert_table_column] Doc={document_id}, table={table_index}, col={column_index}, right={insert_right}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_insert_table_column_request(table_start, column_index, insert_right)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    position = "right of" if insert_right else "left of"
    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Inserted column {position} column {column_index} in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("delete_table_row", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_table_row(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_index: int,
) -> str:
    """
    Deletes a row from an existing table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_index: Row to delete (0-based)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[delete_table_row] Doc={document_id}, table={table_index}, row={row_index}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_delete_table_row_request(table_start, row_index)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted row {row_index} from table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("delete_table_column", service_type="docs")
@require_google_service("docs", "docs_write")
async def delete_table_column(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    column_index: int,
) -> str:
    """
    Deletes a column from an existing table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        column_index: Column to delete (0-based)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[delete_table_column] Doc={document_id}, table={table_index}, col={column_index}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_delete_table_column_request(table_start, column_index)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Deleted column {column_index} from table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("format_table_cells", service_type="docs")
@require_google_service("docs", "docs_write")
async def format_table_cells(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
    background_color: str = None,
    border_color: str = None,
    border_width: float = None,
    padding_top: float = None,
    padding_bottom: float = None,
    padding_left: float = None,
    padding_right: float = None,
    content_alignment: str = None,
) -> str:
    """
    Formats cells in a table (background color, borders, padding, alignment).

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_start: Starting row (0-based, inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (0-based, inclusive)
        column_end: Ending column (exclusive)
        background_color: Cell background color (#RRGGBB)
        border_color: Border color (#RRGGBB)
        border_width: Border width in points
        padding_top: Top padding in points
        padding_bottom: Bottom padding in points
        padding_left: Left padding in points
        padding_right: Right padding in points
        content_alignment: Vertical alignment ("TOP", "MIDDLE", "BOTTOM")

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[format_table_cells] Doc={document_id}, table={table_index}, "
        f"rows={row_start}-{row_end}, cols={column_start}-{column_end}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    # Validate at least one formatting option provided
    if not any([
        background_color, border_color, border_width,
        padding_top, padding_bottom, padding_left, padding_right,
        content_alignment
    ]):
        return "Error: At least one formatting option must be provided"

    # Validate colors if provided
    if background_color:
        is_valid, error_msg = validator.validate_color_param(background_color, "background_color")
        if not is_valid:
            return f"Error: {error_msg}"
    if border_color:
        is_valid, error_msg = validator.validate_color_param(border_color, "border_color")
        if not is_valid:
            return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    # Build style dict
    style = {}
    if background_color:
        style["background_color"] = background_color
    if border_color:
        style["border_color"] = border_color
    if border_width is not None:
        style["border_width"] = border_width
    if padding_top is not None:
        style["padding_top"] = padding_top
    if padding_bottom is not None:
        style["padding_bottom"] = padding_bottom
    if padding_left is not None:
        style["padding_left"] = padding_left
    if padding_right is not None:
        style["padding_right"] = padding_right
    if content_alignment:
        style["content_alignment"] = content_alignment

    requests = [create_update_table_cell_style_request(
        table_start, row_start, row_end, column_start, column_end, style
    )]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Formatted cells [{row_start}:{row_end}, {column_start}:{column_end}] in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("set_table_column_width", service_type="docs")
@require_google_service("docs", "docs_write")
async def set_table_column_width(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    column_index: int,
    width: float,
) -> str:
    """
    Sets the width of a table column.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        column_index: Column to resize (0-based)
        width: Column width in points

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[set_table_column_width] Doc={document_id}, table={table_index}, col={column_index}, width={width}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if width <= 0:
        return "Error: Width must be a positive number"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_update_table_column_properties_request(table_start, column_index, width)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Set column {column_index} width to {width}pt in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("set_table_row_height", service_type="docs")
@require_google_service("docs", "docs_write")
async def set_table_row_height(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_index: int,
    min_height: float,
) -> str:
    """
    Sets the minimum height of a table row.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_index: Row to resize (0-based)
        min_height: Minimum row height in points

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[set_table_row_height] Doc={document_id}, table={table_index}, row={row_index}, height={min_height}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if min_height <= 0:
        return "Error: Height must be a positive number"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_update_table_row_style_request(table_start, row_index, min_height)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Set row {row_index} minimum height to {min_height}pt in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("merge_table_cells", service_type="docs")
@require_google_service("docs", "docs_write")
async def merge_table_cells(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
) -> str:
    """
    Merges a range of cells in a table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_start: Starting row (0-based, inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (0-based, inclusive)
        column_end: Ending column (exclusive)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[merge_table_cells] Doc={document_id}, table={table_index}, "
        f"rows={row_start}-{row_end}, cols={column_start}-{column_end}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    # Validate range makes sense
    if row_end <= row_start or column_end <= column_start:
        return "Error: End indices must be greater than start indices"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_merge_table_cells_request(
        table_start, row_start, row_end, column_start, column_end
    )]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Merged cells [{row_start}:{row_end}, {column_start}:{column_end}] in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("unmerge_table_cells", service_type="docs")
@require_google_service("docs", "docs_write")
async def unmerge_table_cells(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
) -> str:
    """
    Unmerges previously merged cells in a table.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        row_start: Starting row (0-based, inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (0-based, inclusive)
        column_end: Ending column (exclusive)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[unmerge_table_cells] Doc={document_id}, table={table_index}, "
        f"rows={row_start}-{row_end}, cols={column_start}-{column_end}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_unmerge_table_cells_request(
        table_start, row_start, row_end, column_start, column_end
    )]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    return f"Unmerged cells [{row_start}:{row_end}, {column_start}:{column_end}] in table {table_index}. Link: {link}"


@server.tool()
@handle_http_errors("pin_table_header_rows", service_type="docs")
@require_google_service("docs", "docs_write")
async def pin_table_header_rows(
    service: Any,
    user_google_email: str,
    document_id: str,
    table_index: int,
    pinned_rows_count: int,
) -> str:
    """
    Pins (freezes) header rows in a table so they repeat on each page.

    Args:
        user_google_email: User's Google email address
        document_id: ID of the document to update
        table_index: Which table to modify (0 = first table)
        pinned_rows_count: Number of rows to pin (0 to unpin all)

    Returns:
        str: Confirmation message with operation details
    """
    logger.info(
        f"[pin_table_header_rows] Doc={document_id}, table={table_index}, rows={pinned_rows_count}"
    )

    validator = ValidationManager()
    is_valid, error_msg = validator.validate_document_id(document_id)
    if not is_valid:
        return f"Error: {error_msg}"

    if pinned_rows_count < 0:
        return "Error: Pinned rows count cannot be negative"

    success, error_msg, table_start = await _get_table_start_index(service, document_id, table_index)
    if not success:
        return f"Error: {error_msg}"

    requests = [create_pin_table_header_rows_request(table_start, pinned_rows_count)]

    await asyncio.to_thread(
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute
    )

    link = f"https://docs.google.com/document/d/{document_id}/edit"
    if pinned_rows_count == 0:
        return f"Unpinned all header rows in table {table_index}. Link: {link}"
    return f"Pinned {pinned_rows_count} header row(s) in table {table_index}. Link: {link}"
