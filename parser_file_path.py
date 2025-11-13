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

# Enrich metadata with SharePoint info if available
enriched_docs = []
for item in documents:
    meta = item.get("metadata", {}).copy()

    # If SharePoint metadata exists, merge it
    if "file" in item and hasattr(item["file"], "metadata"):
        try:
            sp_meta = asdict(item["file"].metadata)
            meta.update({
                "sitePath": sp_meta.get("sitePath", ""),
                "driveName": sp_meta.get("driveName", ""),
                "parentPath": sp_meta.get("parentPath", ""),
                "webUrl": sp_meta.get("webUrl", ""),
                "downloadUrl": sp_meta.get("downloadUrl", ""),
            })
        except Exception as e:
            self.logger.warning(f"Failed to enrich metadata for {item.get('file')}: {e}")

    doc = LlamaIndexDocument(text=item["markdown"], metadata=meta)
    enriched_docs.append(doc)

llama_documents = enriched_docs
