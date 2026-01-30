"""
Google Docs Tools Package

This package contains all MCP tools for Google Docs operations,
organized into domain-specific modules following the same pattern as gsheets/tools/.
"""

# Document-level operations
from gdocs.tools.document import (
    search_docs,
    get_doc_content,
    list_docs_in_folder,
    create_doc,
    export_doc_to_pdf,
    inspect_doc_structure,
)

# Content operations (text insertion/modification)
from gdocs.tools.content import (
    modify_doc_text,
    find_and_replace_doc,
    batch_update_doc,
    mention_person,
)

# Formatting operations
from gdocs.tools.formatting import (
    update_paragraph_style,
    remove_paragraph_bullets,
)

# Table operations
from gdocs.tools.tables import (
    create_table_with_data,
    debug_table_structure,
    insert_table_row,
    insert_table_column,
    delete_table_row,
    delete_table_column,
    format_table_cells,
    set_table_column_width,
    set_table_row_height,
    merge_table_cells,
    unmerge_table_cells,
    pin_table_header_rows,
)

# Structure operations (sections, page breaks, footnotes)
from gdocs.tools.structure import (
    insert_doc_elements,
    insert_section_break,
    update_document_style,
    insert_footnote,
)

# Headers and footers
from gdocs.tools.headers_footers import (
    update_doc_headers_footers,
    delete_header,
    delete_footer,
)

# Named range operations (prefixed with doc_ to distinguish from Sheets)
from gdocs.tools.named_ranges import (
    create_doc_named_range,
    delete_doc_named_range,
    replace_doc_named_range_content,
    list_doc_named_ranges,
)

# Media operations (images, positioned objects)
from gdocs.tools.media import (
    insert_doc_image,
    replace_image,
    delete_positioned_object,
)

# Document tabs operations
from gdocs.tools.tabs import (
    add_document_tab,
    delete_document_tab,
    update_tab_properties,
    list_document_tabs,
)

# Comment operations (factory creates tools with "document" prefix)
from gdocs.tools.comments import (
    read_doc_comments as read_document_comments,
    create_doc_comment as create_document_comment,
    reply_to_comment as reply_to_document_comment,
    resolve_comment as resolve_document_comment,
)


__all__ = [
    # Document
    "search_docs",
    "get_doc_content",
    "list_docs_in_folder",
    "create_doc",
    "export_doc_to_pdf",
    "inspect_doc_structure",
    # Content
    "modify_doc_text",
    "find_and_replace_doc",
    "batch_update_doc",
    "mention_person",
    # Formatting
    "update_paragraph_style",
    "remove_paragraph_bullets",
    # Tables
    "create_table_with_data",
    "debug_table_structure",
    "insert_table_row",
    "insert_table_column",
    "delete_table_row",
    "delete_table_column",
    "format_table_cells",
    "set_table_column_width",
    "set_table_row_height",
    "merge_table_cells",
    "unmerge_table_cells",
    "pin_table_header_rows",
    # Structure
    "insert_doc_elements",
    "insert_section_break",
    "update_document_style",
    "insert_footnote",
    # Headers/Footers
    "update_doc_headers_footers",
    "delete_header",
    "delete_footer",
    # Named Ranges (doc_ prefix distinguishes from Sheets)
    "create_doc_named_range",
    "delete_doc_named_range",
    "replace_doc_named_range_content",
    "list_doc_named_ranges",
    # Media
    "insert_doc_image",
    "replace_image",
    "delete_positioned_object",
    # Tabs
    "add_document_tab",
    "delete_document_tab",
    "update_tab_properties",
    "list_document_tabs",
    # Comments
    "read_document_comments",
    "create_document_comment",
    "reply_to_document_comment",
    "resolve_document_comment",
]
