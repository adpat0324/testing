import tempfile
from pathlib import Path
from typing import List
from io import BytesIO
from PIL import Image
import openpyxl
from openpyxl.chart import (
    BarChart, LineChart, PieChart, AreaChart, ScatterChart, 
    BubbleChart, RadarChart, DoughnutChart
)
from openpyxl.utils import get_column_letter
import pandas as pd


class ExcelParser(BaseParser):
    def __init__(self) -> None:
        super().__init__(name="EXCEL_PARSER")
    
    def _get_used_range(self, worksheet):
        """
        Determine the actual used range of a worksheet, ignoring completely blank rows/columns.
        Returns (min_row, max_row, min_col, max_col)
        """
        # Get dimensions
        if worksheet.calculate_dimension() == 'A1:A1' and worksheet['A1'].value is None:
            return None
        
        min_row = worksheet.min_row
        max_row = worksheet.max_row
        min_col = worksheet.min_column
        max_col = worksheet.max_column
        
        # Find actual last row with data
        for row in range(max_row, min_row - 1, -1):
            if any(worksheet.cell(row, col).value is not None for col in range(min_col, max_col + 1)):
                max_row = row
                break
        
        # Find actual last column with data
        for col in range(max_col, min_col - 1, -1):
            if any(worksheet.cell(row, col).value is not None for row in range(min_row, max_row + 1)):
                max_col = col
                break
        
        return min_row, max_row, min_col, max_col
    
    def _is_table_region(self, worksheet, start_row, start_col, end_row, end_col):
        """
        Heuristic to determine if a region contains a structured table.
        """
        # Check if first row looks like headers (all non-empty)
        first_row_filled = sum(1 for col in range(start_col, end_col + 1) 
                               if worksheet.cell(start_row, col).value is not None)
        total_cols = end_col - start_col + 1
        
        # If first row is mostly filled (>50%), likely a header row
        if first_row_filled / total_cols > 0.5:
            return True
        
        return False
    
    def _extract_table_to_markdown(self, worksheet, start_row, start_col, end_row, end_col, file_path_spaces):
        """
        Extract a table region and convert to markdown.
        """
        self.logger.debug(f"{file_path_spaces} - Extracting table from cells "
                         f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}")
        
        md = ""
        rows_data = []
        
        # Read all rows
        for row_idx in range(start_row, end_row + 1):
            row_data = []
            for col_idx in range(start_col, end_col + 1):
                cell = worksheet.cell(row_idx, col_idx)
                # Get calculated value for formulas, not the formula itself
                value = cell.value if cell.value is not None else ""
                # Clean up the value
                value = str(value).strip().replace("\n", " ")
                row_data.append(value)
            rows_data.append(row_data)
        
        # Convert to markdown table
        if rows_data:
            # First row as header
            md += "| " + " | ".join(rows_data[0]) + " |\n"
            # Separator
            md += "| " + " | ".join(["---"] * len(rows_data[0])) + " |\n"
            # Data rows
            for row in rows_data[1:]:
                md += "| " + " | ".join(row) + " |\n"
            md += "\n"
        
        return md
    
    def _convert_chart_to_markdown(self, chart, chart_count, worksheet, file_path_spaces):
        """
        Convert Excel chart to markdown representation with data table.
        """
        self.logger.debug(f"{file_path_spaces} - Processing chart number {chart_count}")
        
        md_content = f"**Chart {chart_count}**\n"
        
        # Determine chart type
        chart_type = type(chart).__name__
        md_content += f"_Chart Type: {chart_type}_\n\n"
        
        try:
            # Extract chart title if available
            if hasattr(chart, 'title') and chart.title:
                md_content += f"**{chart.title.text.rich.text if hasattr(chart.title.text, 'rich') else chart.title}**\n\n"
            
            markdown_chart_table = []
            
            # Handle Pie/Doughnut Charts
            if isinstance(chart, (PieChart, DoughnutChart)):
                if chart.series:
                    series = chart.series[0]
                    # Get categories and values
                    if hasattr(series, 'cat') and series.cat:
                        categories = self._get_reference_values(series.cat, worksheet)
                    else:
                        categories = [f"Category {i+1}" for i in range(len(series.val.numRef.numCache.pt) if hasattr(series.val, 'numRef') else 0)]
                    
                    values = self._get_reference_values(series.val, worksheet)
                    
                    markdown_chart_table.append("| Slice Label | Value |")
                    markdown_chart_table.append("|---|---|")
                    for label, value in zip(categories, values):
                        markdown_chart_table.append(f"| {label} | {value} |")
            
            # Handle Scatter/Bubble Charts
            elif isinstance(chart, (ScatterChart, BubbleChart)):
                markdown_chart_table.append("| Series | X Value | Y Value |" + (" Bubble Size |" if isinstance(chart, BubbleChart) else ""))
                markdown_chart_table.append("|---|---|---|" + ("---|" if isinstance(chart, BubbleChart) else ""))
                
                for series in chart.series:
                    series_name = series.title.value if hasattr(series, 'title') and series.title else "Series"
                    x_values = self._get_reference_values(series.xVal, worksheet) if hasattr(series, 'xVal') and series.xVal else []
                    y_values = self._get_reference_values(series.yVal, worksheet) if hasattr(series, 'yVal') and series.yVal else []
                    
                    if isinstance(chart, BubbleChart) and hasattr(series, 'bubbleSize') and series.bubbleSize:
                        bubble_sizes = self._get_reference_values(series.bubbleSize, worksheet)
                        for x, y, size in zip(x_values, y_values, bubble_sizes):
                            markdown_chart_table.append(f"| {series_name} | {x} | {y} | {size} |")
                    else:
                        for x, y in zip(x_values, y_values):
                            markdown_chart_table.append(f"| {series_name} | {x} | {y} |")
            
            # Handle Category-based Charts (Bar, Column, Line, Area, Radar)
            elif isinstance(chart, (BarChart, LineChart, AreaChart, RadarChart)):
                # Get categories from first series
                if chart.series:
                    first_series = chart.series[0]
                    if hasattr(first_series, 'cat') and first_series.cat:
                        categories = self._get_reference_values(first_series.cat, worksheet)
                    else:
                        categories = []
                    
                    # Create header
                    header_row = ["Category"] + [s.title.value if hasattr(s, 'title') and s.title else f"Series {i+1}" 
                                                  for i, s in enumerate(chart.series)]
                    markdown_chart_table.append("| " + " | ".join(header_row) + " |")
                    markdown_chart_table.append("| " + " | ".join(["---"] * len(header_row)) + " |")
                    
                    # Get all series values
                    all_series_values = []
                    for series in chart.series:
                        values = self._get_reference_values(series.val, worksheet)
                        all_series_values.append(values)
                    
                    # Create rows
                    for idx in range(len(categories) if categories else (max(len(v) for v in all_series_values) if all_series_values else 0)):
                        row = [categories[idx] if idx < len(categories) else f"Row {idx+1}"]
                        for series_values in all_series_values:
                            row.append(series_values[idx] if idx < len(series_values) else "")
                        markdown_chart_table.append("| " + " | ".join(map(str, row)) + " |")
            
            else:
                markdown_chart_table.append(f"Unsupported chart type: {chart_type}")
                self.logger.debug(f"{file_path_spaces} - Unsupported chart type: {chart_type}")
            
            # Add chart markdown to content
            if markdown_chart_table:
                md_content += "\n".join(markdown_chart_table) + "\n\n"
        
        except Exception as e:
            self.logger.error(f"{file_path_spaces} - Error processing chart: {e}")
            md_content += f"_Error extracting chart data: {e}_\n\n"
        
        return md_content
    
    def _get_reference_values(self, reference, worksheet):
        """
        Extract values from a chart data reference.
        """
        values = []
        try:
            if hasattr(reference, 'numRef') and reference.numRef:
                # Numeric reference
                if hasattr(reference.numRef, 'numCache') and reference.numRef.numCache:
                    values = [pt.v for pt in reference.numRef.numCache.pt]
                elif hasattr(reference.numRef, 'f') and reference.numRef.f:
                    # Parse the formula reference
                    values = self._parse_formula_reference(reference.numRef.f, worksheet)
            elif hasattr(reference, 'strRef') and reference.strRef:
                # String reference
                if hasattr(reference.strRef, 'strCache') and reference.strRef.strCache:
                    values = [pt.v for pt in reference.strRef.strCache.pt]
                elif hasattr(reference.strRef, 'f') and reference.strRef.f:
                    values = self._parse_formula_reference(reference.strRef.f, worksheet)
        except Exception as e:
            self.logger.debug(f"Error getting reference values: {e}")
        
        return values
    
    def _parse_formula_reference(self, formula, worksheet):
        """
        Parse a formula reference string like 'Sheet1!$A$1:$A$10' and extract values.
        """
        values = []
        try:
            # Remove sheet name if present
            if '!' in formula:
                formula = formula.split('!')[-1]
            
            # Remove $ signs
            formula = formula.replace('$', '')
            
            # Parse range
            if ':' in formula:
                start, end = formula.split(':')
                # This is a simplified parser - for production use openpyxl's range parser
                from openpyxl.utils import coordinate_to_tuple, column_index_from_string
                
                start_row, start_col = coordinate_to_tuple(start)
                end_row, end_col = coordinate_to_tuple(end)
                
                for row in range(start_row, end_row + 1):
                    for col in range(start_col, end_col + 1):
                        cell_value = worksheet.cell(row, col).value
                        if cell_value is not None:
                            values.append(cell_value)
        except Exception as e:
            self.logger.debug(f"Error parsing formula reference: {e}")
        
        return values
    
    def _extract_images_to_markdown(self, worksheet, images_folder, file_path, sheet_name, file_path_spaces):
        """
        Extract images from worksheet and convert to markdown.
        """
        md_content = ""
        
        if hasattr(worksheet, '_images') and worksheet._images:
            for img_idx, img in enumerate(worksheet._images):
                try:
                    figure_count = img_idx + 1
                    self.logger.debug(f"{file_path_spaces} - Processing image {figure_count} in sheet '{sheet_name}'")
                    
                    # Get image data
                    img_data = img._data()
                    image = Image.open(BytesIO(img_data))
                    
                    # Check image size
                    img_width_px, img_height_px = image.size
                    image_area_px = img_width_px * img_height_px
                    
                    min_image_size = 500
                    if image_area_px < min_image_size:
                        self.logger.debug(f"{file_path_spaces} - Skipping small image {figure_count} "
                                        f"({img_width_px}x{img_height_px} = {image_area_px}, threshold: {min_image_size})")
                        continue
                    
                    # Save image
                    img_path = Path(f"{images_folder}/{file_path.name.replace(' ', '-')}-{sheet_name.replace(' ', '-')}-{figure_count}.png")
                    image.save(img_path)
                    self.logger.debug(f"{file_path_spaces} - Image saved at {img_path}")
                    
                    # Add to markdown
                    md_content += f"**Figure {figure_count}**\n"
                    md_content += self._md4vision(img_path)
                    md_content += "\n\n"
                
                except Exception as e:
                    self.logger.error(f"{file_path_spaces} - Error processing image {img_idx + 1}: {e}")
        
        return md_content
    
    def _process_sheet(self, worksheet, sheet_name, images_folder, file_path, file_path_spaces):
        """
        Process a single worksheet and convert to markdown.
        """
        self.logger.info(f"{file_path_spaces} - Processing sheet: '{sheet_name}'")
        
        md_content = f"# {sheet_name}\n\n"
        
        # Get used range
        used_range = self._get_used_range(worksheet)
        if not used_range:
            self.logger.info(f"{file_path_spaces} - Sheet '{sheet_name}' is empty, skipping")
            return ""
        
        min_row, max_row, min_col, max_col = used_range
        
        # Extract main table/data
        if self._is_table_region(worksheet, min_row, min_col, max_row, max_col):
            md_content += self._extract_table_to_markdown(worksheet, min_row, min_col, max_row, max_col, file_path_spaces)
        else:
            # If not a clear table, still output as table format
            md_content += self._extract_table_to_markdown(worksheet, min_row, min_col, max_row, max_col, file_path_spaces)
        
        # Process charts
        if hasattr(worksheet, '_charts') and worksheet._charts:
            for chart_idx, chart in enumerate(worksheet._charts):
                try:
                    md_content += self._convert_chart_to_markdown(chart, chart_idx + 1, worksheet, file_path_spaces)
                except Exception as e:
                    self.logger.error(f"{file_path_spaces} - Error processing chart {chart_idx + 1} in sheet '{sheet_name}': {e}")
        
        # Process images
        md_content += self._extract_images_to_markdown(worksheet, images_folder, file_path, sheet_name, file_path_spaces)
        
        return md_content
    
    def _extract_macro_info(self, file_path, file_path_spaces):
        """
        Extract macro information from xlsm files.
        Note: openpyxl cannot execute or fully read VBA code, but we can detect its presence.
        """
        md_content = ""
        
        try:
            # Check if file is macro-enabled
            if file_path.suffix.lower() in ['.xlsm', '.xlam']:
                wb = openpyxl.load_workbook(file_path, keep_vba=True)
                
                if wb.vba_archive:
                    self.logger.info(f"{file_path_spaces} - Macro-enabled workbook detected")
                    md_content += "## Macro Information\n\n"
                    md_content += "_This workbook contains VBA macros. "
                    md_content += "Macro code cannot be fully extracted by this parser, but its presence is noted._\n\n"
                    
                    # Try to list macro modules if possible
                    try:
                        # This is limited - openpyxl doesn't fully expose VBA structure
                        md_content += "_Macro modules detected in workbook_\n\n"
                    except:
                        pass
        
        except Exception as e:
            self.logger.debug(f"{file_path_spaces} - Could not extract macro info: {e}")
        
        return md_content
    
    def parse(self, file_path: Path, file_path_spaces: str) -> List[dict]:
        """
        Parse Excel file and convert to markdown documents per sheet.
        """
        documents = []
        
        with tempfile.TemporaryDirectory(prefix="excel_img_render_") as tmp_img_dir:
            images_folder = Path(tmp_img_dir)
            
            try:
                self.logger.info(f"{file_path_spaces} - Extracting content from Excel file... ")
                
                # Load workbook with data_only=True to get calculated values instead of formulas
                wb = openpyxl.load_workbook(file_path, data_only=True, keep_vba=True)
                
                # Extract macro info if present
                macro_info = self._extract_macro_info(file_path, file_path_spaces)
                
                total_sheets = len(wb.sheetnames)
                
                for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                    self.logger.info(f"{file_path_spaces} - **Sheet {sheet_idx + 1}/{total_sheets}: '{sheet_name}'**...")
                    
                    try:
                        worksheet = wb[sheet_name]
                        
                        # Process sheet
                        sheet_markdown = self._process_sheet(worksheet, sheet_name, images_folder, file_path, file_path_spaces)
                        
                        # Add macro info to first sheet if present
                        if sheet_idx == 0 and macro_info:
                            sheet_markdown = macro_info + sheet_markdown
                        
                        # Skip empty sheets
                        if not sheet_markdown.strip() or sheet_markdown.strip() == f"# {sheet_name}":
                            self.logger.info(f"{file_path_spaces} - Sheet '{sheet_name}' has no content, skipping")
                            continue
                        
                        metadata = {
                            "file_path": file_path_spaces,
                            "sheet": sheet_name,
                            "sheet_number": sheet_idx + 1,
                            "file_hash": compute_file_hash(file_path)
                        }
                        metadata.update(self._load_sidecar_metadata(file_path))
                        
                        documents.append({"markdown": sheet_markdown, "metadata": metadata})
                    
                    except Exception as e:
                        self.logger.error(f"{file_path_spaces} - X Error on sheet '{sheet_name}': {e}")
                        continue
                
                self.logger.success(f"✓ Converted {file_path_spaces}")
                return documents
            
            except Exception as e:
                self.logger.error(f"Failed to process {file_path_spaces}: {e}")
                return []
