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
from rich.align import Align
from rich import box


console = Console()

ascii_banner = r"""
   ______                     __  ___       __
  / ____/___  ____ ___  ___  /  |/  /___ __/ /_____ _
 / /   / __ \/ __ `__ \/ _ \/ /|_/ / __ `/ __/ __ `/
/ /___/ /_/ / / / / / /  __/ /  / / /_/ / /_/ /_/ /
\____/\____/_/ /_/ /_/\___/_/  /_/\__,_/\__/\__,_/

            TELEGRAM BOT ENGINE
"""


def system_table(status: str) -> Table:
    table = Table(
        box=box.ROUNDED,
        expand=True,
        border_style="cyan",
    )

    table.add_column("Field", style="cyan", justify="right")
    table.add_column("Value", style="white")

    table.add_row("Status", f"[bold green]{status}")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Platform", platform.system())
    table.add_row("Environment", "Dev")

    return table


def build_layout(progress) -> Layout:

    layout = Layout()

    layout.split_column(
        Layout(name="header", size=11),
        Layout(name="progress", size=3),
        Layout(name="body", ratio=1),
    )

    layout["body"].split_row(
        Layout(name="status", ratio=1),
        Layout(name="logs", ratio=2),
    )

    layout["progress"].update(progress)

    return layout


def startup_screen():

    console.clear()

    progress = Progress(
        SpinnerColumn(style="bold cyan"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, complete_style="green"),
        TextColumn("[cyan]{task.percentage:>3.0f}%"),
    )

    task = progress.add_task("Booting Engine", total=6)

    layout = build_layout(progress)

    banner = Align.center(
        Text(ascii_banner, style="bold magenta"),
        vertical="middle",
    )

    layout["header"].update(
        Panel(
            banner,
            border_style="bright_blue",
            box=box.DOUBLE,
        )
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

    with Live(layout, refresh_per_second=12):

        for step in steps:

            logs.append(f"[green]✔[/green] {step}")

            progress.update(task, description=f"[cyan]{step}")

            layout["status"].update(
                Panel(
                    system_table(step),
                    title="[bold cyan]System Status",
                    border_style="cyan",
                    box=box.ROUNDED,
                )
            )

            layout["logs"].update(
                Panel(
                    "\n".join(logs[-8:]),
                    title="[bold green]Boot Log",
                    border_style="green",
                    box=box.ROUNDED,
                )
            )

            time.sleep(0.7)

            progress.advance(task)


    console.print()
    console.print(
        Panel.fit(
            f"[bold green]✓ System Ready[/bold green]\n[dim]Environment: Development[/dim]",
            border_style="green",
            box=box.DOUBLE,
        )
    )

if __name__ == "__main__":
    startup_screen()