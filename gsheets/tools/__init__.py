"""
Google Sheets Tools Package

This package contains all MCP tools for Google Sheets operations,
organized into domain-specific modules.
"""

# Spreadsheet-level operations
from gsheets.tools.spreadsheet import (
    list_spreadsheets,
    get_spreadsheet_info,
    create_spreadsheet,
)

# Sheet (tab) level operations
from gsheets.tools.sheet import (
    create_sheet,
    delete_sheet,
    duplicate_sheet,
    update_sheet_properties,
)

# Data read/write operations
from gsheets.tools.data import (
    read_sheet_values,
    modify_sheet_values,
)

# Formatting operations
from gsheets.tools.formatting import (
    format_sheet_range,
    merge_cells,
    resize_dimensions,
    add_conditional_formatting,
    update_conditional_formatting,
    delete_conditional_formatting,
)

# Dimension (row/column) operations
from gsheets.tools.dimensions import (
    insert_dimension,
    delete_dimension,
    move_dimension,
    auto_resize_dimension,
    add_dimension_group,
    delete_dimension_group,
    update_dimension_group,
)

# Data manipulation operations
from gsheets.tools.manipulation import (
    sort_range,
    find_replace,
    delete_duplicates,
    trim_whitespace,
    copy_paste,
    cut_paste,
    auto_fill,
)

# Validation and filter operations
from gsheets.tools.validation import (
    set_data_validation,
    clear_data_validation,
    set_basic_filter,
    clear_basic_filter,
    add_filter_view,
    delete_filter_view,
)

# Named ranges operations
from gsheets.tools.named_ranges import (
    add_named_range,
    update_named_range,
    delete_named_range,
    list_named_ranges,
)

# Protected ranges operations
from gsheets.tools.protected_ranges import (
    add_protected_range,
    update_protected_range,
    delete_protected_range,
)

# Banding operations
from gsheets.tools.banding import (
    add_banding,
    update_banding,
    delete_banding,
)

# Comment operations
from gsheets.tools.comments import (
    read_sheet_comments,
    create_sheet_comment,
    reply_to_sheet_comment,
    resolve_sheet_comment,
)


__all__ = [
    # Spreadsheet
    "list_spreadsheets",
    "get_spreadsheet_info",
    "create_spreadsheet",
    # Sheet
    "create_sheet",
    "delete_sheet",
    "duplicate_sheet",
    "update_sheet_properties",
    # Data
    "read_sheet_values",
    "modify_sheet_values",
    # Formatting
    "format_sheet_range",
    "merge_cells",
    "resize_dimensions",
    "add_conditional_formatting",
    "update_conditional_formatting",
    "delete_conditional_formatting",
    # Dimensions
    "insert_dimension",
    "delete_dimension",
    "move_dimension",
    "auto_resize_dimension",
    "add_dimension_group",
    "delete_dimension_group",
    "update_dimension_group",
    # Manipulation
    "sort_range",
    "find_replace",
    "delete_duplicates",
    "trim_whitespace",
    "copy_paste",
    "cut_paste",
    "auto_fill",
    # Validation & Filters
    "set_data_validation",
    "clear_data_validation",
    "set_basic_filter",
    "clear_basic_filter",
    "add_filter_view",
    "delete_filter_view",
    # Named Ranges
    "add_named_range",
    "update_named_range",
    "delete_named_range",
    "list_named_ranges",
    # Protected Ranges
    "add_protected_range",
    "update_protected_range",
    "delete_protected_range",
    # Banding
    "add_banding",
    "update_banding",
    "delete_banding",
]
