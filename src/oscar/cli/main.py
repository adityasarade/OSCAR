"""
OSCAR CLI — GitHub-Specialized AI Coding Assistant
"""

import click
import importlib.metadata
import json
import sys
import os
from collections import deque
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

from oscar.config.settings import settings
from oscar.core.repo_context import set_active_repo, get_active_repo, is_git_repo
from oscar.logging_config import configure_logging

console = Console()

try:
    OSCAR_VERSION = importlib.metadata.version("oscar-agent")
except importlib.metadata.PackageNotFoundError:
    OSCAR_VERSION = "unknown"


def display_welcome():
    """Display welcome message."""
    welcome_text = Text()
    welcome_text.append("OSCAR ", style="bold blue")
    welcome_text.append("— GitHub-Specialized AI Coding Assistant", style="white")

    panel = Panel(welcome_text, title="Welcome", border_style="blue", padding=(1, 2))
    console.print(panel)

    repo = get_active_repo() or os.getcwd()
    config_info = (
        "\n    [bold]Powered by:[/bold] Asterix + Gemini 2.5 Flash (Vertex AI)\n"
        f"    [bold]Repo:[/bold] [cyan]{repo}[/cyan]"
        + ("" if is_git_repo(repo) else "  [yellow](not a git repo)[/yellow]")
        + "\n    [dim]Type 'help' for commands or describe what you want to do...[/dim]\n"
    )
    console.print(config_info)


def display_help():
    """Display available commands."""
    help_text = """
    [bold]Commands:[/bold]
    [cyan]help[/cyan] or [cyan]?[/cyan]    Show this help
    [cyan]config[/cyan]       Show configuration
    [cyan]repo[/cyan]         Show or set the active repository
    [cyan]test[/cyan]         Test LLM connection
    [cyan]serve[/cyan]        Start the API server (port 8420)
    [cyan]quit[/cyan]         Exit OSCAR

    [bold]GitHub Assistant — just type naturally:[/bold]
    "Show me the git status"
    "Compare main and feature-branch"
    "Review the changes on dev vs main"
    "What changed in the last 5 commits?"
    "Show me the diff for src/main.py"
    "List all branches"
    "Run the test suite"
    "Search for Python async best practices"

    [bold]Safety:[/bold] Destructive operations (push, checkout, shell commands)
    require your confirmation before executing.
    """
    console.print(help_text)


def show_config():
    """Show current configuration."""
    from oscar.core.agent import get_agent

    agent = get_agent()
    tool_count = len(agent.get_all_tools())
    block_names = list(agent.blocks.keys())
    repo = get_active_repo() or "(default cwd)"

    config_details = f"""
    [bold]OSCAR Configuration:[/bold]

    [bold]Agent:[/bold]
    Model: [cyan]gemini-2.5-flash[/cyan] (Vertex AI)
    Tools: [green]{tool_count}[/green] registered
    Memory blocks: [green]{', '.join(block_names)}[/green]

    [bold]Repository:[/bold]
    Active repo: [cyan]{repo}[/cyan]

    [bold]Directories:[/bold]
    Data: [dim]{Path('./data').resolve()}[/dim]
    """
    console.print(config_details)


def handle_repo_command(rest: str) -> None:
    """`repo` — show; `repo <path>` — set; `repo clear` — unset."""
    arg = rest.strip()
    if not arg:
        active = get_active_repo()
        if active:
            console.print(f"[bold]Active repo:[/bold] [cyan]{active}[/cyan]")
            if not is_git_repo(active):
                console.print("[yellow]Note: this path is not inside a git work tree.[/yellow]")
        else:
            console.print(f"[dim]No explicit repo set. Using cwd: {os.getcwd()}[/dim]")
        return

    if arg.lower() == "clear":
        set_active_repo(None)
        console.print("[green]Cleared active repo.[/green]")
        return

    resolved = set_active_repo(arg)
    if resolved is None:
        console.print(f"[red]Could not resolve path: {arg}[/red]")
        return
    console.print(f"[green]Active repo set to:[/green] [cyan]{resolved}[/cyan]")
    if not is_git_repo(resolved):
        console.print("[yellow]Warning: this directory is not inside a git work tree.[/yellow]")


