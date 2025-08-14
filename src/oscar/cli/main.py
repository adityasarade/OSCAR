"""
OSCAR CLI - Simplified command-line interface
"""

import click
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from oscar.config.settings import settings

console = Console()


def display_welcome():
    """Display welcome message."""
    welcome_text = Text()
    welcome_text.append("🤖 OSCAR ", style="bold blue")
    welcome_text.append("- Operating System's Complete Agentic Rex", style="white")
    
    panel = Panel(welcome_text, title="Welcome", border_style="blue", padding=(1, 2))
    console.print(panel)
    
    # Show current configuration
    active_provider = settings.llm_config.active_provider
    active_config = settings.get_active_llm_config()
    
    config_info = f"""
[bold]Configuration:[/bold]
• LLM Provider: [green]{active_provider}[/green]
• Model: [cyan]{active_config.model}[/cyan]
• Safe Mode: [{'green' if settings.safe_mode else 'red'}]{settings.safe_mode}[/]
• Debug Mode: [{'yellow' if settings.debug_mode else 'dim'}]{settings.debug_mode}[/]
"""
    console.print(config_info)


def display_help():
    """Display available commands."""
    help_text = """
[bold]Available Commands:[/bold]
• [cyan]help[/cyan] or [cyan]?[/cyan] - Show this help
• [cyan]config[/cyan] - Show configuration details
• [cyan]test[/cyan] - Test LLM connection
• [cyan]test-agent[/cyan] - Test all components
• [cyan]quit[/cyan] or [cyan]exit[/cyan] - Exit OSCAR

[bold]Natural Language Usage:[/bold]
Just type your request in plain English:
• "Create a new Python project"
• "Download the latest Python installer"
• "List files in current directory"
• "Search for machine learning tutorials"

[bold]Safety Features:[/bold]
• All actions require confirmation
• Dangerous commands need extra approval
• Complete audit logging
• Dry-run mode available (use --dry-run)
"""
    console.print(help_text)


@click.command()
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--dry-run', is_flag=True, help='Enable dry-run mode')
@click.option('--config-check', is_flag=True, help='Check configuration and exit')
def main(debug, dry_run, config_check):
    """OSCAR - Operating System's Complete Agentic Rex"""
    
    # Override settings if flags provided
    if debug:
        os.environ['OSCAR_DEBUG'] = 'true'
    if dry_run:
        os.environ['OSCAR_DRY_RUN'] = 'true'
    
    try:
        # Configuration check mode
        if config_check:
            console.print("[green]✓[/green] Configuration loaded successfully")
            console.print(f"[green]✓[/green] Active LLM: {settings.llm_config.active_provider}")
            console.print(f"[green]✓[/green] Data directory: {settings.data_dir}")
            
            try:
                api_key = settings.get_api_key(settings.llm_config.active_provider)
                console.print(f"[green]✓[/green] API key found")
                console.print("[bold green]Configuration check passed![/bold green]")
            except ValueError as e:
                console.print(f"[red]✗[/red] {e}")
            return
        
        # Start main CLI
        display_welcome()
        console.print("\n[dim]Type 'help' for commands or describe what you want to do...[/dim]\n")
        
        # Main interaction loop
        while True:
            try:
                user_input = console.input("[bold blue]OSCAR>[/bold blue] ").strip()
                
                if not user_input:
                    continue
                
                # Handle built-in commands
                if user_input.lower() in ['quit', 'exit']:
                    console.print("[yellow]Goodbye! 👋[/yellow]")
                    break
                
                elif user_input.lower() in ['help', '?']:
                    display_help()
                
                elif user_input.lower() == 'config':
                    show_config()
                
                elif user_input.lower() == 'test':
                    test_llm_connection()
                
                elif user_input.lower() == 'test-agent':
                    test_agent_components()
                
                else:
                    # Process natural language input
                    process_user_request(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'quit' or 'exit' to leave OSCAR[/yellow]")
            except EOFError:
                console.print("\n[yellow]Goodbye! 👋[/yellow]")
                break
    
    except Exception as e:
        console.print(f"[red]Error starting OSCAR: {e}[/red]")
        if debug or settings.debug_mode:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def show_config():
    """Show current configuration."""
    active_provider = settings.llm_config.active_provider
    active_config = settings.get_active_llm_config()
    
    config_details = f"""
[bold]OSCAR Configuration:[/bold]

[bold]LLM Settings:[/bold]
• Provider: [green]{active_provider}[/green]
• Model: [cyan]{active_config.model}[/cyan]
• Max Tokens: [yellow]{active_config.max_tokens}[/yellow]
• Temperature: [yellow]{active_config.temperature}[/yellow]

[bold]System Settings:[/bold]
• Safe Mode: [{'green' if settings.safe_mode else 'red'}]{settings.safe_mode}[/]
• Debug Mode: [{'yellow' if settings.debug_mode else 'dim'}]{settings.debug_mode}[/]
• Dry Run: [{'yellow' if settings.dry_run_mode else 'dim'}]{settings.dry_run_mode}[/]

[bold]Directories:[/bold]
• Data: [dim]{settings.data_dir}[/dim]
• Config: [dim]{settings.config_dir}[/dim]
"""
    console.print(config_details)


def test_llm_connection():
    """Test LLM connection."""
    console.print("[yellow]Testing LLM connection...[/yellow]")
    
    try:
        from groq import Groq
        
        api_key = settings.get_api_key(settings.llm_config.active_provider)
        active_config = settings.get_active_llm_config()
        
        client = Groq(api_key=api_key)
        
        completion = client.chat.completions.create(
            model=active_config.model,
            messages=[{"role": "user", "content": "Hello, respond with 'OSCAR connection test successful'"}],
            max_tokens=50,
            temperature=0.1
        )
        
        response = completion.choices[0].message.content
        console.print(f"[green]✓[/green] LLM Response: {response}")
        
    except Exception as e:
        console.print(f"[red]✗[/red] LLM connection failed: {e}")


def test_agent_components():
    """Test all agent components."""
    console.print("[bold blue]🧪 Testing OSCAR Components...[/bold blue]\n")
    
    try:
        from oscar.core.agent import OSCARAgent
        
        agent = OSCARAgent()
        test_results = agent.test_all_components()
        
        if test_results["overall"]["ready"]:
            console.print("\n[bold green]🎉 OSCAR is ready for requests![/bold green]")
        else:
            console.print("\n[bold red]⚠️  Some issues detected.[/bold red]")
    
    except Exception as e:
        console.print(f"[red]✗[/red] Agent test failed: {e}")


def process_user_request(user_input: str):
    """Process natural language user request."""
    try:
        from oscar.core.agent import OSCARAgent
        
        # Create agent instance
        agent = OSCARAgent()
        
        # Process the request
        result = agent.process_request(user_input)
        
        # Display result summary
        if result["success"]:
            console.print(f"\n[bold green]✅ Request completed successfully![/bold green]")
        elif result["stage"] == "rejected":
            console.print(f"\n[yellow]⚠️  Plan was rejected by user[/yellow]")
        else:
            console.print(f"\n[red]❌ Request failed at {result['stage']} stage[/red]")
            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
    
    except Exception as e:
        console.print(f"[red]Error processing request: {e}[/red]")
        if settings.debug_mode:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()