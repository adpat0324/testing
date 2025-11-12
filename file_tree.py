from typing import Dict, List, Optional, Set
import streamlit as st


class FileNode:
    """Represents either a folder or file in the tree."""
    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        """Add or retrieve a child node."""
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


class FileTreeSelector:
    """Renders a hierarchical file tree with working search, scroll, and select-all."""

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata or {}
        self.tree = self._build_tree(file_metadata)
        self.selected_files: Set[str] = st.session_state.get("fts_selected_files", set())

    # --------------------------------------------------------------------------
    def _build_tree(self, file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        roots: Dict[str, FileNode] = {}

        for file_path in file_metadata.keys():
            parts = [p for p in file_path.strip("/").split("/") if p]
            if not parts:
                continue

            current = roots.setdefault(parts[0], FileNode(parts[0]))
            for part in parts[1:-1]:
                current = current.add_child(part)
            # last part = file
            current.add_child(parts[-1], is_file=True, file_path=file_path)

        return roots

    # --------------------------------------------------------------------------
    def _filter_tree(self, node: FileNode, query: str) -> Optional[FileNode]:
        """Return a filtered copy of node (folders kept if they or descendants match)."""
        if not query:
            return node

        q = query.lower()
        match_self = q in node.name.lower()
        filtered_children = {
            k: v_filtered
            for k, v in node.children.items()
            if (v_filtered := self._filter_tree(v, query))
        }

        if match_self or filtered_children:
            new_node = FileNode(node.name, node.is_file, node.file_path)
            new_node.children = filtered_children
            return new_node
        return None

    def _get_all_files(self, node: FileNode) -> Set[str]:
        """Recursively collect all file paths in this node."""
        files = set()
        if node.is_file and node.file_path:
            files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files(child))
        return files

    # --------------------------------------------------------------------------
    def _render_node(self, node: FileNode, level: int = 0):
        """Render node (folder or file) recursively."""
        indent = " " * level  # em-space for indentation

        if node.is_file:
            # ✅ FILES = simple checkbox, no expander
            checked = node.file_path in self.selected_files
            if st.checkbox(f"{indent}📄 {node.name}", key=node.file_path, value=checked):
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        # ✅ FOLDERS = expander with “Select all” inside
        with st.expander(f"{indent}📁 {node.name}", expanded=False):
            folder_files = self._get_all_files(node)
            folder_selected = all(f in self.selected_files for f in folder_files)

            def toggle_folder():
                if st.session_state.get(f"{node.name}_select_all", False):
                    self.selected_files.update(folder_files)
                else:
                    self.selected_files.difference_update(folder_files)

            st.checkbox(
                "Select all in this folder",
                key=f"{node.name}_select_all",
                value=folder_selected,
                on_change=toggle_folder,
            )

            for child in sorted(node.children.values(), key=lambda n: (not n.is_file, n.name.lower())):
                self._render_node(child, level + 1)

    # --------------------------------------------------------------------------
    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        if container is None:
            container = st

        search_query = container.text_input("🔍 Search files and folders", "").strip()

        container.markdown(
            """
            <style>
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"] {
                max-height: 450px;
                overflow-y: auto;
                padding-right: 0.5rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Global select all
        all_files = {fp for root in self.tree.values() for fp in self._get_all_files(root)}
        all_selected = all_files and self.selected_files.issuperset(all_files)

        def toggle_global():
            if st.session_state.get("fts_select_all", False):
                self.selected_files.update(all_files)
            else:
                self.selected_files.clear()

        container.checkbox(
            "Select All Files",
            key="fts_select_all",
            value=all_selected,
            on_change=toggle_global,
        )

        for root_name, root_node in sorted(self.tree.items()):
            filtered = self._filter_tree(root_node, search_query)
            if filtered:
                self._render_node(filtered)

        container.caption(f"**{len(self.selected_files)}** files selected")
        st.session_state["fts_selected_files"] = self.selected_files
        return list(self.selected_files)
