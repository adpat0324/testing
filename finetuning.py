from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.core.schema import MetadataFilter, MetadataFilters

# ---------------------------------------------------------------------
# 1️⃣ Fetch file names directly from Risklab VectorStore
# ---------------------------------------------------------------------
def get_file_names(self) -> Dict[str, str]:
    """Fetch unique file names currently stored in the Risklab VectorStore."""
    try:
        # Query the vector store for all stored nodes
        query = VectorStoreQuery(similarity_top_k=1000)
        results = self.vector_store.query(query)

        if not results or not results.nodes:
            self.logger.info("📂 No files currently indexed in Risklab VectorStore.")
            return {}

        file_names = {}
        for node in results.nodes:
            meta = node.metadata or {}
            fname = meta.get("file_name")
            fpath = meta.get("file_path")
            if fname and fpath:
                file_names[fpath] = fname

        # Deduplicate and sort for display in Streamlit
        file_names = dict(sorted(file_names.items()))
        self.logger.info(f"📚 Retrieved {len(file_names)} indexed files from Risklab store.")
        return file_names

    except Exception as e:
        self.logger.error(f"⚠️ Failed to fetch file names from Risklab store: {e}")
        return {}



# ---------------------------------------------------------------------
# 2️⃣ Get a file hash from Risklab store (used by _build_tasks dedup logic)
# ---------------------------------------------------------------------
def _get_file_hash_from_store(self, doc_name: str) -> Optional[str]:
    """Retrieve the stored file hash for a document by its file_path."""
    try:
        filters = MetadataFilters(filters=[MetadataFilter(key="file_path", value=doc_name)])
        query = VectorStoreQuery(filters=filters, similarity_top_k=1)
        result = self.vector_store.query(query)
        if result and result.nodes:
            return result.nodes[0].metadata.get("file_hash")
    except Exception as e:
        self.logger.warning(f"⚠️ Could not retrieve file hash for {doc_name}: {e}")
    return None



# ---------------------------------------------------------------------
# 3️⃣ Update index to store or overwrite Risklab VectorStore entries
# ---------------------------------------------------------------------
def update_index(
    self,
    kb_dir: Path,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    streamlit_off: bool = False,
):
    """
    Update Risklab VectorStore indexes with new or changed documents.
    Compatible with original Streamlit indexing workflow.
    """
    kb_docs = self._read_kb_docs(kb_dir)
    if not kb_docs:
        self.logger.info("📂 No files found to index.", streamlit_off=streamlit_off)
        return 0

    documents = self._group_documents(kb_docs)
    tasks = self._build_tasks(documents, streamlit_off=streamlit_off)

    if not tasks:
        self.logger.info("✨ No new or modified documents detected.", streamlit_off=streamlit_off)
        return 0

    results = []
    if parallel:
        max_workers = max_workers or min(8, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._prepare_nodes, t) for t in tasks]
            for f in as_completed(futures):
                results.append(f.result())
    else:
        for t in tasks:
            results.append(self._prepare_nodes(t))

    success_count, fail_count = 0, 0
    for doc_name, nodes, err in results:
        if err:
            fail_count += 1
            self.logger.error(f"❌ Failed to index '{doc_name}': {err}", streamlit_off=streamlit_off)
        else:
            success_count += 1
            self.logger.success(f"✅ Indexed '{doc_name}' successfully.", streamlit_off=streamlit_off)

    self.logger.info(
        f"📊 Index update complete. {success_count} succeeded, {fail_count} failed.",
        streamlit_off=streamlit_off,
    )

    # ✅ Return number of successfully indexed documents to Streamlit
    return success_count
