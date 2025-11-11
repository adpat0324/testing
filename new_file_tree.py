# file_tree.py
from typing import Dict, List, Set, Optional
import streamlit as st


class FileNode:
    """Represents a node in the file tree (folder or file)."""

    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path  # Full file_path for selection
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        """Add or get a child node."""
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


class FileTreeBuilder:
    """Build a hierarchical tree structure from file metadata."""

    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        """
        Build a tree structure from file metadata.

        Args:
            file_metadata: Dict mapping file_path -> metadata dict with SharePoint info

        Returns:
            Dict mapping root category name -> FileNode
        """
        roots = {}

        for file_path, metadata in file_metadata.items():
            # Determine the source and path structure
            site_path = metadata.get("sitePath")
            site_name = metadata.get("siteName")
            drive_name = metadata.get("driveName")
            parent_path = metadata.get("parentPath")

            if site_path and drive_name:
                # SharePoint file - build hierarchical structure
                root_name = f"SharePoint: {site_name if site_name else site_path}"

                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)

                current = roots[root_name]

                # Add drive
                current = current.add_child(f"{drive_name}")

                # Add parent path folders (if present)
                if parent_path:
                    # Clean up the parent path (e.g., "/Folder A/Child")
                    path_parts = parent_path.strip("/").split("/")
                    for part in path_parts:
                        if part:
                            current = current.add_child(f"{part}")

                # Add the file itself
                current.add_child(f"{file_path}", is_file=True, file_path=file_path)

            else:
                # Uploaded file or other source - flat structure
                root_name = "Other Files"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)

                roots[root_name].add_child(f"{file_path}", is_file=True, file_path=file_path)

        return roots


class FileTreeSelector:
    """Interactive file tree selector with checkboxes."""

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata
        self.tree = FileTreeBuilder.build_tree(file_metadata)
        self.selected_files: Set[str] = set()
        self.checkbox_states: Dict[str, bool] = {}

    # ---------------------------
    # NEW: search + scroll helper
    # ---------------------------
    def _node_matches(self, node: FileNode, query: str) -> bool:
        """Return True if this node or any descendant matches the query."""
        if not query:
            return True
        q = query.lower()
        if node.is_file and node.file_path:
            # Match on file_path or file name
            return q in node.file_path.lower() or q in node.name.lower()
        # Folder: match if folder name matches OR any child matches
        if q in node.name.lower():
            return True
        return any(self._node_matches(child, query) for child in node.children.values())

    # CSS to make expander content scrollable (fixed height)
    @staticmethod
    def _inject_scroll_css(scroll_height: int = 420):
        st.markdown(
            f"""
            <style>
            /* Limit the height of expander contents and make them scroll */
            .streamlit-expanderContent {{
                max-height: {scroll_height}px;
                overflow-y: auto;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _render_node(
        self,
        node: FileNode,
        level: int = 0,
        parent_key: str = "",
        container=None,
        query: str = "",
    ):
        if container is None:
            container = st

        # If this node (or any descendant) doesn't match the filter, skip rendering.
        if not self._node_matches(node, query):
            return

        if node.is_file:
            # File node - show checkbox with file name
            key = f"file_{parent_key}_{node.file_path}"
            checked = self.checkbox_states.get(key, node.file_path in self.selected_files)
            # Keep the default fixed; do not mutate session state for the same key after widget creation.
            if container.checkbox(node.name, value=checked, key=key):
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        # Folder node - show expander
        with container.expander(node.name, expanded=(level < 1)):
            # Add "Select All" checkbox for this folder
            key = f"folder_{parent_key}_{node.name}_select_all"
            folder_selected = container.checkbox("Select all", key=key, value=False)

            # Get all files under this folder (recursively)
            folder_files = self._get_all_files_in_node(node)
            if folder_selected:
                self.selected_files.update(folder_files)

            # Render children
            for child_name in sorted(node.children.keys()):
                child = node.children[child_name]
                self._render_node(
                    child,
                    level + 1,
                    f"{parent_key}_{node.name}",
                    container=container,
                    query=query,
                )

    def _get_all_files_in_node(self, node: FileNode) -> Set[str]:
        """Get all file paths under a node (recursively)."""
        files = set()
        if node.is_file and node.file_path:
            files.add(node.file_path)
        else:
            for child in node.children.values():
                files.update(self._get_all_files_in_node(child))
        return files

    def render(self, container=None, *, scroll_height: int = 420) -> List[str]:
        """
        Render the complete file tree and return selected files.

        Args:
            container: Streamlit container to render in (e.g., st.sidebar)
            scroll_height: fixed height for a scrollable tree area (px)

        Returns:
            List of selected file paths
        """
        if container is None:
            container = st

        # NEW: inject scrolling CSS once (affects expander contents)
        self._inject_scroll_css(scroll_height=scroll_height)

        # NEW: search box to filter files/folders
        query = container.text_input("Search documents…", value="", key="file_tree_search").strip()

        # Global select all
        if container.checkbox("Select All Files", key="select_all_global"):
            self.selected_files = set(self.file_metadata.keys())

        # Render tree (filtered by query) inside a container (expanders are scrollable via CSS)
        for root_name in sorted(self.tree.keys()):
            root = self.tree[root_name]
            self._render_node(root, level=0, parent_key="root", container=container, query=query)

        # Show count
        container.caption(f"**{len(self.selected_files)}** files selected")

        return list(self.selected_files)



