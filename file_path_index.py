site_path = docs[0].metadata.get("sitePath") or ""
drive_name = docs[0].metadata.get("driveName") or ""
parent_path = docs[0].metadata.get("parentPath") or ""

# fallback: infer from doc_file_path if metadata missing
if not any([site_path, drive_name, parent_path]):
    path_parts = doc_file_path.split("/")
    if len(path_parts) >= 3:
        site_path, drive_name, parent_path = (
            path_parts[0],
            path_parts[1],
            "/".join(path_parts[2:-1]),
        )
    elif len(path_parts) == 2:
        site_path, drive_name = path_parts

# Construct normalized full path
full_path = "/".join(p for p in [site_path, drive_name, parent_path, doc_file_path] if p).replace("//", "/").strip("/")

self.logger.info(
    f"Metadata for {doc_file_path}: site={site_path}, drive={drive_name}, parent={parent_path}"
)
