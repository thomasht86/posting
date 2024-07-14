# Sample textual app that renders markdown widget with url link
from textual.widgets import Markdown
from textual.app import App, ComposeResult

MARKDOWN = """
# This is an h1

Rich can do a pretty *decent* job of rendering markdown.

1. This is a list item
2. This is another list item

[Google](https://www.google.com)
"""

class HyperlinkApp(App):

    def compose(self) -> ComposeResult:
        yield Markdown(MARKDOWN)

# if __name__ == "__main__":
#     app = HyperlinkApp()
#     app.run()

from rich.console import Console
from rich.markdown import Markdown

console = Console()
md = Markdown(MARKDOWN)
console.print(md)