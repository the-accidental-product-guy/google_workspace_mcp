"""
Google Docs Helper Functions

This module provides utility functions for common Google Docs operations
to simplify the implementation of document editing tools.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _normalize_color(
    color: Optional[str], param_name: str
) -> Optional[Dict[str, float]]:
    """
    Normalize a user-supplied color into Docs API rgbColor format.

    Supports only hex strings in the form "#RRGGBB".
    """
    if color is None:
        return None

    if not isinstance(color, str):
        raise ValueError(f"{param_name} must be a hex string like '#RRGGBB'")

    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"{param_name} must be a hex string like '#RRGGBB'")

    hex_color = color[1:]
    if any(c not in "0123456789abcdefABCDEF" for c in hex_color):
        raise ValueError(f"{param_name} must be a hex string like '#RRGGBB'")

    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return {"red": r, "green": g, "blue": b}


def build_text_style(
    bold: bool = None,
    italic: bool = None,
    underline: bool = None,
    font_size: int = None,
    font_family: str = None,
    text_color: str = None,
    background_color: str = None,
) -> tuple[Dict[str, Any], list[str]]:
    """
    Build text style object for Google Docs API requests.

    Args:
        bold: Whether text should be bold
        italic: Whether text should be italic
        underline: Whether text should be underlined
        font_size: Font size in points
        font_family: Font family name
        text_color: Text color as hex string "#RRGGBB"
        background_color: Background (highlight) color as hex string "#RRGGBB"

    Returns:
        Tuple of (text_style_dict, list_of_field_names)
    """
    text_style = {}
    fields = []

    if bold is not None:
        text_style["bold"] = bold
        fields.append("bold")

    if italic is not None:
        text_style["italic"] = italic
        fields.append("italic")

    if underline is not None:
        text_style["underline"] = underline
        fields.append("underline")

    if font_size is not None:
        text_style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
        fields.append("fontSize")

    if font_family is not None:
        text_style["weightedFontFamily"] = {"fontFamily": font_family}
        fields.append("weightedFontFamily")

    if text_color is not None:
        rgb = _normalize_color(text_color, "text_color")
        text_style["foregroundColor"] = {"color": {"rgbColor": rgb}}
        fields.append("foregroundColor")

    if background_color is not None:
        rgb = _normalize_color(background_color, "background_color")
        text_style["backgroundColor"] = {"color": {"rgbColor": rgb}}
        fields.append("backgroundColor")

    return text_style, fields


# =============================================================================
# TEXT OPERATIONS
# =============================================================================


def create_insert_text_request(index: int, text: str) -> Dict[str, Any]:
    """
    Create an insertText request for Google Docs API.

    Args:
        index: Position to insert text
        text: Text to insert

    Returns:
        Dictionary representing the insertText request
    """
    return {"insertText": {"location": {"index": index}, "text": text}}


def create_insert_text_segment_request(
    index: int, text: str, segment_id: str
) -> Dict[str, Any]:
    """
    Create an insertText request for Google Docs API with segmentId (for headers/footers).

    Args:
        index: Position to insert text
        text: Text to insert
        segment_id: Segment ID (for targeting headers/footers)

    Returns:
        Dictionary representing the insertText request with segmentId
    """
    return {
        "insertText": {
            "location": {"segmentId": segment_id, "index": index},
            "text": text,
        }
    }


def create_delete_range_request(start_index: int, end_index: int) -> Dict[str, Any]:
    """
    Create a deleteContentRange request for Google Docs API.

    Args:
        start_index: Start position of content to delete
        end_index: End position of content to delete

    Returns:
        Dictionary representing the deleteContentRange request
    """
    return {
        "deleteContentRange": {
            "range": {"startIndex": start_index, "endIndex": end_index}
        }
    }


def create_format_text_request(
    start_index: int,
    end_index: int,
    bold: bool = None,
    italic: bool = None,
    underline: bool = None,
    font_size: int = None,
    font_family: str = None,
    text_color: str = None,
    background_color: str = None,
) -> Optional[Dict[str, Any]]:
    """
    Create an updateTextStyle request for Google Docs API.

    Args:
        start_index: Start position of text to format
        end_index: End position of text to format
        bold: Whether text should be bold
        italic: Whether text should be italic
        underline: Whether text should be underlined
        font_size: Font size in points
        font_family: Font family name
        text_color: Text color as hex string "#RRGGBB"
        background_color: Background (highlight) color as hex string "#RRGGBB"

    Returns:
        Dictionary representing the updateTextStyle request, or None if no styles provided
    """
    text_style, fields = build_text_style(
        bold, italic, underline, font_size, font_family, text_color, background_color
    )

    if not text_style:
        return None

    return {
        "updateTextStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "textStyle": text_style,
            "fields": ",".join(fields),
        }
    }


def create_find_replace_request(
    find_text: str, replace_text: str, match_case: bool = False
) -> Dict[str, Any]:
    """
    Create a replaceAllText request for Google Docs API.

    Args:
        find_text: Text to find
        replace_text: Text to replace with
        match_case: Whether to match case exactly

    Returns:
        Dictionary representing the replaceAllText request
    """
    return {
        "replaceAllText": {
            "containsText": {"text": find_text, "matchCase": match_case},
            "replaceText": replace_text,
        }
    }


def create_insert_person_request(index: int, person_email: str) -> Dict[str, Any]:
    """
    Create an insertPerson request for Google Docs API (@ mentions).

    Args:
        index: Position to insert the person mention
        person_email: Email address of the person to mention

    Returns:
        Dictionary representing the insertPerson request
    """
    return {
        "insertPerson": {
            "location": {"index": index},
            "personProperties": {"email": person_email},
        }
    }


# =============================================================================
# TABLE OPERATIONS
# =============================================================================


def create_insert_table_request(index: int, rows: int, columns: int) -> Dict[str, Any]:
    """
    Create an insertTable request for Google Docs API.

    Args:
        index: Position to insert table
        rows: Number of rows
        columns: Number of columns

    Returns:
        Dictionary representing the insertTable request
    """
    return {
        "insertTable": {"location": {"index": index}, "rows": rows, "columns": columns}
    }


def create_insert_table_row_request(
    table_start_index: int, row_index: int, insert_below: bool = True
) -> Dict[str, Any]:
    """
    Create an insertTableRow request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_index: Row index to insert relative to
        insert_below: If True, insert below; if False, insert above

    Returns:
        Dictionary representing the insertTableRow request
    """
    return {
        "insertTableRow": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index},
                "rowIndex": row_index,
                "columnIndex": 0,
            },
            "insertBelow": insert_below,
        }
    }


def create_insert_table_column_request(
    table_start_index: int, column_index: int, insert_right: bool = True
) -> Dict[str, Any]:
    """
    Create an insertTableColumn request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        column_index: Column index to insert relative to
        insert_right: If True, insert to the right; if False, insert to the left

    Returns:
        Dictionary representing the insertTableColumn request
    """
    return {
        "insertTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index},
                "rowIndex": 0,
                "columnIndex": column_index,
            },
            "insertRight": insert_right,
        }
    }


def create_delete_table_row_request(
    table_start_index: int, row_index: int
) -> Dict[str, Any]:
    """
    Create a deleteTableRow request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_index: Row index to delete

    Returns:
        Dictionary representing the deleteTableRow request
    """
    return {
        "deleteTableRow": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index},
                "rowIndex": row_index,
                "columnIndex": 0,
            }
        }
    }


def create_delete_table_column_request(
    table_start_index: int, column_index: int
) -> Dict[str, Any]:
    """
    Create a deleteTableColumn request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        column_index: Column index to delete

    Returns:
        Dictionary representing the deleteTableColumn request
    """
    return {
        "deleteTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index},
                "rowIndex": 0,
                "columnIndex": column_index,
            }
        }
    }


def create_update_table_cell_style_request(
    table_start_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
    style: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create an updateTableCellStyle request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_start: Starting row (inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (inclusive)
        column_end: Ending column (exclusive)
        style: Dictionary containing style properties:
            - background_color: Hex color "#RRGGBB"
            - border_color: Hex color "#RRGGBB"
            - border_width: Width in points
            - padding_top/bottom/left/right: Padding in points
            - content_alignment: "TOP", "MIDDLE", or "BOTTOM"

    Returns:
        Dictionary representing the updateTableCellStyle request
    """
    table_cell_style = {}
    fields = []

    if "background_color" in style:
        rgb = _normalize_color(style["background_color"], "background_color")
        table_cell_style["backgroundColor"] = {"color": {"rgbColor": rgb}}
        fields.append("backgroundColor")

    # Build border style if border properties provided
    if "border_color" in style or "border_width" in style:
        border_style = {}
        if "border_color" in style:
            rgb = _normalize_color(style["border_color"], "border_color")
            border_style["color"] = {"color": {"rgbColor": rgb}}
        if "border_width" in style:
            border_style["width"] = {"magnitude": style["border_width"], "unit": "PT"}
        border_style["dashStyle"] = "SOLID"

        # Apply to all borders
        for border_name in ["borderTop", "borderBottom", "borderLeft", "borderRight"]:
            table_cell_style[border_name] = border_style
            fields.append(border_name)

    # Padding
    for padding_name in ["padding_top", "padding_bottom", "padding_left", "padding_right"]:
        if padding_name in style:
            api_name = padding_name.replace("_", "").replace("padding", "padding")
            # Convert padding_top -> paddingTop
            api_name = "padding" + padding_name.split("_")[1].capitalize()
            table_cell_style[api_name] = {
                "magnitude": style[padding_name],
                "unit": "PT"
            }
            fields.append(api_name)

    # Content alignment
    if "content_alignment" in style:
        table_cell_style["contentAlignment"] = style["content_alignment"]
        fields.append("contentAlignment")

    # Note: updateTableCellStyle uses a oneof field - must use EITHER tableRange
    # OR tableCellLocation, but not both. We use tableRange for range operations.
    return {
        "updateTableCellStyle": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index},
                    "rowIndex": row_start,
                    "columnIndex": column_start,
                },
                "rowSpan": row_end - row_start,
                "columnSpan": column_end - column_start,
            },
            "tableCellStyle": table_cell_style,
            "fields": ",".join(fields),
        }
    }


