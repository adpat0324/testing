folder_selected = container.checkbox("Select all", key=folder_key)

previous_state = self._checkbox_states.get(folder_key, False)
if folder_selected != previous_state:
    # Record new state
    self._checkbox_states[folder_key] = folder_selected
    current_path = f"{parent_key}/{node.name}" if parent_key else node.name
    # Apply change to all descendants
    self._set_files_under_node(node, folder_selected, current_path)
    
    # If unselecting, recursively clear all deeper folder checkboxes in state
    if not folder_selected:
        self._clear_folder_checkboxes_recursive(node, current_path)


def _clear_folder_checkboxes_recursive(self, node: FileNode, current_path: str) -> None:
    """Recursively clear all folder checkbox states under a node."""
    for child in node.children.values():
        if not child.is_file:
            child_key = self._folder_checkbox_key(current_path, child.name)
            st.session_state[child_key] = False
            self._checkbox_states[child_key] = False
            # Recursively clear checkboxes in child folders
            child_path = f"{current_path}/{child.name}"
            self._clear_folder_checkboxes_recursive(child, child_path)