def test_llm_connection():
    """Test LLM connection via Asterix agent."""
    console.print("[yellow]Testing Gemini connection via Vertex AI...[/yellow]")
    try:
        from oscar.core.agent import get_agent

        agent = get_agent()
        response = agent.chat("Respond with exactly: OSCAR connection OK")
        console.print(f"[green]OK[/green] Response: {response}")
    except Exception as e:
        console.print(f"[red]FAIL[/red] {e}")


def _render_tool_call(tool_name: str, args_summary: str, risk: str) -> None:
    risk_color = {
        "low": "dim",
        "medium": "yellow",
        "high": "bold yellow",
        "dangerous": "bold red",
    }.get(risk, "dim")
    args_text = f" [dim]{args_summary}[/dim]" if args_summary else ""
    risk_tag = f" [{risk_color}]({risk})[/{risk_color}]" if risk and risk != "low" else ""
    console.print(f"  [bold cyan]›[/bold cyan] [cyan]{tool_name}[/cyan]{risk_tag}{args_text}")


def _render_tool_result(tool_name: str, snippet: str, ok: bool) -> None:
    symbol = "[green]✓[/green]" if ok else "[red]✗[/red]"
    if snippet:
        console.print(f"    {symbol} [dim]{snippet}[/dim]")
    else:
        console.print(f"    {symbol} [dim]({tool_name} done)[/dim]")


def process_user_request(user_input: str):
    """Process natural language request through the Asterix agent.

    Streams a compact view of the agent's tool usage to the console while it
    works, then prints the final markdown response.
    """
    try:
        from oscar.core import events
        from oscar.core.agent import get_agent

        agent = get_agent()

        def _on_event(event):
            etype = event.get("type")
            if etype == "tool_call":
                _render_tool_call(
                    event.get("tool_name", "tool"),
                    event.get("data", "") or "",
                    event.get("risk", "low"),
                )
            elif etype == "tool_result":
                _render_tool_result(
                    event.get("tool_name", "tool"),
                    event.get("data", "") or "",
                    bool(event.get("ok", True)),
                )
            # step/thinking events are intentionally suppressed in the CLI;
            # the tool_call line conveys the same information without
            # double-printing.

        unsubscribe = events.subscribe(_on_event)
        try:
            with console.status("[bold blue]Thinking...[/bold blue]", spinner="dots"):
                response = agent.chat(user_input)
        finally:
            unsubscribe()

        console.print()
        console.print(Markdown(response))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.getenv("OSCAR_DEBUG", "").lower() == "true":
            import traceback
            traceback.print_exc()


def start_api_server():
    """Start the FastAPI server."""
    try:
        from oscar.api.server import start_server

        console.print("[bold green]Starting OSCAR API server on port 8420...[/bold green]")
        start_server()
    except ImportError:
        console.print("[red]FastAPI server not available. Install fastapi and uvicorn.[/red]")
    except Exception as e:
        console.print(f"[red]Server error: {e}[/red]")


def _tail_lines(path: Path, count: int) -> list[str]:
    """Return the last count lines from path."""
    if count <= 0 or not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as handle:
        return list(deque(handle, maxlen=count))


