def _read_kb_docs(self, kb_dir: Path) -> List[LlamaIndexDocument]:
    if not any(kb_dir.iterdir()):
        self.logger.info("No files to index.")
        return []

    self.logger.info("Reading documents in knowledge base.", streamlit_off=True)

    def file_extractor(file_path: str) -> List[LlamaIndexDocument]:
        docs = PickleReader().load_data(Path(file_path))
        file_hash = compute_file_hash(file_path)

        for d in docs:
            d.metadata["file_path"] = file_path
            d.metadata["file_name"] = os.path.basename(file_path)
            d.metadata["file_hash"] = file_hash

        return docs

    return SimpleDirectoryReader(
        input_dir=str(kb_dir),
        recursive=False,
        file_extractor={"*.pkl": file_extractor}
    ).load_data()


def _prepare_nodes(self, task_tuple):
    doc_name, docs, action, streamlit_off = task_tuple

    try:
        # All docs in this group have same metadata
        base_meta = docs[0].metadata
        file_path = base_meta["file_path"]
        file_name = base_meta["file_name"]
        file_hash = base_meta["file_hash"]

        # Generate nodes
        splitter = SentenceSplitter(chunk_size=2048, chunk_overlap=200)
        nodes = splitter.get_nodes_from_documents(docs)

        # Attach metadata
        for node in nodes:
            node.metadata.update({
                "file_name": file_name,
                "file_path": file_path,
                "file_hash": file_hash
            })

        # Add vector embeddings
        embedded_nodes = Settings.embed_model(nodes)
        self.vector_store.add(embedded_nodes)

        # Generate summary
        summary_text = self._generate_document_summary(nodes, file_name)

        summary_doc = LlamaIndexDocument(
            text=summary_text,
            metadata={
                "file_name": file_name,
                "file_path": file_path,
                "file_hash": file_hash  # ✅ Reuse correct hash
            }
        )

        embedded_summary = Settings.embed_model([summary_doc])
        self.summary_store.add(embedded_summary)

        return (file_name, nodes, None)

    except Exception as e:
        return (doc_name, None, str(e))