def create_update_table_column_properties_request(
    table_start_index: int, column_index: int, width: float
) -> Dict[str, Any]:
    """
    Create an updateTableColumnProperties request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        column_index: Column index to update
        width: Column width in points

    Returns:
        Dictionary representing the updateTableColumnProperties request
    """
    return {
        "updateTableColumnProperties": {
            "tableStartLocation": {"index": table_start_index},
            "columnIndices": [column_index],
            "tableColumnProperties": {
                "widthType": "FIXED_WIDTH",
                "width": {"magnitude": width, "unit": "PT"},
            },
            "fields": "widthType,width",
        }
    }


def create_update_table_row_style_request(
    table_start_index: int, row_index: int, min_height: float
) -> Dict[str, Any]:
    """
    Create an updateTableRowStyle request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_index: Row index to update
        min_height: Minimum row height in points

    Returns:
        Dictionary representing the updateTableRowStyle request
    """
    return {
        "updateTableRowStyle": {
            "tableStartLocation": {"index": table_start_index},
            "rowIndices": [row_index],
            "tableRowStyle": {
                "minRowHeight": {"magnitude": min_height, "unit": "PT"},
            },
            "fields": "minRowHeight",
        }
    }


def create_merge_table_cells_request(
    table_start_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
) -> Dict[str, Any]:
    """
    Create a mergeTableCells request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_start: Starting row (inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (inclusive)
        column_end: Ending column (exclusive)

    Returns:
        Dictionary representing the mergeTableCells request
    """
    return {
        "mergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index},
                    "rowIndex": row_start,
                    "columnIndex": column_start,
                },
                "rowSpan": row_end - row_start,
                "columnSpan": column_end - column_start,
            }
        }
    }