@click.group(invoke_without_command=True)
@click.version_option(OSCAR_VERSION, "-V", "--version", prog_name="oscar")
@click.pass_context
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--config-check", is_flag=True, help="Check configuration and exit")
@click.option(
    "--repo",
    "repo",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    help="Path to the git repository OSCAR should operate on (defaults to current directory)",
)
def main(ctx, debug, config_check, repo):
    """OSCAR — GitHub-Specialized AI Coding Assistant"""

    if debug:
        os.environ["OSCAR_DEBUG"] = "true"

    configure_logging(level="DEBUG" if debug else "WARNING")

    # Set repo from --repo flag, or default to the cwd OSCAR was invoked from.
    initial_repo = repo or os.getcwd()
    resolved = set_active_repo(initial_repo)
    if resolved is None and repo:
        console.print(f"[red]Cannot use --repo {repo!r}: directory does not exist.[/red]")
        sys.exit(1)

    if ctx.invoked_subcommand is not None:
        return

    try:
        if config_check:
            from oscar.core.agent import get_agent

            agent = get_agent()
            tool_count = len(agent.get_all_tools())
            console.print(f"[green]OK[/green] Agent initialized with {tool_count} tools")
            console.print("[green]OK[/green] Model: gemini-2.5-flash (Vertex AI)")
            console.print(f"[green]OK[/green] Memory blocks: {list(agent.blocks.keys())}")
            console.print(f"[green]OK[/green] Active repo: {get_active_repo() or '(default)'}")
            return

        display_welcome()

        while True:
            try:
                user_input = console.input("[bold blue]OSCAR>[/bold blue] ").strip()

                if not user_input:
                    continue

                lowered = user_input.lower()
                first_word = lowered.split(maxsplit=1)[0]

                if first_word in ("quit", "exit"):
                    console.print("[dim]Goodbye.[/dim]")
                    break
                elif first_word in ("help", "?"):
                    display_help()
                elif first_word == "config":
                    show_config()
                elif first_word == "repo":
                    handle_repo_command(user_input[len(first_word):])
                elif first_word == "test":
                    test_llm_connection()
                elif first_word == "serve":
                    start_api_server()
                else:
                    process_user_request(user_input)

            except KeyboardInterrupt:
                console.print("\n[dim]Use 'quit' to exit[/dim]")
            except EOFError:
                console.print("\n[dim]Goodbye.[/dim]")
                break

    except Exception as e:
        console.print(f"[red]Error starting OSCAR: {e}[/red]")
        if debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command("audit")
@click.option("--tail", default=20, show_default=True, type=int, help="Number of recent audit entries to show")
def audit(tail):
    """Show recent audit log entries."""
    audit_path = settings.data_dir / "logs" / "audit.jsonl"
    rows = _tail_lines(audit_path, tail)

    table = Table(title="OSCAR Audit Log")
    table.add_column("Timestamp")
    table.add_column("Tool")
    table.add_column("Risk")
    table.add_column("OK")
    table.add_column("Arguments")

    for row in rows:
        try:
            entry = json.loads(row)
            arguments = json.dumps(entry.get("arguments", {}))
            approved = entry.get("approved")
            approved_cell = "" if approved is None else ("y" if approved else "n")
            table.add_row(
                str(entry.get("timestamp", "")),
                str(entry.get("tool", "")),
                str(entry.get("risk", "")),
                approved_cell,
                arguments,
            )
        except json.JSONDecodeError:
            table.add_row("", "", "", "", row.strip())

    if not rows:
        console.print(f"[dim]No audit entries found at {audit_path}[/dim]")
        return

    console.print(table)


@main.command("metrics")
def metrics():
    """Summarize the audit log: tool counts, risk distribution, latency."""
    from oscar.core.metrics import summarize_audit_log, audit_path

    summary = summarize_audit_log()
    path = audit_path()
    if summary["entries"] == 0:
        console.print(f"[dim]No audit entries found at {path}[/dim]")
        return

    console.print(f"[bold]Audit summary[/bold]  [dim]{path}[/dim]")
    console.print(f"  entries:    [cyan]{summary['entries']}[/cyan]")
    console.print(
        f"  approved:   [green]{summary['approved']}[/green]   "
        f"rejected: [red]{summary['rejected']}[/red]"
    )

    risk_table = Table(title="Risk distribution", show_header=False)
    risk_table.add_column("tier")
    risk_table.add_column("count", justify="right")
    for tier, count in summary["by_risk"].items():
        if count == 0:
            continue
        risk_table.add_row(tier, str(count))
    console.print(risk_table)

    tool_table = Table(title="Per-tool calls", show_header=False)
    tool_table.add_column("tool")
    tool_table.add_column("calls", justify="right")
    for tool, count in sorted(
        summary["by_tool"].items(), key=lambda kv: kv[1], reverse=True
    ):
        tool_table.add_row(tool, str(count))
    console.print(tool_table)

    latency = summary.get("latency_ms")
    if latency:
        console.print(
            f"[bold]Latency (ms)[/bold] over {latency['count']} sampled calls: "
            f"mean={latency['mean']}  median={latency['median']}  "
            f"p95={latency['p95']}  max={latency['max']}"
        )
    else:
        console.print(
            "[dim]No latency samples — run the agent on real tool calls to populate them.[/dim]"
        )


if __name__ == "__main__":
    main()
