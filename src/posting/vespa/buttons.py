from textual.widgets import Button


class SearchButton(Button, can_focus=False):
    DEFAULT_CSS = """
    SearchButton { 
            height: 3;
            padding: 0;
            width: 20%;
            background: $primary;
            color: $text;
            border: none;
            text-style: none;
            &:hover {
                border: none;
                background: $primary-darken-1;
            }
        }
    """


class FilterButton(Button):
    DEFAULT_CSS = """
        FilterButton { 
            }
        """