def create_unmerge_table_cells_request(
    table_start_index: int,
    row_start: int,
    row_end: int,
    column_start: int,
    column_end: int,
) -> Dict[str, Any]:
    """
    Create an unmergeTableCells request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        row_start: Starting row (inclusive)
        row_end: Ending row (exclusive)
        column_start: Starting column (inclusive)
        column_end: Ending column (exclusive)

    Returns:
        Dictionary representing the unmergeTableCells request
    """
    return {
        "unmergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index},
                    "rowIndex": row_start,
                    "columnIndex": column_start,
                },
                "rowSpan": row_end - row_start,
                "columnSpan": column_end - column_start,
            }
        }
    }


def create_pin_table_header_rows_request(
    table_start_index: int, pinned_rows_count: int
) -> Dict[str, Any]:
    """
    Create a pinTableHeaderRows request for Google Docs API.

    Args:
        table_start_index: Start index of the table
        pinned_rows_count: Number of header rows to pin (0 to unpin)

    Returns:
        Dictionary representing the pinTableHeaderRows request
    """
    return {
        "pinTableHeaderRows": {
            "tableStartLocation": {"index": table_start_index},
            "pinnedHeaderRowsCount": pinned_rows_count,
        }
    }


# =============================================================================
# PARAGRAPH OPERATIONS
# =============================================================================


