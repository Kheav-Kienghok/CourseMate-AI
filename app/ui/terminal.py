from __future__ import annotations

import time
import platform
import sys

from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text

from utils.config import get_environment

console = Console()

ascii_banner = r"""
     _________                                      _____          __              _____  .___ 
     \_   ___ \  ____  __ _________  ______ ____   /     \ _____ _/  |_  ____     /  _  \ |   |
     /    \  \/ /  _ \|  |  \_  __ \/  ___// __ \ /  \ /  \\__  \\   __\/ __ \   /  /_\  \|   |
     \     \___(  <_> )  |  /|  | \/\___ \\  ___//    Y    \/ __ \|  | \  ___/  /    |    \   |
      \______  /\____/|____/ |__|  /____  >\___  >____|__  (____  /__|  \___  > \____|__  /___|
             \/                         \/     \/        \/     \/          \/          \/     
                                         TELEGRAM BOT ENGINE
"""


def system_table(status: str) -> Table:
    table = Table.grid(padding=1)
    # Force two columns so labels / values align and wrap properly
    table.add_column("Field", justify="right", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Status", status)
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Platform", platform.system())
    table.add_row("Environment", get_environment())
    return table


def build_layout(progress) -> Layout:
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=9),
        Layout(name="progress", size=3),
        Layout(name="body", ratio=1),
    )

    layout["body"].split_row(
        Layout(name="status"),
        Layout(name="logs", ratio=2),
    )

    layout["progress"].update(progress)

    return layout


def startup_screen():

    console.clear()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
    )

    task = progress.add_task("Booting...", total=6)

    layout = build_layout(progress)

    layout["header"].update(
        Panel(Text(ascii_banner, style="bold magenta"), border_style="bright_blue")
    )

    steps = [
        "Loading configuration",
        "Connecting modules",
        "Preparing Telegram API",
        "Initializing AI core",
        "Starting bot services",
        "Finalizing startup",
    ]

    logs = []

    with Live(layout, refresh_per_second=10):

        for step in steps:

            logs.append(f"[green]✔[/green] {step}")

            progress.update(task, description=step)

            layout["status"].update(
                Panel(system_table(step), title="System Status", border_style="cyan")
            )

            layout["logs"].update(
                Panel("\n".join(logs[-8:]), title="Boot Log", border_style="green")
            )

            time.sleep(0.7)
            progress.advance(task)

    env = get_environment()
    console.print(f"\n[bold green]✓ System Ready[/bold green] [dim]({env})[/dim]")
    console.print(
        f"[dim]Telegram bot is ready to start in {env} environment.[/dim]"
    )


def prompt_start_or_exit() -> bool:
    """Ask the user whether to start the bot or exit.

    Returns True to start the bot, False to exit immediately.
    """

    console.print(
        "\n[cyan]Press [Enter] to start the bot, or type 'q' to quit.[/cyan]"
    )
    try:
        choice = console.input("[bold]> [/bold]").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Exiting CourseMate AI.[/yellow]")
        return False

    if choice in {"q", "quit", "exit"}:
        console.print("[yellow]Exiting CourseMate AI.[/yellow]")
        return False

    console.print("\n[bold green]🚀 Starting Telegram Bot...[/bold green]")

    return True