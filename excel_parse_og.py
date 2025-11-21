class ExcelParser(BaseParser):
    def __init__(self) -> None:
        super().__init__(name="EXCEL_PARSER")

    def parse(self, file_path: Path, file_path_spaces: str) -> List[dict]:
        try:
            md_converter = MarkitDown(enable_plugins=True)
            result = md_converter.convert(str(file_path))
            md_content = result.text_content

            matches = re.split(r'(?m)^##\s*(.+):$', md_content)
            documents = []
            for i in range(1, len(matches), 2):
                page_name = matches[i].strip()
                page_content = matches[i + 1].strip() if i + 1 < len(matches) else ""
                
                metadata = {
                    "file_path": file_path,
                    "file_path_spaces": file_path_spaces,
                    "page": page_name,
                    "file_hash": compute_file_hash(file_path)
                }
                metadata.update(self._load_sidecar_metadata(file_path))
                
                documents.append({
                    "markdown": page_content,
                    "metadata": metadata
                })

            self.logger.success(f"✓ Converted {file_path_spaces}")
            return documents

        except Exception as e:
            self.logger.error(f"✗ Failed to convert {file_path_spaces}: {e}")
            return []
