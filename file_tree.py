"""
file_tree.py

Hierarchical file tree builder and Streamlit selector for RAG knowledge base files.
Supports nested folders, per-folder “Select All”, global “Select All”,
and recursive search that expands only matching branches.
"""

from typing import Dict, List, Set, Optional
import streamlit as st


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

                current = roots[root_name]
                current = current.add_child(drive_name)
                if parent_path:
                    path_parts = parent_path.strip("/").split("/"):
                        for part in path_parts:
                            current = current.add_child(part)

                current.add_child(file_path, is_file=True, file_path=file_path)

            else:
                # Other / flat structure
                root_name = "Other Files"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)
                roots[root_name].add_child(file_path, is_file=True, file_path=file_path)

        return roots


class FileTreeSelector:
    """Interactive file tree selector with search and multi-level checkboxes."""

    def __init__(self, file_metadata: List[Dict]):
        self.file_metadata = self._iter_items(file_metadata)
        self.tree = FileTreeBuilder.build_tree(self.file_metadata)
        self.selected_files: Set[str] = set()
        self._checkbox_states: Dict[str, bool] = {}

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
        if node.is_file and node.file_path:
            files.add(node.file_path)
        else:
            for child in node.children.values():
                files.update(self._get_all_files_in_node(child))
        return files

    def _node_matches_search(self, node: FileNode, query: str) -> bool:
        """True if node or any descendant name contains query."""
        if q in node.name.lower():
            return True
        return any(self._node_matches_search(child, query) for child in node.children.values())

    # Recursive Renderer
    def _render_node(
        self,
        node: FileNode,
        level: int = 0,
        parent_key: str = "",
        parent_selected: bool = False,
        container=None) -> None:
        """Recursively render node (folder or file) with checkboxes."""
        if container is None:
            container = st

        # FILE NODE
        if node.file_path:
            key = f"file_{node.file_path}"
            checked = parent_selected or (node.file_path in self.selected_files if node.file_path else False)
            if container.checkbox(node.name, value=checked, key=key):
                if node.file_path:
                    self.selected_files.add(node.file_path)
            elif node.file_path and node.file_oath in self.selected_files and not parent_selected:
                self.selected_files.discard(node.file_path)
        else:
            if node.children:
                with container.expander(node.name, expanded={level<1)):
                    key = f"folder+{parent_key}_{node.name}_select_all"
                    folder_selected = st.checkbox("Select all", key=key, value=False)
                    if folder_selected:
                        folder_files = self._get_all_files_in_node(node)
                        self.selected_files.update(folder_files)
                    else:
                        folder_files = self._get_all_files_in_node(node)
                        self.selected_files.difference_update(folder_files)
                    for child_name in sorted(node.children.keys():
                        self._render_node(node.children[child_name], level+1, f"{parent_key}_{node.name}", folder_selected, container)
        
    # -------------------------------------------------------------------------
    # Main Renderer
    # -------------------------------------------------------------------------
    def render(self, container=None) -> List[str]:
        """Render the entire tree and return selected file paths."""
        if container is None:
            container = st

        # Search bar
        search_query = container.text_input("🔎 Search files", "").strip().lower()

        # Sort so 'Other Files' is last
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
                container=container)

        container.caption(f"**{len(self.selected_files)}** files selected")
        return list(self.selected_files)
