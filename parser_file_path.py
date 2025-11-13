from dataclasses import asdict

def _extract_metadata(self, f) -> dict:
    """Extract metadata for a parsed file, including SharePoint fields if available."""
    meta = {"file_name": getattr(f, "name", "")}

    # If it's a SharePoint DownloadedFile, merge its metadata
    if hasattr(f, "metadata"):
        try:
            sp_meta = asdict(f.metadata)
            meta.update({
                "sitePath": sp_meta.get("sitePath", ""),
                "driveName": sp_meta.get("driveName", ""),
                "parentPath": sp_meta.get("parentPath", ""),
                "webUrl": sp_meta.get("webUrl", ""),
                "downloadUrl": sp_meta.get("downloadUrl", ""),
            })
        except Exception as e:
            self.logger.warning(f"Failed to extract SharePoint metadata for {f}: {e}")

    return meta
