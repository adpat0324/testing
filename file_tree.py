"""
file_tree.py

Hierarchical file tree builder and Streamlit selector for RAG knowledge base files.
Supports nested folders, per-folder “Select All”, global “Select All”,
and recursive search that expands only matching branches.
"""

from typing import Dict, List, Set, Optional
import streamlit as st


# -----------------------------------------------------------------------------
# File Node
# -----------------------------------------------------------------------------
class FileNode:
    """Represents a node in the file tree (folder or file)."""

    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path  # Full path for file nodes
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        """Add a child node if not already present."""
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


# -----------------------------------------------------------------------------
# File Tree Builder
# -----------------------------------------------------------------------------
class FileTreeBuilder:
    """Builds a hierarchical file tree from file metadata."""

    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        """
        Build a tree from file metadata.

        Args:
            file_metadata: Mapping file_path -> metadata dict

        Returns:
            Dict mapping root category name -> FileNode
        """
        roots: Dict[str, FileNode] = {}

        for file_path, metadata in file_metadata.items():
            site_path = metadata.get("sitePath")
            site_name = metadata.get("siteName")
            drive_name = metadata.get("driveName")
            parent_path = metadata.get("parentPath")

            if site_path and drive_name:
                # Build SharePoint hierarchy
                root_name = f"SharePoint: {site_name}" if site_name else site_path
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)

                current = roots[root_name].add_child(drive_name)
                if parent_path:
                    for part in parent_path.strip("/").split("/"):
                        if part:
                            current = current.add_child(part)

                current.add_child(file_path, is_file=True, file_path=file_path)

            else:
                # Other / flat structure
                root_name = "Other Files"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)
                roots[root_name].add_child(file_path, is_file=True, file_path=file_path)

        return roots


# -----------------------------------------------------------------------------
# File Tree Selector (Streamlit)
# -----------------------------------------------------------------------------
class FileTreeSelector:
    """Interactive file tree selector with search and multi-level checkboxes."""

    def __init__(self, file_metadata: List[Dict]):
        self.file_metadata = self._iter_items(file_metadata)
        self.tree = FileTreeBuilder.build_tree(self.file_metadata)
        self.selected_files: Set[str] = set()

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------
    @staticmethod
    def _iter_items(file_metadata: List[Dict]) -> Dict[str, Dict]:
        """Convert list of metadata dicts to path->metadata mapping."""
        out: Dict[str, Dict] = {}
        for md in file_metadata:
            if not isinstance(md, dict):
                continue
            fp = md.get("file_path")
            if fp:
                out[fp] = md
        return out

    def _get_all_files_in_node(self, node: FileNode) -> Set[str]:
        """Recursively collect all file paths under a node."""
        files = set()
        if node.file_path:
            files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files_in_node(child))
        return files

    def _node_matches_search(self, node: FileNode, query: str) -> bool:
        """True if node or any descendant name contains query."""
        q = query.lower()
        if q in node.name.lower():
            return True
        return any(self._node_matches_search(c, query) for c in node.children.values())

    def _matching_children(self, node: FileNode, query: str) -> List[FileNode]:
        """Return only children that match search (or have matching descendants)."""
        if not query:
            return list(node.children.values())
        return [c for c in node.children.values() if self._node_matches_search(c, query)]

    def _highlight(self, name: str, query: str) -> str:
        """Bold matching substring."""
        q = query.lower()
        i = name.lower().find(q)
        if i == -1:
            return name
        return f"{name[:i]}**{name[i:i+len(q)]}**{name[i+len(q):]}"

    # -------------------------------------------------------------------------
    # Recursive Renderer
    # -------------------------------------------------------------------------
    def _render_node(
        self,
        node: FileNode,
        level: int = 0,
        parent_key: str = "",
        parent_selected: bool = False,
        container=None,
        search_query: str = ""
    ) -> None:
        """Recursively render node (folder or file) with checkboxes."""
        if container is None:
            container = st

        # FILE NODE
        if node.file_path:
            key = f"file_{node.file_path}"
            default_checked = parent_selected or (node.file_path in self.selected_files)
            label = self._highlight(node.name, search_query) if search_query else node.name
            checked = container.checkbox(label, key=key, value=default_checked)
            if checked:
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        # FOLDER NODE
        children_to_render = self._matching_children(node, search_query)
        if search_query and not children_to_render and search_query not in node.name.lower():
            return

        exp_label = self._highlight(node.name, search_query) if search_query else node.name
        expanded = (level < 1) or bool(search_query)
        with container.expander(exp_label, expanded=expanded):
            # Select all in folder
            sel_key = f"folder_{parent_key}_{node.name}_select_all"
            prev_val = st.session_state.get(sel_key, False)
            folder_selected = container.checkbox(
                f"Select all in '{node.name}'",
                key=sel_key,
                value=prev_val
            )

            folder_files = self._get_all_files_in_node(node)
            if folder_selected and not prev_val:
                self.selected_files.update(folder_files)
            elif (not folder_selected) and prev_val:
                self.selected_files.difference_update(folder_files)

            st.session_state[sel_key] = folder_selected

            for child in sorted(children_to_render, key=lambda c: c.name.lower()):
                self._render_node(
                    child,
                    level + 1,
                    f"{parent_key}/{node.name}",
                    parent_selected=folder_selected or parent_selected,
                    container=container,
                    search_query=search_query,
                )

    # -------------------------------------------------------------------------
    # Main Renderer
    # -------------------------------------------------------------------------
    def render(self, container=None) -> List[str]:
        """Render the entire tree and return selected file paths."""
        if container is None:
            container = st

        # --- Search bar
        search_query = container.text_input("🔎 Search files", "").strip().lower()

        # --- Global select all
        all_files = set()
        for root in self.tree.values():
            all_files.update(self._get_all_files_in_node(root))

        global_key = "select_all_global"
        prev_global = st.session_state.get(global_key, False)
        now_global = container.checkbox("Select All Files", key=global_key, value=prev_global)

        if now_global and not prev_global:
            self.selected_files = set(all_files)
        elif (not now_global) and prev_global:
            self.selected_files.clear()

        st.session_state[global_key] = now_global

        # --- Render roots
        root_names = sorted(self.tree.keys(), key=lambda x: (x == "Other Files", x.lower()))
        for root_name in root_names:
            root = self.tree[root_name]
            if search_query and not self._node_matches_search(root, search_query):
                continue
            self._render_node(
                root,
                level=0,
                parent_key="root",
                parent_selected=now_global,
                container=container,
                search_query=search_query
            )

        # --- Footer
        container.caption(f"**{len(self.selected_files)}** files selected")
        return list(self.selected_files)
