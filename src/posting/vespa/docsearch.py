from textual.message import Message
from pydantic.dataclasses import dataclass as pydantic_dataclass
from textual.widgets import Input, ContentSwitcher, DataTable, Markdown, Button, Label
from textual.containers import VerticalScroll, Horizontal, Center, Grid, Vertical
from posting.vespa.buttons import SearchButton, FilterButton
from textual.binding import Binding
import httpx
from dataclasses import dataclass
from typing import List
import webbrowser
from textual.reactive import reactive, Reactive
from textual import work
from textual.app import ComposeResult, on

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
    BINDINGS = [
        Binding(
            "ctrl+enter",
            "search_via_event",
            description="Search",
        ),
    ]
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
    def action_search_via_event(self) -> None:
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