def create_update_paragraph_style_request(
    start_index: int,
    end_index: int,
    alignment: str = None,
    line_spacing: float = None,
    space_above: float = None,
    space_below: float = None,
    indent_first_line: float = None,
    indent_start: float = None,
    indent_end: float = None,
    heading_id: str = None,
    named_style_type: str = None,
) -> Dict[str, Any]:
    """
    Create an updateParagraphStyle request for Google Docs API.

    Args:
        start_index: Start position of paragraphs to style
        end_index: End position of paragraphs to style
        alignment: Text alignment ("START", "CENTER", "END", "JUSTIFIED")
        line_spacing: Line spacing multiplier (e.g., 1.0, 1.5, 2.0)
        space_above: Space before paragraph in points
        space_below: Space after paragraph in points
        indent_first_line: First line indent in points
        indent_start: Left/start indent in points
        indent_end: Right/end indent in points
        heading_id: Heading ID for linking
        named_style_type: Named style type

    Returns:
        Dictionary representing the updateParagraphStyle request
    """
    paragraph_style = {}
    fields = []

    if alignment:
        paragraph_style["alignment"] = alignment
        fields.append("alignment")

    if line_spacing is not None:
        paragraph_style["lineSpacing"] = line_spacing * 100  # API uses percentage
        fields.append("lineSpacing")

    if space_above is not None:
        paragraph_style["spaceAbove"] = {"magnitude": space_above, "unit": "PT"}
        fields.append("spaceAbove")

    if space_below is not None:
        paragraph_style["spaceBelow"] = {"magnitude": space_below, "unit": "PT"}
        fields.append("spaceBelow")

    if indent_first_line is not None:
        paragraph_style["indentFirstLine"] = {"magnitude": indent_first_line, "unit": "PT"}
        fields.append("indentFirstLine")

    if indent_start is not None:
        paragraph_style["indentStart"] = {"magnitude": indent_start, "unit": "PT"}
        fields.append("indentStart")

    if indent_end is not None:
        paragraph_style["indentEnd"] = {"magnitude": indent_end, "unit": "PT"}
        fields.append("indentEnd")

    if heading_id:
        paragraph_style["headingId"] = heading_id
        fields.append("headingId")

    if named_style_type:
        paragraph_style["namedStyleType"] = named_style_type
        fields.append("namedStyleType")

    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "paragraphStyle": paragraph_style,
            "fields": ",".join(fields),
        }
    }


