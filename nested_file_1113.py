# FileTreeSelector:
def _node_matches_search(self, node: FileNode, query: str) -> bool:
    """Return True if node or any descendant matches the search query."""
    if query in node.name.lower():
        return True
    return any(self._node_matches_search(child, query) for child in node.children.values())


if search_query and not self._node_matches_search(root, search_query):
    continue


# render_node:
if node.children:
    with container.expander(node.name, expanded=(level < 1)):
        key = f"folder_{parent_key}_{node.name}_select_all"
        folder_selected = st.checkbox(f"Select all in '{node.name}'", key=key, value=False)

        if folder_selected:
            # Select all files recursively
            folder_files = self._get_all_files_in_node(node)
            self.selected_files.update(folder_files)
        else:
            # Unselect all if previously selected
            folder_files = self._get_all_files_in_node(node)
            self.selected_files.difference_update(folder_files)

        # Render children
        for child_name in sorted(node.children.keys()):
            self._render_node(
                node.children[child_name],
                level + 1,
                f"{parent_key}_{node.name}",
                folder_selected,
                container
            )
