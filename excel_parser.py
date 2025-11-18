import pandas as pd
from openpyxl import load_workbook
from pathlib import Path
from typing import List, Dict

class ExcelParser(BaseParser):
    def __init__(self) -> None:
        super().__init__(name="EXCEL_PARSER")

    def parse(self, file_path: Path, file_path_spaces: str) -> List[Dict]:
        try:
            wb = load_workbook(filename=file_path, data_only=True)
            parsed_documents = []

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                data = sheet.values
                df = pd.DataFrame(data)

                # Remove empty rows & columns
                df = df.dropna(how="all").dropna(axis=1, how="all")
                if df.empty:
                    continue  # Skip empty sheets

                df.columns = df.iloc[0] if df.shape[0] > 1 else df.columns
                df = df[1:] if df.shape[0] > 1 else df  # Remove duplicate header row

                # Convert to markdown
                markdown_table = df.to_markdown(index=False)

                # Chunking for RAG retrieval
                chunks = self._chunk_dataframe(df, max_rows=30)

                # Metadata
                metadata = {
                    "file_path": str(file_path),
                    "file_path_spaces": file_path_spaces,
                    "sheet_name": sheet_name,
                    "file_hash": compute_file_hash(file_path),
                    "columns": df.columns.tolist(),
                    "num_rows": len(df),
                }
                metadata.update(self._load_sidecar_metadata(file_path))

                # Store markdown + JSON
                for chunk in chunks:
                    parsed_documents.append({
                        "content": {
                            "markdown": chunk,
                            "json": df.to_json(orient="records")
                        },
                        "metadata": metadata
                    })

            self.logger.success(f"✓ Parsed {file_path_spaces} successfully")
            return parsed_documents

        except Exception as e:
            self.logger.error(f"⚠ Failed to parse {file_path_spaces}: {e}")
            return []

    # ----------------------------------
    # RAG-Ready Table Chunking
    # ----------------------------------
    @staticmethod
    def _chunk_dataframe(df: pd.DataFrame, max_rows: int = 30) -> List[str]:
        chunks = []
        for start in range(0, len(df), max_rows):
            chunk = df.iloc[start:start + max_rows]
            chunks.append(chunk.to_markdown(index=False))
        return chunks
