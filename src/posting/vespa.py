from textual.containers import Vertical
from textual.widgets import Label, Markdown, Button
from textual.app import ComposeResult, on
from textual.message import Message
from textual.widgets import Input, ContentSwitcher, DataTable
from textual.containers import VerticalScroll, Horizontal, Center, Grid
from textual import work
from textual.reactive import reactive, Reactive
from textual.screen import ModalScreen
from rich.text import Text
from pydantic.dataclasses import dataclass as pydantic_dataclass
from posting.widgets.vespa.buttons import SearchButton, FilterButton
from dataclasses import dataclass
import httpx
import os
import sys
import subprocess
import shlex
import select
from typing import List
import webbrowser


COLUMNS = (
    "Application",
    "Environment",
    "URL endpoint",
    "Document count",
    "Auth type",
    "Cert status",
    "Status",
)
ROWS = [
    (
        "colbert-ai",
        "dev",
        "https://b29dd9de.d95f671d.z.vespa-app.cloud/",
        1400,
        "mTLS",
        "Not Found",
        "No cert",
    ),
    (
        "semantic-search",
        "dev",
        "https://b29ddgde.d95f434d.z.vespa-app.cloud/",
        1000,
        "mTLS",
        "Not Found",
        "No cert",
    ),
    (
        "pdf-search",
        "prod",
        "https://b29dd9de.d95f67434.z.vespa-app.cloud/",
        2000,
        "token",
        "OK",
        "Ready",
    ),
]


class AddTokenScreen(ModalScreen):
    """Screen with a dialog to quit."""

    DEFAULT_CSS = """
    AddTokenScreen {
    align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 4;
        padding: 0 1;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }

    #label-token {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }

    #token {
        column-span: 2;
        width: 1fr;
    }

    Button {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Input token from vespa cloud", id="label-token"),
            Input(placeholder="Token", id="token"),
            Button("Add", variant="primary", id="add-token"),
            Button("Cancel", variant="error", id="cancel"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        elif event.button.id == "add-token":
            # TODO: Add token to the environment
            self.app.pop_screen()
        else:
            self.app.pop_screen()


class ApplicationTable(DataTable):
    DEFAULT_CSS = """
    ApplicationTable {
        margin: 1
    
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs, cursor_type="row", id="app_table")
        self.column_keys = self.add_columns(*COLUMNS)
        self.col_label_to_key = {
            col: key for key, col in zip(self.column_keys, COLUMNS)
        }
        # self.add_rows(ROWS)
        for row in ROWS:
            # Adding styled and justified `Text` objects instead of plain strings.
            styled_row = [
                Text(str(cell), style=self.get_style_for_cell(cell_no, cell))
                for cell_no, cell in enumerate(row)
            ]
            self.add_row(*styled_row)
        self.sort(self.col_label_to_key["Status"], key=lambda x: str(x).lower())

    def get_style_for_cell(self, cell_no: int, cell: str) -> str:
        if cell_no == 6:
            return "green" if cell == "Ready" else "yellow"
        return ""


