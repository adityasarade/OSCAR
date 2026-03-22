"""
OSCAR CLI — GitHub-Specialized AI Coding Assistant
"""

import click
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

console = Console()


def display_welcome():
    """Display welcome message."""
    welcome_text = Text()
    welcome_text.append("OSCAR ", style="bold blue")
    welcome_text.append("— GitHub-Specialized AI Coding Assistant", style="white")

    panel = Panel(welcome_text, title="Welcome", border_style="blue", padding=(1, 2))
    console.print(panel)

    config_info = """
    [bold]Powered by:[/bold] Asterix + Gemini 2.5 Flash (Vertex AI)
    [dim]Type 'help' for commands or describe what you want to do...[/dim]
    """
    console.print(config_info)


def display_help():
    """Display available commands."""
    help_text = """
    [bold]Commands:[/bold]
    [cyan]help[/cyan] or [cyan]?[/cyan]    Show this help
    [cyan]config[/cyan]       Show configuration
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

    config_details = f"""
    [bold]OSCAR Configuration:[/bold]

    [bold]Agent:[/bold]
    Model: [cyan]gemini-2.5-flash[/cyan] (Vertex AI)
    Tools: [green]{tool_count}[/green] registered
    Memory blocks: [green]{', '.join(block_names)}[/green]

    [bold]Directories:[/bold]
    Data: [dim]{Path('./data').resolve()}[/dim]
    """
    console.print(config_details)


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


def process_user_request(user_input: str):
    """Process natural language request through the Asterix agent."""
    try:
        from oscar.core.agent import get_agent

        agent = get_agent()

        with console.status("[bold blue]Thinking...[/bold blue]"):
            response = agent.chat(user_input)

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


@click.command()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--config-check", is_flag=True, help="Check configuration and exit")
def main(debug, config_check):
    """OSCAR — GitHub-Specialized AI Coding Assistant"""

    if debug:
        os.environ["OSCAR_DEBUG"] = "true"

    try:
        if config_check:
            from oscar.core.agent import get_agent

            agent = get_agent()
            tool_count = len(agent.get_all_tools())
            console.print(f"[green]OK[/green] Agent initialized with {tool_count} tools")
            console.print(f"[green]OK[/green] Model: gemini-2.5-flash (Vertex AI)")
            console.print(f"[green]OK[/green] Memory blocks: {list(agent.blocks.keys())}")
            return

        display_welcome()

        while True:
            try:
                user_input = console.input("[bold blue]OSCAR>[/bold blue] ").strip()

                if not user_input:
                    continue

                cmd = user_input.lower()

                if cmd in ("quit", "exit"):
                    console.print("[dim]Goodbye.[/dim]")
                    break
                elif cmd in ("help", "?"):
                    display_help()
                elif cmd == "config":
                    show_config()
                elif cmd == "test":
                    test_llm_connection()
                elif cmd == "serve":
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


if __name__ == "__main__":
    main()