def create_delete_paragraph_bullets_request(
    start_index: int, end_index: int
) -> Dict[str, Any]:
    """
    Create a deleteParagraphBullets request for Google Docs API.

    Args:
        start_index: Start position of paragraphs
        end_index: End position of paragraphs

    Returns:
        Dictionary representing the deleteParagraphBullets request
    """
    return {
        "deleteParagraphBullets": {
            "range": {"startIndex": start_index, "endIndex": end_index}
        }
    }


# =============================================================================
# DOCUMENT STRUCTURE OPERATIONS
# =============================================================================


def create_insert_page_break_request(index: int) -> Dict[str, Any]:
    """
    Create an insertPageBreak request for Google Docs API.

    Args:
        index: Position to insert page break

    Returns:
        Dictionary representing the insertPageBreak request
    """
    return {"insertPageBreak": {"location": {"index": index}}}


def create_insert_section_break_request(
    index: int, section_type: str = "NEXT_PAGE"
) -> Dict[str, Any]:
    """
    Create an insertSectionBreak request for Google Docs API.

    Args:
        index: Position to insert section break
        section_type: Type of section break ("NEXT_PAGE" or "CONTINUOUS")

    Returns:
        Dictionary representing the insertSectionBreak request
    """
    return {
        "insertSectionBreak": {
            "location": {"index": index},
            "sectionType": section_type,
        }
    }


def create_update_document_style_request(
    margin_top: float = None,
    margin_bottom: float = None,
    margin_left: float = None,
    margin_right: float = None,
    page_width: float = None,
    page_height: float = None,
    use_first_page_header_footer: bool = None,
    use_even_page_header_footer: bool = None,
) -> Dict[str, Any]:
    """
    Create an updateDocumentStyle request for Google Docs API.

    Args:
        margin_top: Top margin in points
        margin_bottom: Bottom margin in points
        margin_left: Left margin in points
        margin_right: Right margin in points
        page_width: Page width in points
        page_height: Page height in points
        use_first_page_header_footer: Enable different first page header/footer
        use_even_page_header_footer: Enable different even/odd page headers/footers

    Returns:
        Dictionary representing the updateDocumentStyle request
    """
    document_style = {}
    fields = []

    if margin_top is not None:
        document_style["marginTop"] = {"magnitude": margin_top, "unit": "PT"}
        fields.append("marginTop")

    if margin_bottom is not None:
        document_style["marginBottom"] = {"magnitude": margin_bottom, "unit": "PT"}
        fields.append("marginBottom")

    if margin_left is not None:
        document_style["marginLeft"] = {"magnitude": margin_left, "unit": "PT"}
        fields.append("marginLeft")

    if margin_right is not None:
        document_style["marginRight"] = {"magnitude": margin_right, "unit": "PT"}
        fields.append("marginRight")

    if page_width is not None or page_height is not None:
        page_size = {}
        if page_width is not None:
            page_size["width"] = {"magnitude": page_width, "unit": "PT"}
        if page_height is not None:
            page_size["height"] = {"magnitude": page_height, "unit": "PT"}
        document_style["pageSize"] = page_size
        fields.append("pageSize")

    if use_first_page_header_footer is not None:
        document_style["useFirstPageHeaderFooter"] = use_first_page_header_footer
        fields.append("useFirstPageHeaderFooter")

    if use_even_page_header_footer is not None:
        document_style["useEvenPageHeaderFooter"] = use_even_page_header_footer
        fields.append("useEvenPageHeaderFooter")

    return {
        "updateDocumentStyle": {
            "documentStyle": document_style,
            "fields": ",".join(fields),
        }
    }


def create_insert_footnote_request(index: int) -> Dict[str, Any]:
    """
    Create a createFootnote request for Google Docs API.

    Args:
        index: Position to insert footnote reference

    Returns:
        Dictionary representing the createFootnote request
    """
    return {"createFootnote": {"location": {"index": index}}}


