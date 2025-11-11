class FileTreeBuilder:
    """Builds a flat file list from metadata (no hierarchy)."""

    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, "FileNode"]:
        """
        Returns a flat dictionary: { file_name: FileNode }
        """
        tree = {}
        for file_path, metadata in file_metadata.items():
            file_name = metadata.get("fileName") or metadata.get("file_name") or file_path
            tree[file_name] = FileNode(
                name=file_name,
                is_file=True,
                file_path=file_path
            )
        return tree


class FileTreeSelector:
    """Interactive flat file selector with checkboxes + search + scroll UI."""

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata
        self.tree = FileTreeBuilder.build_tree(file_metadata)

        self.selected_files: Set[str] = set()
        self.checkbox_states: Dict[str, bool] = {}

    def render(self, container=None) -> List[str]:
        if container is None:
            container = st

        st.subheader("📁 Select Knowledge Base Files")

        # -----------------------------
        # ✅ SEARCH BAR
        # -----------------------------
        search_term = container.text_input("Search files", value="", key="file_search").lower()

        # Filter files
        filtered_files = {
            name: node for name, node in self.tree.items()
            if search_term in name.lower()
        }

        # -----------------------------
        # ✅ SELECT ALL CHECKBOX
        # -----------------------------
        select_all = container.checkbox("Select All Files", key="select_all_files")

        if select_all:
            # Mark all checkbox states true
            for name, node in filtered_files.items():
                self.checkbox_states[node.file_path] = True
            self.selected_files = {node.file_path for node in filtered_files.values()}
        else:
            # User unchecked select-all → unselect all only if previously selected
            if len(self.selected_files) == len(filtered_files):
                self.selected_files = set()
                for node in filtered_files.values():
                    self.checkbox_states[node.file_path] = False

        # -----------------------------
        # ✅ SCROLLABLE CHECKBOX AREA
        # -----------------------------
        with container.container():
            container.write("")  # small visual padding

            # Create scroll box
            scroll_container = container.container()
            scroll_container.markdown(
                """
                <div style="height:300px; overflow-y:scroll; border:1px solid #DDD; padding:10px;">
                """,
                unsafe_allow_html=True
            )

            # Render checkboxes inside scroll box
            for file_name, node in sorted(filtered_files.items()):
                current_state = self.checkbox_states.get(node.file_path, False)
                new_state = container.checkbox(
                    file_name,
                    value=current_state,
                    key=f"chk_{node.file_path}"
                )

                self.checkbox_states[node.file_path] = new_state
                if new_state:
                    self.selected_files.add(node.file_path)
                else:
                    self.selected_files.discard(node.file_path)

            # Close scrollable div
            container.markdown("</div>", unsafe_allow_html=True)

        # Count
        container.caption(f"✅ **{len(self.selected_files)} files selected**")

        return list(self.selected_files)


