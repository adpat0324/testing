class PDFParser(BaseParser):
    def __init__(self) -> None:
        super().__init__(name="PDF_PARSER")
    
    def parse(self, file_path: Path, file_path_spaces: str) -> List[dict]:
        with tempfile.TemporaryDirectory(prefix="img_render_") as tmp_img_dir:
            tmp_path = Path(tmp_img_dir)
            try:
                self.logger.info(f"{file_path_spaces} - Extracting text from PDF... ")
                md_text = pymupdf4llm.to_markdown(
                    str(file_path),
                    page_chunks=True,
                    write_images=True,
                    image_path=str(tmp_path),
                    image_format="png",
                    dpi=self.pixels,
                    image_size_limit=0.1,
                    table_strategy="lines",
                )
                
                documents = []
                pages = len(md_text)
                for i, page in enumerate(md_text):
                    self.logger.info(f"{file_path_spaces} - **Page {i+1}/{pages}**...")
                    page_markdown = page['text']
                    page_number = page['metadata']['page']
                    image_files_path = Path(f"{tmp_path}/{file_path.name.replace(' ', '-')}-{int(page_number) - 1}-*.png")
                    try:
                        self.logger.debug(f"{file_path_spaces} - Replacing images in page {i+1} with markdown using GPT vision")
                        page_markdown = self.replace_images_with_markdown(page_markdown, image_files_path)
                    except Exception as err:
                        self.logger.error(f"{file_path_spaces} - X Error on page {i+1}: {err}")
                        continue
                    
                    metadata = {"file_path": file_path_spaces, "page": int(page_number), "file_hash": compute_file_hash(file_path)}
                    metadata.update(self._load_sidecar_metadata(file_path))
                    documents.append({"markdown": page_markdown, "metadata": metadata})
                
                self.logger.success(f"✓ Converted {file_path_spaces}")
                return documents
            except Exception as e:
                self.logger.error(f"Failed to process {file_path_spaces}: {e}")
                return []


