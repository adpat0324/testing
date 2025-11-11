import streamlit as st
from typing import Dict, List, Optional

class FileTreeSelector:
    """
    Flat searchable file selector with Select All.
    Safe with Streamlit session state (never rewrites widget keys after creation).
    """

    def __init__(self, file_metadata: Dict[str, Dict], *, state_key: str = "fts"):
        self.file_metadata = file_metadata or {}
        self.state_key = state_key

        # Flatten file paths
        self.options: List[str] = sorted(file_metadata.keys(), key=str.lower)

        # Internal session-state keys (NOT used by widgets)
        self._internal_selected = f"{state_key}_internal_selected"
        self._internal_search   = f"{state_key}_internal_search"

        # Widget keys (never modified after creation)
        self._w_search = f"{state_key}_search"
        self._w_selectall = f"{state_key}_select_all"
        self._w_multiselect = f"{state_key}_multiselect"

        # Initialize internal values once
        st.session_state.setdefault(self._internal_selected, [])
        st.session_state.setdefault(self._internal_search, "")

    # ---------------------------------------------------------
    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None,
               height: int = 350) -> List[str]:

        if container is None:
            container = st

        # ----- Sync widget defaults only BEFORE widget creation -----
        default_search = st.session_state[self._internal_search]
        default_selected = st.session_state[self._internal_selected].copy()

        # Search bar
        search_val = container.text_input(
            "Search documents",
            key=self._w_search,
            value=default_search,
            placeholder="Search…"
        )
        st.session_state[self._internal_search] = search_val
        search_lower = search_val.lower()

        # Filter options
        filtered = [
            p for p in self.options
            if search_lower in p.lower()
        ]

        # Default select-all based on internal selection
        default_all = len(filtered) > 0 and set(default_selected) >= set(filtered)

        # Select All
        select_all_checked = container.checkbox(
            "Select All",
            value=default_all,
            key=self._w_selectall
        )

        # Scrollable CSS
        container.markdown(
            f"""
            <style>
            .fts-scroll {{
                max-height: {height}px;
                border: 1px solid #ccc;
                padding: 6px;
                border-radius: 6px;
                overflow-y: auto;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

        container.markdown('<div class="fts-scroll">', unsafe_allow_html=True)

        # Determine default selection for widget
        if select_all_checked:
            default_selected = filtered.copy()

        # Multi-select widget
        selected = container.multiselect(
            label="",
            key=self._w_multiselect,
            options=filtered,
            default=default_selected,
        )

        container.markdown("</div>", unsafe_allow_html=True)

        # ----- Update internal state AFTER widget creation -----
        st.session_state[self._internal_selected] = selected

        # Footer
        container.caption(f"**{len(selected)} files selected**")

        return selected
