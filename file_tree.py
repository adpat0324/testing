from typing import Dict, List, Optional, Set
import streamlit as st


class FileNode:
    """Represents a node in the file tree (folder or file)."""
    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        """Add or get a child node."""
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


class FileTreeSelector:
    """Interactive hierarchical file selector with search, scroll, and working select-all."""

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata or {}
        self.tree: Dict[str, FileNode] = self._build_tree(file_metadata)
        self.selected_files: Set[str] = st.session_state.get("fts_selected_files", set())

    # --------------------------------------------------------------------------
    # Build tree
    def _build_tree(self, file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        roots: Dict[str, FileNode] = {}

        for file_path, metadata in file_metadata.items():
            parts = [p for p in file_path.strip("/").split("/") if p]
            if not parts:
                continue

            root_name = parts[0]
            if root_name not in roots:
                roots[root_name] = FileNode(root_name)

            current = roots[root_name]
            for part in parts[1:-1]:
                current = current.add_child(part)
            current.add_child(parts[-1], is_file=True, file_path=file_path)

        return roots

    # --------------------------------------------------------------------------
    def _filter_tree(self, node: FileNode, query: str) -> Optional[FileNode]:
        """Return filtered copy of node that matches query or has matching descendants."""
        if not query:
            return node

        q = query.lower()
        match_self = q in node.name.lower()
        filtered_children = {}

        for child_name, child in node.children.items():
            filtered_child = self._filter_tree(child, query)
            if filtered_child:
                filtered_children[child_name] = filtered_child

        if match_self or filtered_children:
            new_node = FileNode(node.name, node.is_file, node.file_path)
            new_node.children = filtered_children
            return new_node
        return None

    def _get_all_files(self, node: FileNode) -> Set[str]:
        files = set()
        if node.is_file and node.file_path:
            files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files(child))
        return files

    # --------------------------------------------------------------------------
    def _render_node(self, node: FileNode, level: int = 0):
        """Render a folder and its contents recursively."""
        indent = " " * level  # em-space

        if node.is_file:
            checked = node.file_path in self.selected_files
            if st.checkbox(f"{indent}📄 {node.name}", value=checked, key=node.file_path):
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        # Folder: render as expander
        folder_key = f"exp_{node.name}_{level}"
        with st.expander(f"{indent}📁 {node.name}", expanded=False):
            folder_files = self._get_all_files(node)
            folder_selected = all(f in self.selected_files for f in folder_files)

            def toggle_folder():
                if st.session_state.get(f"{folder_key}_select_all", False):
                    self.selected_files.update(folder_files)
                else:
                    self.selected_files.difference_update(folder_files)

            st.checkbox(
                "Select all in this folder",
                key=f"{folder_key}_select_all",
                value=folder_selected,
                on_change=toggle_folder,
            )

            for child in sorted(node.children.values(), key=lambda n: (not n.is_file, n.name.lower())):
                self._render_node(child, level + 1)

    # --------------------------------------------------------------------------
    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        if container is None:
            container = st

        # Search
        search_query = container.text_input("🔍 Search files and folders", "").strip()

        # Scrollable styling
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
        all_files = set()
        for root in self.tree.values():
            all_files.update(self._get_all_files(root))
        all_selected = len(all_files) > 0 and self.selected_files.issuperset(all_files)

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

        # Render tree (filtered)
        for root_name, root_node in sorted(self.tree.items()):
            filtered = self._filter_tree(root_node, search_query)
            if filtered:
                self._render_node(filtered)

        container.caption(f"**{len(self.selected_files)}** files selected")
        st.session_state["fts_selected_files"] = self.selected_files
        return list(self.selected_files)