class VespaPage(Vertical):
    """The Vespa page."""

    DEFAULT_CSS = """
    VespaPage {
        & #auth-row {
            height: 3;
        }

        & #button-row {
            content-align: center middle;
            margin: 1;

            & Button {
                margin: 1;
            }
        }

        & #auth_button {
            margin: 1;
            padding: 1;
        }

        & #tenant_input {
            width: 20%;
            margin: 1;
        }
    }
    """

    @dataclass
    class AuthenticatedMessage(Message):
        authenticated: bool = True

    class GenerateCertButton(Button):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = "Generate Cert"

    class GenerateCollectionButton(Button):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = "Generate Collection"

    class AddTokenButton(Button):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = "Add Token"

    class AddEnvButton(Button):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = "Add to environment"

    def compose(self) -> ComposeResult:
        self.border_title = "Vespa cloud applications"
        self.styles.border_title_align = "center"
        self.add_class("section")
        yield Label("Authenticate to Vespa cloud tenant:")
        with Horizontal(id="auth-row"):
            yield Input(placeholder="Vespa cloud tenant", id="tenant_input")
            yield Button("Authenticate", id="auth_button", variant="primary")
        yield Label("Applications:")
        yield ApplicationTable()
        with Horizontal(id="button-row"):
            yield self.GenerateCollectionButton(
                label="Generate collection", id="generate_button", variant="success"
            )
            yield self.GenerateCertButton(
                label="Generate Cert", id="cert_button", variant="success"
            )
            yield self.AddTokenButton(
                label="Add Token", id="token_button", variant="success"
            )
            yield self.AddEnvButton(
                label="Add to environment", id="env_button", variant="success"
            )
        # yield ApplicationTable()
        # yield Markdown("Output:", id="output")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "token_button":
            self.app.push_screen(AddTokenScreen())

    def _on_mount(self) -> None:
        table = self.query_one(DataTable)
        # table.add_columns(*ROWS[0])
        # table.add_rows(ROWS[1:])

    @on(Button.Pressed, "#auth_button")
    def run_vespa_auth_login(self, event):
        # Run the Vespa auth login command and capture the output
        # Open a new pseudo-terminal
        import pty

        master, slave = pty.openpty()

        # Start the subprocess with its input/output connected to the PTY
        p = subprocess.Popen(
            shlex.split("vespa auth login"),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            universal_newlines=True,
        )

        # Close the slave end in the parent process
        os.close(slave)
        finished = False
        try:
            while not finished:
                # Use select to wait for data to be available on the PTY
                rlist, _, _ = select.select([master], [], [], 1)

                for fd in rlist:
                    if fd == master:
                        # Read output from the master end of the PTY
                        output = os.read(master, 1024).decode("utf-8")
                        if output:
                            print(output, end="")
                            self.query_one("#output", Markdown).update(
                                markdown=f"Output: {output}"
                            )
                            sys.stdout.flush()
                        if "Success:" in output:
                            finished = True  # Exit the loop after success message
                            break

                        # Check for input only if running in a Jupyter Notebook
                        if "[Y/n]" in output:
                            user_input = "y\n"  # input() + "\n"
                            os.write(master, user_input.encode())
                            sys.stdout.flush()
                if finished:
                    break

        finally:
            # Ensure the master end of the PTY is closed
            os.close(master)
            # Ensure the subprocess is properly terminated
            p.terminate()
            p.wait()
        # Add the output to the Markdown widget
        msg = self.AuthenticatedMessage(authenticated=True)
        posted = self.post_message(msg)
        self.query_one("#output", Markdown).update(
            markdown=f"Output: {posted} Msg: {msg}"
        )


@dataclass
class ChatResponse(Message):
    response: str


@dataclass
class ResetChat(Message):
    pass


@dataclass
class ResetSearch(Message):
    pass


@pydantic_dataclass(config=dict(extra="allow"))
class SearchResult:
    number: int
    title: str
    base_uri: str
    path: str
    content: str
    relevance: float
    source: str

    def to_markdown(self) -> str:
        return f"### [[{self.number}] {self.title}]({self.base_uri}{self.path})\n{self.content}\n\n[Read more]({self.base_uri}{self.path})\n___"


@dataclass
class SearchResponse(Message):
    results: List[SearchResult]


# Not in use yet
class SearchResultWidget(Vertical):
    DEFAULT_CSS = """
    SearchResultWidget {
        border: solid $background-lighten-3;
        
        & Button {
            width: 80%;
        }
    }
    """

    def __init__(self, result: SearchResult, **kwargs):
        super().__init__(**kwargs)
        self.result = result

    def compose(self) -> ComposeResult:
        yield Markdown(self.result)
        yield Button("Read more", id="read-more")


