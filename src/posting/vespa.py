from textual.containers import Vertical
from textual.widgets import Label, Markdown, Button
from textual.app import ComposeResult, on  
from textual.message import Message
from posting.widgets.request.url_bar import SendRequestButton
from textual.widgets import Input, Markdown, Placeholder, Label, ContentSwitcher, Button, Collapsible
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal, Vertical, Center
from textual.binding import Binding
from textual import work, on
from textual.message import Message
from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass
from posting.widgets.vespa.buttons import SearchButton, FilterButton
from dataclasses import dataclass
import httpx
import asyncio
from dataclasses import dataclass
from subprocess import run
import pty
import os
import sys
import subprocess
import shlex
import select
from typing import List



class VespaPage(Vertical):
    """ The Vespa page. """

    @dataclass
    class AuthenticatedMessage(Message):
        authenticated: bool = True
    
    def compose(self) -> ComposeResult:
        yield Label("Vespa")
        yield Button("Authenticate", id="auth_button", variant="primary")
        yield Markdown("Output:", id="output")
    
    @on(Button.Pressed, "#auth_button")
    def run_vespa_auth_login(self, event):
        # Run the Vespa auth login command and capture the output
        # Open a new pseudo-terminal
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
                            self.query_one("#output", Markdown).update(markdown=f"Output: {output}")
                            sys.stdout.flush()
                        if "Success:" in output:
                            finished = True  # Exit the loop after success message
                            break

                        # Check for input only if running in a Jupyter Notebook
                        if "[Y/n]" in output:
                            user_input = "y\n" #input() + "\n"
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
        self.query_one("#output", Markdown).update(markdown=f"Output: {posted} Msg: {msg}")






@dataclass
class ChatResponse(Message):
    response: str

@pydantic_dataclass(config=dict(extra="allow"))
class SearchResult():
    title: str
    base_uri: str
    path: str
    content: str
    relevance: float

    def to_markdown(self) -> str:
        return f"{self.title}\n\n{self.content}\n\n[Read more]({self.base_uri}{self.path})"

@dataclass
class SearchResponse(Message):
    results: List[SearchResult]

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

    FILTERS = {"docs": "+namespace:open-p", "cloud-docs": "+namespace:cloud-p", "sample-apps":"+namespace:vespaapps-p", "blog": "+namespace:blog-p", "pyvespa": "+namespace:pyvespa-p"}
    # Initialize the button states to False
    BUTTON_STATES = {filter_name: False for filter_name in FILTERS.keys()}

    
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
                yield Label("Filter by:")
                for filter_name, filter_query in self.FILTERS.items():
                    yield FilterButton(filter_name, id=filter_name, variant="success", classes="filter-button")
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
                    yield Markdown("This is an AI-generated abstract")
                    yield Markdown("Response: ", id="chat-response")

    def _on_mount(self):
        self.query_one(selector="#search-input").focus()
        # Add binding to self.app
        # BINDINGS = [Binding("ctrl+enter", "send_request", "Search"),]
        # for binding in BINDINGS:
        #     self.app.BINDINGS.append(binding)
    
    def get_filter_string(self) -> str:
        return " ".join([filter_name for filter_name, is_active in self.BUTTON_STATES.items() if is_active])

    @work(exclusive=True)
    async def send_chat_via_worker(self) -> None:
        await self.send_chat_request()
    
    @work(exclusive=True)
    async def send_search_via_worker(self) -> None:
        search_query = self.query_one(selector="#search-input").value
        await self.send_search_request(query=search_query, filter_string=self.get_filter_string())
    
    @on(FilterButton.Pressed, selector=".filter-button")
    def handle_filter_button(self, event) -> None:
        # Get the current state of the button
        current_state = self.BUTTON_STATES[event.button.id]
        self.query_one(selector=f"#{event.button.id}").set_class(not current_state, "disabled")
        self.BUTTON_STATES[event.button.id] = not current_state

    @on(Button.Pressed, selector="#chat-button")
    def handle_submit_via_event(self) -> None:
        """Send the request."""
        self.query_one(ContentSwitcher).current = "after-consent"
        self.send_chat_via_worker()
    
    @on(Button.Pressed, selector="#search-button")
    def handle_search_via_event(self) -> None:
        """Send the request."""
        self.send_search_via_worker()

    async def send_chat_request(self) -> None:
        "Temporarily simulate a chat request"
        # Sleep for 1 sec after button is pushed, then update the chat area
        await asyncio.sleep(1)
        self.post_message(ChatResponse(response="This is blblblblblb response"))
    
    async def send_search_request(self, query: str, filter_string: str) -> None:
        "Temporarily simulate a chat request"

        headers = {
            'User-Agent': 'Vespa TUI',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'application/json',
            'Referer': 'https://search.vespa.ai/',
            'Origin': 'https://search.vespa.ai',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Priority': 'u=4',
        }

        #query = 'hello'
        #filters = '+namespace:open-p +namespace:cloud-p +namespace:vespaapps-p +namespace:blog-p +namespace:pyvespa-p'
        query_profile = 'llmsearch'

        params = {
            'query': query,
            'filters': filter_string,
            'queryProfile': query_profile,
        }

        url = 'https://api.search.vespa.ai/search/'

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                resp = response.json()
                children = resp.get('root', {}).get('children', []) 
                results = []
                for child in children:
                    fields = child.get('fields', {})
                    result = SearchResult(
                        title=fields.get('title', ''),
                        base_uri=fields.get('base_uri', ''),
                        path=fields.get('path', ''),
                        content=fields.get('content', ''),
                        relevance=child.get('relevance', 0.0)
                    )
                    results.append(result)
                for result in results:
                    search_response = SearchResponse(results=results)
            except httpx.HTTPStatusError as e:
                search_response = SearchResponse(results=[])
                print(f"HTTP status error: {e}")
                raise e
                exit()
        self.post_message(search_response)
        self.query_one(selector="#empty-results").update(f"finished")

    @on(message_type=ChatResponse)
    def on_response_received(self, event: ChatResponse) -> None:
        self.query_one(selector="#chat-response", expect_type=Markdown).update(
            markdown=event.response
        )
        print("Sending request")
    
    @on(message_type=SearchResponse)
    def on_search_response_received(self, event: SearchResponse) -> None:
        mount_area = self.query_one(selector="#all-search-results", expect_type=VerticalScroll)
        for result in event.results:
            md_result = result.to_markdown()
            mount_area.mount(Markdown(md_result))
    
    @property
    def sample_response(self) -> SearchResponse:
        return SearchResponse(
            results=[
                SearchResult(
                    title="Sample title",
                    base_uri="https://vespa.ai",
                    path="/docs",
                    content="Sample content",
                    relevance=0.9,
                ),
                SearchResult(
                    title="Sample title 2",
                    base_uri="https://vespa.ai",
                    path="/docs",
                    content="Sample content 2",
                    relevance=0.8,
                ),
            ]
        )