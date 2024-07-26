from textual.containers import Vertical
from textual.widgets import Label, Markdown, Button
from textual.app import ComposeResult, on
from textual.message import Message
from textual.widgets import Input, ContentSwitcher, DataTable
from textual.containers import VerticalScroll, Horizontal, Center, Grid
from textual import work
from textual.reactive import reactive, Reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label
from textual.binding import Binding
from rich.text import Text
from pydantic.dataclasses import dataclass as pydantic_dataclass
from posting.vespasrc.buttons import SearchButton, FilterButton
from vespa.deployment import VespaCloud

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
        

        & #dialog {
            grid-size: 2;
            grid-gutter: 1 2;
            grid-rows: 1fr 4;
            padding: 0 1;
            width: 60;
            height: 11;
            border: thick $background 80%;
            background: $surface;
        }

        & #label-token {
            column-span: 2;
            height: 1fr;
            width: 1fr;
            content-align: center middle;
        }

        & #input-token {
            column-span: 2;
            width: 1fr;
        }

        & Button {
            width: 100%;
        }
    }
    """
    AUTO_FOCUS = "#input-token"

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Input token from vespa cloud", id="label-token"),
            Input(placeholder="Token", id="input-token"),
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
    AUTO_FOCUS = "#tenant_input"
    BINDINGS = [
        Binding(
            "ctrl+l",
            "ring_bell",
            description="Ring Bell",
        ),
    ]

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
        # self.focus("tenant_input")
        # table.add_columns(*ROWS[0])
        # table.add_rows(ROWS[1:])

    def action_ring_bell(self) -> None:
        self.app.bell()

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