class PowerPointParser(BaseParser):
    def __init__(self) -> None:
        super().__init__(name="POWERPOINT_PARSER")
    
    @staticmethod
    def classify_text(text, font_size):
        """
        Classify text as title, heading, or body based on font size.
        """
        if font_size > 25:  # Titles (adjust threshold as needed)
            return f"# {text.strip()}\n\n"
        elif font_size > 20:  # Headings
            return f"## {text.strip()}\n\n"
        else:  # Body text
            return f"{text.strip()}\n\n"
    
    @staticmethod
    def extract_text_with_formatting(shape):
        md = ""
        for paragraph in shape.text_frame.paragraphs:
            para_md = ""
            for run in paragraph.runs:
                text = run.text.strip()
                # Markdown formatting
                if run.font.bold:
                    text = f"**{text}**"
                if run.font.italic:
                    text = f"*{text}*"
                if run.font.underline:
                    text = f"<u>{text}</u>"  # Markdown doesn't support underline natively
                if run.hyperlink and run.hyperlink.address:
                    text = f"[{text}]({run.hyperlink.address})"
                
                # Font size heading
                font_size = run.font.size.pt if run.font.size else 12
                if int(font_size) >= 25:  # title
                    text = f"# {text}\n\n"
                elif int(font_size) >= 20:  # heading
                    text = f"## {text.strip()}\n\n"
                
                para_md += text
            
            md += f"{para_md}\n\n"
        return md
    
    @staticmethod
    def find_caption_for_shape(text_shapes, target_shape, v_threshold = 400, h_threshold = 0):
        target_top = target_shape.top
        target_left = target_shape.left
        target_bottom = target_shape.top + target_shape.height
        target_right = target_shape.left + target_shape.width
        best_caption = None
        min_distance = float('inf')
        
        for text_shape in text_shapes:
            text_top = text_shape.top
            text_left = text_shape.left
            text_bottom = text_shape.top + text_shape.height
            text_right = text_shape.left + text_shape.width
            
            vertical_distance = min(abs(text_bottom - target_top), abs(text_top - target_bottom))
            horizontal_overlap = max(0, min(target_right, text_right) - max(target_left, text_left))
            
            if horizontal_overlap > h_threshold and vertical_distance < v_threshold:
                if vertical_distance < min_distance:
                    min_distance = vertical_distance
                    best_caption = text_shape.text.strip()
        
        return best_caption
    
    def convert_image_to_markdown(self, shape, figure_count, images_folder, file_path, page_number, text_shapes, file_path_spaces, min_image_size=500):
        # Get the actual image dimensions in pixels
        img_stream = shape.image.blob
        img = Image.open(BytesIO(img_stream))
        img_width_px, img_height_px = img.size
        image_area_px = img_width_px * img_height_px
        
        # Check image size to determine if it's worth processing
        if image_area_px < min_image_size:
            self.logger.debug(f"{file_path_spaces} - Skipping small image {{figure_count}} ({img_width_px}x{img_height_px} = {image_area_px}, threshold: {min_image_size})")
            return ""
        
        self.logger.debug(f"{file_path_spaces} - Processing image number {{figure_count}} ({img_width_px}x{img_height_px} = {image_area_px})")
        
        md = ""
        
        img_path = Path(f"{images_folder}/{file_path.name.replace(' ', '-')}-{int(page_number)}-{figure_count}.png")
        img.save(img_path)
        self.logger.debug(f"{file_path_spaces} - Image saved at {img_path}")
        
        caption = self.find_caption_for_shape(text_shapes=text_shapes, target_shape=shape)
        md += f"**Figure {figure_count}: {caption}**\n" if caption else f"**Figure {figure_count}**\n"
        
        self.logger.debug(f"{file_path_spaces} - Replacing image in page with markdown using GPT vision")
        md += self._md4visionPath(img_path))
        return md
    
    def convert_table_to_markdown(self, table_count, text_shapes, shape, file_path_spaces):
        self.logger.debug(f"{file_path_spaces} - Processing table number {table_count}")
        
        md = ""
        
        caption = self.find_caption_for_shape(text_shapes=text_shapes, target_shape=shape)
        md += f"**Table {table_count}: {caption}**\n" if caption else f"**Table {table_count}**\n"
        
        table = shape.table
        markdown_table = []
        for row in table.rows:
            row_content = []
            for cell in row.cells:
                cell_text = cell.text.strip().replace("\n", " ")
                row_content.append(cell_text)
            markdown_table.append(" | " + " | ".join(row_content) + " |")
        
        if markdown_table:
            # Add markdown table header separator (assumes the first row is the header)
            if len(markdown_table) > 1:
                header_separator = "| " + " | ".join(["---"] * len(table.columns)) + " |"
                markdown_table.insert(1, header_separator)
        
        md += "\n".join(markdown_table) + "\n\n"
        return md
    
    def convert_chart_to_markdown(self, shape, chart_count, text_shapes, file_path_spaces):
        
        md_content = ""
        
        chart = shape.chart
        chart_type = chart.chart_type
        markdown_chart_table = []
        
        self.logger.debug(f"{file_path_spaces} - Processing chart number {chart_count}, chart type: {chart_type}")
        
        caption = self.find_caption_for_shape(text_shapes=text_shapes, target_shape=shape)
        md_content += f"**Chart {chart_count}: {caption}**\n" if caption else f"**Chart {chart_count}**\n"
        
        # Add chart type
        md_content += f"_Chart Type: {chart_type}_\n\n"
        
        # Handle different chart types
        
        # PIE & DOUGHNUT (single series, single-level categories)
        if chart_type in [XL_CHART_TYPE.PIE, XL_CHART_TYPE.PIE_EXPLODED,
                          XL_CHART_TYPE.DOUGHNUT, XL_CHART_TYPE.DOUGHNUT_EXPLODED]:
            series = chart.series[0]
            categories = [cat.label for cat in chart.plots[0].categories]
            values = list(series.values)
            markdown_chart_table.append("| Slice Label | Value |")
            markdown_chart_table.append("|---|---|")
            for label, value in zip(categories, values):
                markdown_chart_table.append(f"| {label} | {value} |")
        
        # XY SCATTER (multi-series, x/y values)
        elif chart_type in [
            XL_CHART_TYPE.XY_SCATTER, XL_CHART_TYPE.XY_SCATTER_LINES,
            XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS,
            XL_CHART_TYPE.XY_SCATTER_SMOOTH,
            XL_CHART_TYPE.XY_SCATTER_SMOOTH_NO_MARKERS
        ]:
            markdown_chart_table.append("| Series | X Value | Y Value |")
            markdown_chart_table.append("|---|---|---|")
            for s in chart.series:
                try:
                    x_values = s.x_values
                    y_values = s.y_values
                    for x, y in zip(x_values, y_values):
                        markdown_chart_table.append(f"| {s.name} | {x} | {y} |")
                except Exception as e:
                    markdown_chart_table.append(f"| {s.name} | [Error: {e}] | |")
        
        # CATEGORY-BASED CHARTS (bar, column, line, area, radar, etc.)
        elif chart_type in [
            XL_CHART_TYPE.BAR_CLUSTERED, XL_CHART_TYPE.BAR_STACKED, XL_CHART_TYPE.BAR_STACKED_100,
            XL_CHART_TYPE.COLUMN_CLUSTERED, XL_CHART_TYPE.COLUMN_STACKED, XL_CHART_TYPE.COLUMN_STACKED_100,
            XL_CHART_TYPE.LINE, XL_CHART_TYPE.LINE_MARKERS, XL_CHART_TYPE.LINE_MARKERS_STACKED,
            XL_CHART_TYPE.LINE_MARKERS_STACKED_100, XL_CHART_TYPE.LINE_STACKED, XL_CHART_TYPE.LINE_STACKED_100,
            XL_CHART_TYPE.AREA, XL_CHART_TYPE.AREA_STACKED, XL_CHART_TYPE.AREA_STACKED_100,
            XL_CHART_TYPE.RADAR, XL_CHART_TYPE.RADAR_FILLED, XL_CHART_TYPE.RADAR_MARKERS
        ]:
            # Multi-level categories support
            try:
                categories = chart.plots[0].categories
                # Multi-level: categories.levels is available
                if hasattr(categories, "levels") and categories.depth > 1:
                    # Flattened labels for multi-level
                    flattened = categories.flattened_labels
                    header_row = ["Category"] + categories.depth * [s.name for s in chart.series]
                    markdown_chart_table.append("| " + " | ".join(header_row) + " |")
                    markdown_chart_table.append("| " + " | ".join(["---"] * len(header_row)) + " |")
                    for idx, cat_tuple in enumerate(flattened):
                        row = list(cat_tuple)
                        for s in chart.series:
                            row.append(s.values[idx])
                        markdown_chart_table.append("| " + " | ".join(map(str, row)) + " |")
                else:
                    # Single-level
                    categories = [cat.label for cat in chart.plots[0].categories]
                    header_row = ["Category"] + [s.name for s in chart.series]
                    markdown_chart_table.append("| " + " | ".join(header_row) + " |")
                    markdown_chart_table.append("| " + " | ".join(["---"] * len(header_row)) + " |")
                    for idx, category in enumerate(categories):
                        row = [category]
                        for s in chart.series:
                            row.append(s.values[idx])
                        markdown_chart_table.append("| " + " | ".join(map(str, row)) + " |")
            except Exception as e:
                markdown_chart_table.append(f"Error processing categories: {e}")
        
        # BUBBLE (multi-series, x/y/size)
        elif chart_type in [XL_CHART_TYPE.BUBBLE, XL_CHART_TYPE.BUBBLE_THREE_D_EFFECT]:
            markdown_chart_table.append("| Series | X Value | Y Value | Bubble Size |")
            markdown_chart_table.append("|---|---|---|---|")
            for s in chart.series:
                try:
                    x_values = getattr(s, "x_values", None)
                    y_values = getattr(s, "y_values", None)
                    sizes = getattr(s, "bubble_sizes", None)
                    if x_values is not None and y_values is not None and sizes is not None:
                        for x, y, size in zip(x_values, y_values, sizes):
                            markdown_chart_table.append(f"| {s.name} | {x} | {y} | {size} |")
                    else:
                        markdown_chart_table.append(f"| {s.name} | [Bubble data not available] | | |")
                except Exception as e:
                    markdown_chart_table.append(f"| {s.name} | [Error: {e}] | | |")
        
        elif chart_type == XL_CHART_TYPE.RADAR:
            chart_type == XL_CHART_TYPE.RADAR
            categories = [cat.label for cat in chart.plots[0].categories]
            series = chart.series
            header_row = ["Category"] + [s.name for s in series]
            markdown_chart_table.append("| " + " | ".join(header_row) + " |")
            markdown_chart_table.append("| " + " | ".join(["---"] * len(header_row)) + " |")
            for idx, category in enumerate(categories):
                row = [category]
                for s in series:
                    row.append(s.values[idx])
                markdown_chart_table.append("| " + " | ".join(map(str, row)) + " |")
        
        else:
            # Unsupported chart type
            markdown_chart_table.append(f"Unsupported chart type: {chart_type}")
            self.logger.debug(f"{file_path_spaces} - Unsupported chart type: {chart_type}")
        
        # Add chart markdown to content
        if markdown_chart_table:
            md_content += "\n".join(markdown_chart_table) + "\n\n"
        
        return md_content
    
    def convert_shapes_to_markdown(self, md_content: str, shapes: list, page_number, images_folder: Path, file_path: Path, file_path_spaces: str):
        figure_count = 0
        table_count = 1
        chart_count = 1
        
        # First, collect all shapes that are inside groups to avoid processing them twice
        grouped_shapes = set()
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                for grouped_shape in shape.shapes:
                    grouped_shapes.add(id(grouped_shape))
        
        # Update text_shapes to exclude grouped shapes for caption finding
        text_shapes = [s for s in shapes if s.has_text_frame and s.text.strip() and id(s) not in grouped_shapes]
        
        for shape in shapes:
            # Skip shapes that are part of a group - they'll be processed when we handle the group
            if id(shape) in grouped_shapes:
                continue
            
            # Handle grouped shapes first
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                try:
                    group_shapes = list(shape.shapes)
                    self.logger.debug(f"{file_path_spaces} - Processing group with {len(group_shapes)} shapes")
                    md_content = self.convert_shapes_to_markdown(md_content, group_shapes, page_number, images_folder, file_path, file_path_spaces)
                except Exception as e:
                    self.logger.error(f"{file_path_spaces} - Error processing grouped shapes on slide: {e}")
                continue
            
            # handle text
            if shape.has_text_frame and shape.text.strip():
                md_content += self.extract_text_with_formatting(shape)
            
            # handle images
            elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                image_md = self.convert_image_to_markdown(shape, figure_count, images_folder, file_path, page_number, text_shapes, file_path_spaces)
                if image_md:  # Only add content and increment counter if image was processed
                    md_content += image_md
                    figure_count += 1
            
            # handle tables
            elif shape.has_table:
                md_content += self.convert_table_to_markdown(table_count, text_shapes, shape, file_path_spaces)
                table_count += 1
            
            # handle charts
            elif shape.has_chart:
                try:
                    md_content += self.convert_chart_to_markdown(shape, chart_count, text_shapes, file_path_spaces)
                    chart_count += 1
                except Exception as e:
                    self.logger.error(f"{file_path_spaces} - Error processing chart on slide: {e}")
            
            else:
                self.logger.info(f"{file_path_spaces} - Unhandled shape type: {shape.shape_type}")
        
        md_content += "\n\n"
        
        return md_content
    
    def convert_slide_to_markdown(self, slide, page_number, images_folder: Path, file_path: Path, file_path_spaces: str):
        md_content = ""
        
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            md_content += "**Notes:**"
            md_content += "> " + slide.notes_slide.notes_text_frame.text.replace("\n", "\n> ")
        
        # Sort shapes by their top and left positions to enforce visual order
        sorted_shapes = sorted(slide.shapes, key=lambda shape: (shape.top, shape.left))
        self.logger.info(f"{file_path_spaces} - Found {len(sorted_shapes)} shapes")
        
        md_content = self.convert_shapes_to_markdown(md_content, sorted_shapes, page_number, images_folder, file_path, file_path_spaces)
        
        return md_content
    
    def parse(self, file_path: Path, file_path_spaces: str) -> List[dict]:
        prs = Presentation(str(file_path))
        documents = []
        
        with tempfile.TemporaryDirectory(prefix="ppt_img_render_") as tmp_img_dir:
            images_folder = Path(tmp_img_dir)
            try:
                self.logger.info(f"{file_path_spaces} - Extracting content from PowerPoint... ")
                pages = len(prs.slides)
                for i, slide in enumerate(prs.slides):
                    self.logger.info(f"{file_path_spaces} - **Page {i+1}/{pages}**...")
                    
                    try:
                        page_markdown = self.convert_slide_to_markdown(slide=slide, page_number=i, images_folder=images_folder, file_path=file_path, file_path_spaces=file_path_spaces)
                    except Exception as e:
                        self.logger.error(f"{file_path_spaces} - X Error on page {i+1}: {e}")
                        page_markdown = ""
                    
                    metadata = {"file_path": file_path_spaces, "page": i+1, "file_hash": compute_file_hash(file_path)}
                    metadata.update(self._load_sidecar_metadata(file_path))
                    documents.append({"markdown": page_markdown, "metadata": metadata})
                
                self.logger.success(f"✓ Converted {file_path_spaces}")
                return documents
            except Exception as e:
                self.logger.error(f"Failed to process {file_path_spaces}: {e}")
                return []