class DocSearchView(Horizontal):
    """DocSearchView"""

    DEFAULT_CSS = """
    DocSearchView {
        height: auto;
        padding: 1;
        & SearchButton {
            dock: right;
            padding: 1;
        }

        & FilterButton {
            
            &.disabled {
            background: $background-lighten-3;
            color: $text-muted;
            }    
        }
        #search-input {
            width: 90%;
            height: auto;

        }
        #search-emoji {
            height: 3;
            padding: 0;
        }
        #chat-button {
            background: $primary;
            color: $text;
            .hover {
                background: $primary-darken-1;
            }
        }
        #consent {
            color: $text-muted;
            padding: 1;
        }
    }
    """

    FILTERS = {
        "docs": "+namespace:open-p",
        "cloud-docs": "+namespace:cloud-p",
        "sample-apps": "+namespace:vespaapps-p",
        "blog": "+namespace:blog-p",
        "pyvespa": "+namespace:pyvespa-p",
    }
    # Initialize the button states to False
    BUTTON_STATES = {filter_name: True for filter_name in FILTERS.keys()}

    abstract_consent: bool = False
    has_searched: bool = False

    class AbstractMarkdown(Markdown):
        init_text: str = "Abstract will be shown here"
        text: Reactive = reactive(init_text)

        def reset_text(self) -> None:
            self.text = self.init_text

        def add_text(self, text: str) -> None:
            self.text += text

        def watch_text(self) -> None:
            self.update(markdown=self.text)

    def compose(self) -> ComposeResult:
        self.border_title = "Search vespa.ai documentation"
        self.add_class("section")
        self.styles.border_title_align = "center"
        with VerticalScroll() as search_column:
            search_column.styles.width = "2fr"
            with Horizontal() as search_bar:
                search_bar.styles.height = 1
                yield Label("🔍", id="search-emoji")
                yield Input(
                    placeholder="Search Vespa.ai documentation",
                    id="search-input",
                )
                yield SearchButton("Search", id="search-button")
            with Horizontal() as filters:
                filters.styles.margin = 1
                filters.styles.height = 1
                # yield Label("Filter by:")
                for filter_name, filter_query in self.FILTERS.items():
                    yield FilterButton(
                        filter_name,
                        id=filter_name,
                        variant="success",
                        classes="filter-button",
                    )
                    yield Label(" ")
            with VerticalScroll(id="all-search-results") as results_area:
                yield Label("Empty for now", id="empty-results")
        with VerticalScroll() as chat_area:
            chat_area.styles.width = "1fr"
            chat_area.styles.height = "auto"
            yield Center(Label("Abstract (experimental)", id="abstract-label"))
            yield Label("")
            with ContentSwitcher(initial="before-consent"):
                with Vertical(id="before-consent") as initial:
                    initial.styles.height = "auto"
                    yield Center(Button("Show abstract", id="chat-button"))
                    yield Markdown(
                        "By showing, you consent to share data with OpenAI. The AI-generated abstract may have biases or inaccuracies. See privacy notice for more details. For the traditional search docs.search.ai.",
                        id="consent",
                    )
                with Vertical(id="after-consent"):
                    yield self.AbstractMarkdown(id="chat-response")

    def _on_mount(self):
        # TODO: Should only be when DocSearchView tab is selected.
        self.query_one(selector="#search-input").focus()
        # TODO: Seems like the reactivity of the markdown widget is not working
        self.watch(
            self.query_one(selector="#chat-response"),
            "text",
            self.query_one(selector="#chat-response").watch_text,
        )
        # Add binding to self.app
        # BINDINGS = [Binding("ctrl+enter", "send_request", "Search"),]
        # for binding in BINDINGS:
        #     self.app.BINDINGS.append(binding)

    def get_filter_string(self) -> str:
        # TODO: The filters does not seem to be applied correctly
        return " ".join(
            [
                self.FILTERS[filter_name]
                for filter_name, is_active in self.BUTTON_STATES.items()
                if is_active
            ]
        )

    @work(exclusive=True)
    async def send_chat_via_worker(self) -> None:
        await self.send_chat_request(
            query=self.search_query, filter_string=self.get_filter_string()
        )

    @work(exclusive=True)
    async def send_search_via_worker(self) -> None:
        await self.send_search_request(
            query=self.search_query, filter_string=self.get_filter_string()
        )

    @on(Markdown.LinkClicked)
    def handle_link_clicked(self, event: Markdown.LinkClicked) -> None:
        # Open in a new tab, if possible, else in the default browser
        webbrowser.open_new_tab(event.href)

    @on(FilterButton.Pressed, selector=".filter-button")
    def handle_filter_button(self, event) -> None:
        # Get the current state of the button
        current_state = self.BUTTON_STATES[event.button.id]
        self.query_one(selector=f"#{event.button.id}").set_class(
            not current_state, "disabled"
        )
        self.BUTTON_STATES[event.button.id] = not current_state

    @on(Button.Pressed, selector="#chat-button")
    def handle_submit_via_event(self) -> None:
        """Send the request."""
        self.query_one(ContentSwitcher).current = "after-consent"
        self.abstract_consent = True
        if self.has_searched:
            self.send_chat_via_worker()

    @on(Button.Pressed, selector="#search-button")
    def handle_search_via_event(self) -> None:
        """Send the request."""
        self.has_searched = True
        self.send_search_via_worker()
        if self.abstract_consent:
            self.send_chat_via_worker()

    @on(message_type=ChatResponse)
    def on_response_received(self, event: ChatResponse) -> None:
        self.abstract_markdown.add_text(event.response)
        self.abstract_markdown.update(markdown=self.abstract_markdown.text)

    @on(message_type=ResetChat)
    def reset_text(self) -> None:
        self.abstract_markdown.reset_text()
        self.abstract_markdown.update(markdown=self.abstract_markdown.text)

    async def send_chat_request(self, query: str, filter_string: str) -> None:
        "Send chat request"
        self.post_message(ResetChat())

        params = {
            "query": query,
            "filters": filter_string,
            "queryProfile": self.query_profile,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.chat_url, headers=self.chat_request_headers, params=params
                )
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[len("data: ") :]
                        self.post_message(ChatResponse(response=data))
                    elif line.startswith("event: end"):
                        print("\nEnd of message.")  # Final message post
                        break
            except httpx.HTTPStatusError as e:
                raise e

    async def send_search_request(self, query: str, filter_string: str) -> None:
        "Send search request"

        # query = 'hello'
        # filters = '+namespace:open-p +namespace:cloud-p +namespace:vespaapps-p +namespace:blog-p +namespace:pyvespa-p'
        # query_profile = 'llmsearch'

        params = {
            "query": query,
            "filters": filter_string,
            "queryProfile": self.query_profile,
        }
        self.post_message(ResetSearch())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.search_url, headers=self.search_request_headers, params=params
                )
                response.raise_for_status()
                resp = response.json()
                children = resp.get("root", {}).get("children", [])
                results = []
                for number, child in enumerate(children, start=1):
                    fields = child.get("fields", {})
                    result = SearchResult(
                        number=number,
                        title=fields.get("title", ""),
                        base_uri=fields.get("base_uri", ""),
                        path=fields.get("path", ""),
                        content=fields.get("content", ""),
                        relevance=child.get("relevance", 0.0),
                        source=child.get("source", ""),
                    )
                    results.append(result)
                for result in results:
                    search_response = SearchResponse(results=results)
            except httpx.HTTPStatusError as e:
                search_response = SearchResponse(results=[])
                raise e
                exit()
        self.post_message(search_response)
        # self.query_one(selector="#empty-results").update(f"finished")

    @on(message_type=SearchResponse)
    def on_search_response_received(self, event: SearchResponse) -> None:
        mount_area = self.query_one(
            selector="#all-search-results", expect_type=VerticalScroll
        )
        for result_no, result in enumerate(event.results, start=1):
            md_result = result.to_markdown()
            mount_area.mount(Markdown(md_result))

    @on(message_type=ResetSearch)
    def reset_search(self, event: ResetSearch) -> None:
        self.query_one(selector="#all-search-results").remove_children()
        # self.query_one(selector="#empty-results").update("Empty for now")

    @property
    def search_request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Vespa TUI",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "application/json",
            "Referer": "https://search.vespa.ai/",
            "Origin": "https://search.vespa.ai",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=4",
        }

    @property
    def chat_request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Vespa TUI",
            "Accept": "text/event-stream",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://search.vespa.ai/",
            "Origin": "https://search.vespa.ai",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=1",
            "TE": "trailers",
        }

    @property
    def query_profile(self) -> str:
        return "llmsearch"

    @property
    def base_url(self) -> str:
        return "https://api.search.vespa.ai/"

    @property
    def search_url(self) -> str:
        return f"{self.base_url}search/"

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}stream/"

    @property
    def search_query(self) -> str:
        return self.query_one(selector="#search-input").value

    @property
    def abstract_markdown(self) -> Markdown:
        return self.query_one(
            selector="#chat-response", expect_type=self.AbstractMarkdown
        )