def create_delete_header_request(header_id: str) -> Dict[str, Any]:
    """
    Create a deleteHeader request for Google Docs API.

    Args:
        header_id: ID of the header to delete

    Returns:
        Dictionary representing the deleteHeader request
    """
    return {"deleteHeader": {"headerId": header_id}}


def create_delete_footer_request(footer_id: str) -> Dict[str, Any]:
    """
    Create a deleteFooter request for Google Docs API.

    Args:
        footer_id: ID of the footer to delete

    Returns:
        Dictionary representing the deleteFooter request
    """
    return {"deleteFooter": {"footerId": footer_id}}


# =============================================================================
# NAMED RANGES OPERATIONS
# =============================================================================


def create_named_range_request(
    name: str, start_index: int, end_index: int
) -> Dict[str, Any]:
    """
    Create a createNamedRange request for Google Docs API.

    Args:
        name: Name for the range
        start_index: Start position of the range
        end_index: End position of the range

    Returns:
        Dictionary representing the createNamedRange request
    """
    return {
        "createNamedRange": {
            "name": name,
            "range": {"startIndex": start_index, "endIndex": end_index},
        }
    }


def create_delete_named_range_request(
    named_range_id: str = None, name: str = None
) -> Dict[str, Any]:
    """
    Create a deleteNamedRange request for Google Docs API.

    Args:
        named_range_id: ID of the named range to delete
        name: Name of the named range to delete

    Returns:
        Dictionary representing the deleteNamedRange request
    """
    request = {"deleteNamedRange": {}}

    if named_range_id:
        request["deleteNamedRange"]["namedRangeId"] = named_range_id
    elif name:
        request["deleteNamedRange"]["name"] = name

    return request


def create_replace_named_range_content_request(
    text: str, named_range_id: str = None, name: str = None
) -> Dict[str, Any]:
    """
    Create a replaceNamedRangeContent request for Google Docs API.

    Args:
        text: New text to insert
        named_range_id: ID of the named range
        name: Name of the named range

    Returns:
        Dictionary representing the replaceNamedRangeContent request
    """
    request = {"replaceNamedRangeContent": {"text": text}}

    if named_range_id:
        request["replaceNamedRangeContent"]["namedRangeId"] = named_range_id
    elif name:
        # API expects "namedRangeName", not "name"
        request["replaceNamedRangeContent"]["namedRangeName"] = name

    return request


# =============================================================================
# DOCUMENT TABS OPERATIONS
# =============================================================================


