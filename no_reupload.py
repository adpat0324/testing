def _build_tasks(self, documents, streamlit_off=False):
    """
    Determine which documents need to be (re)indexed by comparing incoming file hashes
    to cached hashes or to hashes stored in the Risklab vector store.
    """

    # Local cache of seen hashes (not persisted across sessions)
    self._cached_hashes = getattr(self, "_cached_hashes", {})

    tasks = []

    for doc_name, docs in documents.items():
        incoming_hash = docs[0].metadata.get("file_hash")
        existing_hash = self._cached_hashes.get(doc_name)

        # NEW document
        if existing_hash is None:
            self.logger.info(f"[NEW] {doc_name}", streamlit_off=streamlit_off)
            tasks.append((doc_name, docs, "new"))
            continue

        # MODIFIED document
        if existing_hash != incoming_hash:
            self.logger.info(f"[MODIFIED] {doc_name}", streamlit_off=streamlit_off)
            tasks.append((doc_name, docs, "modified"))
            continue

        # UNCHANGED
        self.logger.info(f"[UNCHANGED] {doc_name} — skipping", streamlit_off=streamlit_off)

    return tasks



def _prepare_nodes(self, task_tuple):
    """
    Chunk, embed, and store document nodes in Risklab VectorStores.
    Only runs for 'new' and 'modified' documents.
    """

    doc_name, docs, action = task_tuple

    # Skip unchanged
    if action not in ("new", "modified"):
        return (doc_name, None, "skipped")

    try:
        # ------------------------
        # 1. Chunk the document
        # ------------------------
        try:
            splitter = SemanticSplitter(chunk_size=2048, chunk_overlap=200)
            nodes = splitter.get_nodes_from_documents(docs)
        except Exception as e:
            self.logger.warning(
                f"SemanticSplitter failed ({e}). Falling back to SentenceSplitter.",
                streamlit_off=True,
            )
            splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
            nodes = splitter.get_nodes_from_documents(docs)

        # ------------------------
        # 2. Add metadata
        # ------------------------
        for node in nodes:
            node.metadata.update({
                "file_name": os.path.basename(doc_name),
                "file_path": doc_name,
                "file_hash": docs[0].metadata.get("file_hash"),
            })

        # ------------------------
        # 3. Embed + store text nodes
        # ------------------------
        embedded_nodes = Settings.embed_model(nodes)
        self.vector_store.add(embedded_nodes)

        # ------------------------
        # 4. Generate + embed summary
        # ------------------------
        summary_text = self.generate_document_summary(nodes, doc_name)

        summary_doc = LlamaIndexDocument(
            text=summary_text,
            metadata={
                "file_name": os.path.basename(doc_name),
                "file_path": doc_name,
                "file_hash": docs[0].metadata.get("file_hash"),
                "_node_type": "Document",
            },
        )

        summary_nodes = Settings.embed_model([summary_doc])
        self.summary_store.add(summary_nodes)

        # ------------------------
        # 5. Update in-memory hash cache
        # ------------------------
        self._cached_hashes[doc_name] = docs[0].metadata.get("file_hash")

        return (doc_name, nodes, None)

    except Exception as e:
        return (doc_name, None, e)


def update_index(self,
                 kb_dir: Path,
                 parallel: bool = True,
                 max_workers: Optional[int] = None,
                 streamlit_off: bool = False):

    """
    Update Risklab VectorStore indexes with new or changed documents.
    """

    kb_docs = self._read_kb_docs(kb_dir)
    if not kb_docs:
        self.logger.info("No files found to index.", streamlit_off=streamlit_off)
        return 0

    documents = self._group_documents(kb_docs)
    tasks = self._build_tasks(documents, streamlit_off=streamlit_off)

    # NOTHING TO INDEX
    if not tasks:
        self.logger.info("No new or modified documents detected.", streamlit_off=streamlit_off)
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

    # -----------------------------
    # Collect results
    # -----------------------------
    success_count = 0
    fail_count = 0

    for doc_name, nodes, err in results:
        if err:
            fail_count += 1
            self.logger.error(f"Failed to index {doc_name}: {err}", streamlit_off=streamlit_off)
        else:
            success_count += 1
            self.logger.success(f"Indexed {doc_name} successfully.", streamlit_off=streamlit_off)

    self.logger.info(
        f"Index update complete. ({success_count} succeeded, {fail_count} failed.)",
        streamlit_off=True,
    )

    return success_count
