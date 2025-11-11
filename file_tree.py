class FileTreeSelector:
    """
    Flat, searchable, scrollable file selector with a real Select All toggle.
    Updated to avoid modifying Streamlit widget keys after creation.
    """

    def __init__(self, file_metadata: Dict[str, Dict], *, state_key: str = "fts"):
        self.file_metadata = file_metadata or {}
        self.state_key = state_key

        # Build stable option list
        self.options: List[str] = sorted(
            self.file_metadata.keys(),
            key=lambda p: (self.file_metadata.get(p, {}).get("file_name") or p).lower()
        )

        # Labels for display
        self.labels = {
            p: self.file_metadata.get(p, {}).get("file_name") or p
            for p in self.options
        }

        # Session keys — note: _all_key is ONLY controlled by checkbox callback
        self._sel_key = f"{self.state_key}_selected"        # list of selected paths
        self._all_key = f"{self.state_key}_select_all"      # widget checkbox
        self._ms_key  = f"{self.state_key}_multiselect"     # widget list

        # We use a derived state, NOT the widget key, for internal sync logic
        self._computed_all = f"{self.state_key}_computed_all"

        # Initialize session state safely
        ss = st.session_state
        ss.setdefault(self._sel_key, [])
        ss.setdefault(self._all_key, False)      # widget controls this
        ss.setdefault(self._ms_key, [])
        ss.setdefault(self._computed_all, False)

    # ----------------------------------------------------------------------
    # ❗ No longer touches st.session_state[self._all_key] directly
    # Only computes whether all should be checked
    # ----------------------------------------------------------------------
    def _compute_select_all(self):
        ss = st.session_state
        all_selected = (
            len(ss[self._sel_key]) == len(self.options) and len(self.options) > 0
        )
        ss[self._computed_all] = all_selected  # safe, not a widget key

    # ----------------------------------------------------------------------
    # ✅ Only legal place to modify st.session_state[self._all_key] or selection
    # ----------------------------------------------------------------------
    def _on_select_all_toggle(self):
        ss = st.session_state
        if ss[self._all_key]:  # user checked "Select All"
            ss[self._sel_key] = list(self.options)
            ss[self._ms_key]  = list(self.options)
        else:                  # user unchecked it
            ss[self._sel_key] = []
            ss[self._ms_key]  = []

    # ----------------------------------------------------------------------
    def render(self, container=None) -> List[str]:
        if container is None:
            container = st

        ss = st.session_state

        # Before rendering widgets, compute whether all should be selected.
        # This does NOT touch the widget key.
        self._compute_select_all()

        # ------------------------------------------------------
        # ✅ SELECT ALL CHECKBOX (widget key must NOT be overwritten later)
        # ------------------------------------------------------
        container.checkbox(
            "Select All",
            key=self._all_key,
            value=ss[self._all_key],  # widget owns this
            on_change=self._on_select_all_toggle,
            help="Toggle to select/unselect all files."
        )

        # ------------------------------------------------------
        # ✅ MULTISELECT (searchable + scrollable)
        # ------------------------------------------------------
        container.markdown("""
            <style>
            div[data-baseweb="select"] > div { max-height: 380px; overflow-y: auto; }
            </style>
        """, unsafe_allow_html=True)

        selected = container.multiselect(
            "Pick Documents",
            options=self.options,
            default=ss[self._sel_key],
            key=self._ms_key,
            format_func=lambda p: self.labels.get(p, p),
            placeholder="Search files…"
        )

        # Update selected state only (legal)
        ss[self._sel_key] = selected

        # Recompute "computed all" (indirect state)
        self._compute_select_all()

        # Now update the widget state if it is OUT OF SYNC
        # Must be done BEFORE the next render cycle triggers the widget
        if ss[self._all_key] != ss[self._computed_all]:
            ss[self._all_key] = ss[self._computed_all]

        # Footer count
        container.caption(f"**{len(selected)} files selected**")

        return selected




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






# app/config/file_tree.py

from typing import Dict, List, Optional
import streamlit as st

class FileTreeSelector:
    """
    Flat, searchable, scrollable file selector with a true Select All toggle.
    API-compatible with your previous selector:
      selected = FileTreeSelector(file_metadata).render(container) -> List[str]
    """

    def __init__(self, file_metadata: Dict[str, Dict], *, state_key: str = "fts"):
        self.file_metadata = file_metadata or {}
        self.state_key = state_key

        # Build stable option list + labels
        # options are file_paths; labels display file names (fallback to path)
        self.options: List[str] = sorted(
            self.file_metadata.keys(),
            key=lambda p: (self.file_metadata.get(p, {}).get("file_name") or p).lower()
        )
        self.labels = {
            p: self.file_metadata.get(p, {}).get("file_name") or p for p in self.options
        }

        # Session keys
        self._sel_key = f"{self.state_key}_selected"
        self._all_key = f"{self.state_key}_select_all"
        self._ms_key  = f"{self.state_key}_multiselect"

        # Init session state defaults once
        if self._sel_key not in st.session_state:
            st.session_state[self._sel_key] = []
        if self._all_key not in st.session_state:
            st.session_state[self._all_key] = False
        if self._ms_key not in st.session_state:
            st.session_state[self._ms_key] = []

    def _sync_select_all_checkbox(self):
        """Keep the 'Select All' checkbox in sync with current selection size."""
        all_selected = len(st.session_state[self._sel_key]) == len(self.options) and len(self.options) > 0
        st.session_state[self._all_key] = all_selected

    def _on_select_all_toggle(self):
        """Callback when 'Select All' is toggled: set selection accordingly."""
        if st.session_state[self._all_key]:
            st.session_state[self._sel_key] = list(self.options)
            st.session_state[self._ms_key]  = list(self.options)
        else:
            st.session_state[self._sel_key] = []
            st.session_state[self._ms_key]  = []

    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        """
        Render the selector and return the list of selected file paths.
        """
        if container is None:
            container = st

        # --- Controls header
        with container.container():
            # A slim header row with Select All (kept in sync)
            self._sync_select_all_checkbox()
            container.checkbox(
                "Select All",
                key=self._all_key,
                value=st.session_state[self._all_key],
                on_change=self._on_select_all_toggle,
                help="Toggle to select/unselect all files in the list."
            )

        # --- Searchable, scrollable multi-select
        # st.multiselect is searchable and scrollable by default.
        # We keep it in a container with a fixed max height via simple CSS.
        with container.container():
            # Optional: cap height of the widget’s area
            container.markdown(
                """
                <style>
                div[data-baseweb="select"] > div { max-height: 380px; overflow-y: auto; }
                </style>
                """,
                unsafe_allow_html=True,
            )

            selected = container.multiselect(
                "Pick Documents",
                options=self.options,
                default=st.session_state[self._sel_key],
                key=self._ms_key,
                format_func=lambda p: self.labels.get(p, p),
                placeholder="Search files…"
            )

        # Persist & sync state
        st.session_state[self._sel_key] = selected
        self._sync_select_all_checkbox()

        # Footer count
        container.caption(f"**{len(selected)}** files selected")

        return selected