def create_add_document_tab_request(
    tab_properties: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create an addDocumentTab request for Google Docs API.

    Args:
        tab_properties: Properties for the new tab. Can include:
            - title: User-visible name of the tab
            - parentTabId: ID of parent tab for nested tabs (optional)
            - index: Position to insert the tab (optional)

    Returns:
        Dictionary representing the addDocumentTab request
    """
    # The correct request type is "addDocumentTab", not "createDocumentTab"
    return {"addDocumentTab": {"tabProperties": tab_properties}}


def create_delete_tab_request(tab_id: str) -> Dict[str, Any]:
    """
    Create a deleteTab request for Google Docs API.

    Args:
        tab_id: ID of the tab to delete

    Returns:
        Dictionary representing the deleteTab request
    """
    return {"deleteTab": {"tabId": tab_id}}


def create_update_tab_properties_request(
    tab_id: str, properties: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create an updateDocumentTabProperties request for Google Docs API.

    Args:
        tab_id: ID of the tab to update
        properties: Properties to update (title, iconEmoji, etc.)

    Returns:
        Dictionary representing the updateDocumentTabProperties request
    """
    # Build fields list from provided properties (don't include tabId in fields)
    fields = list(properties.keys())

    # tabId must be inside tabProperties, not at top level
    tab_properties = {"tabId": tab_id}
    tab_properties.update(properties)

    return {
        "updateDocumentTabProperties": {
            "tabProperties": tab_properties,
            "fields": ",".join(fields),
        }
    }


# =============================================================================
# MEDIA OPERATIONS
# =============================================================================


def create_insert_image_request(
    index: int, image_uri: str, width: int = None, height: int = None
) -> Dict[str, Any]:
    """
    Create an insertInlineImage request for Google Docs API.

    Args:
        index: Position to insert image
        image_uri: URI of the image (Drive URL or public URL)
        width: Image width in points
        height: Image height in points

    Returns:
        Dictionary representing the insertInlineImage request
    """
    request = {"insertInlineImage": {"location": {"index": index}, "uri": image_uri}}

    # Add size properties if specified
    object_size = {}
    if width is not None:
        object_size["width"] = {"magnitude": width, "unit": "PT"}
    if height is not None:
        object_size["height"] = {"magnitude": height, "unit": "PT"}

    if object_size:
        request["insertInlineImage"]["objectSize"] = object_size

    return request


def create_replace_image_request(image_object_id: str, new_uri: str) -> Dict[str, Any]:
    """
    Create a replaceImage request for Google Docs API.

    Args:
        image_object_id: ID of the inline image object to replace
        new_uri: URI of the new image

    Returns:
        Dictionary representing the replaceImage request
    """
    return {
        "replaceImage": {
            "imageObjectId": image_object_id,
            "uri": new_uri,
            "imageReplaceMethod": "CENTER_CROP",
        }
    }


def create_delete_positioned_object_request(object_id: str) -> Dict[str, Any]:
    """
    Create a deletePositionedObject request for Google Docs API.

    Args:
        object_id: ID of the positioned object to delete

    Returns:
        Dictionary representing the deletePositionedObject request
    """
    return {"deletePositionedObject": {"objectId": object_id}}


# =============================================================================
# LIST OPERATIONS
# =============================================================================


def create_bullet_list_request(
    start_index: int, end_index: int, list_type: str = "UNORDERED"
) -> Dict[str, Any]:
    """
    Create a createParagraphBullets request for Google Docs API.

    Args:
        start_index: Start of text range to convert to list
        end_index: End of text range to convert to list
        list_type: Type of list ("UNORDERED" or "ORDERED")

    Returns:
        Dictionary representing the createParagraphBullets request
    """
    bullet_preset = (
        "BULLET_DISC_CIRCLE_SQUARE"
        if list_type == "UNORDERED"
        else "NUMBERED_DECIMAL_ALPHA_ROMAN"
    )

    return {
        "createParagraphBullets": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "bulletPreset": bullet_preset,
        }
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================


def validate_operation(operation: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate a batch operation dictionary.

    Args:
        operation: Operation dictionary to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    op_type = operation.get("type")
    if not op_type:
        return False, "Missing 'type' field"

    # Validate required fields for each operation type
    required_fields = {
        "insert_text": ["index", "text"],
        "delete_text": ["start_index", "end_index"],
        "replace_text": ["start_index", "end_index", "text"],
        "format_text": ["start_index", "end_index"],
        "insert_table": ["index", "rows", "columns"],
        "insert_page_break": ["index"],
        "find_replace": ["find_text", "replace_text"],
        "insert_table_row": ["table_start_index", "row_index"],
        "delete_table_row": ["table_start_index", "row_index"],
        "insert_table_column": ["table_start_index", "column_index"],
        "delete_table_column": ["table_start_index", "column_index"],
        "format_table_cells": ["table_start_index", "row_start", "row_end", "column_start", "column_end"],
        "merge_table_cells": ["table_start_index", "row_start", "row_end", "column_start", "column_end"],
        "update_paragraph_style": ["start_index", "end_index"],
        "insert_section_break": ["index"],
        "create_named_range": ["name", "start_index", "end_index"],
        "replace_named_range_content": ["text"],
    }

    if op_type not in required_fields:
        return False, f"Unsupported operation type: {op_type or 'None'}"

    for field in required_fields[op_type]:
        if field not in operation:
            return False, f"Missing required field: {field}"

    return True, ""
