"""
OSCAR CLI - Main entry point for the Operating System's Complete Agentic Rex
"""

import click
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from oscar.config.settings import settings

console = Console()

def display_welcome():
    """Display welcome message and system info."""
    welcome_text = Text()
    welcome_text.append("🤖 OSCAR ", style="bold blue")
    welcome_text.append("- Operating System's Complete Agentic Rex", style="white")
    
    panel = Panel(
        welcome_text,
        title="Welcome",
        border_style="blue",
        padding=(1, 2)
    )
    console.print(panel)
    
    # Display current configuration
    active_provider = settings.llm_config.active_provider
    active_config = settings.get_active_llm_config()
    
    config_info = f"""
[bold]Current Configuration:[/bold]
• LLM Provider: [green]{active_provider}[/green]
• Model: [cyan]{active_config.model}[/cyan]
• Safe Mode: [{'green' if settings.safe_mode else 'red'}]{settings.safe_mode}[/]
• Debug Mode: [{'yellow' if settings.debug_mode else 'dim'}]{settings.debug_mode}[/]
• Data Directory: [dim]{settings.data_dir}[/dim]
"""
    
    console.print(config_info)

def display_help():
    """Display available commands."""
    help_text = """
[bold]Available Commands:[/bold]
• [cyan]help[/cyan] or [cyan]?[/cyan] - Show this help message
• [cyan]config[/cyan] - Show current configuration
• [cyan]status[/cyan] - Check system status
• [cyan]test[/cyan] - Test LLM connection
• [cyan]test-agent[/cyan] - Test full agent components
• [cyan]session[/cyan] - Show current session info
• [cyan]quit[/cyan] or [cyan]exit[/cyan] - Exit OSCAR

[bold]Natural Language Usage:[/bold]
• Just type your request in plain English
• Examples:
  - "Create a new Python project"
  - "Download the latest Python installer"
  - "Clean up my Downloads folder"
  - "Show me system information"

[bold]Safety Features:[/bold]
• All actions require explicit confirmation
• Dangerous commands are flagged and require extra confirmation
• Dry-run mode available for testing (use --dry-run flag)
• Complete audit trail of all actions
"""
    console.print(help_text)

@click.command()
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--dry-run', is_flag=True, help='Enable dry-run mode (no actual execution)')
@click.option('--config-check', is_flag=True, help='Check configuration and exit')
def main(debug, dry_run, config_check):
    """
    OSCAR - Operating System's Complete Agentic Rex
    
    An intelligent agent for safe system automation through natural language.
    """
    
    # Override environment settings if flags are provided
    if debug:
        os.environ['OSCAR_DEBUG'] = 'true'
    if dry_run:
        os.environ['OSCAR_DRY_RUN'] = 'true'
    
    try:
        # Test configuration loading
        if config_check:
            console.print("[green]✓[/green] Configuration loaded successfully")
            console.print(f"[green]✓[/green] Active LLM: {settings.llm_config.active_provider}")
            console.print(f"[green]✓[/green] Data directory: {settings.data_dir}")
            
            # Test API key
            try:
                api_key = settings.get_api_key(settings.llm_config.active_provider)
                console.print(f"[green]✓[/green] API key found for {settings.llm_config.active_provider}")
            except ValueError as e:
                console.print(f"[red]✗[/red] {e}")
                return
            
            console.print("[bold green]Configuration check passed![/bold green]")
            return
        
        # Start main CLI loop
        display_welcome()
        
        console.print("\n[dim]Type 'help' for available commands or start with your request...[/dim]\n")
        
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
                    show_config_details()
                    
                elif user_input.lower() == 'status':
                    show_system_status()
                    
                elif user_input.lower() == 'test':
                    test_llm_connection()
                    
                elif user_input.lower() == 'test-agent':
                    test_full_agent()
                    
                elif user_input.lower() == 'session':
                    show_session_info()
                    
                else:
                    # Process natural language input through OSCAR agent
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

def show_config_details():
    """Show detailed configuration information."""
    active_provider = settings.llm_config.active_provider
    active_config = settings.get_active_llm_config()
    
    config_details = f"""
[bold]Detailed Configuration:[/bold]

[bold]LLM Settings:[/bold]
• Provider: [green]{active_provider}[/green]
• Model: [cyan]{active_config.model}[/cyan]
• Max Tokens: [yellow]{active_config.max_tokens}[/yellow]
• Temperature: [yellow]{active_config.temperature}[/yellow]
• Timeout: [yellow]{active_config.timeout}s[/yellow]

[bold]System Settings:[/bold]
• Safe Mode: [{'green' if settings.safe_mode else 'red'}]{settings.safe_mode}[/]
• Debug Mode: [{'yellow' if settings.debug_mode else 'dim'}]{settings.debug_mode}[/]
• Dry Run: [{'yellow' if settings.dry_run_mode else 'dim'}]{settings.dry_run_mode}[/]
• Log Level: [yellow]{settings.log_level}[/yellow]

[bold]Directories:[/bold]
• Data: [dim]{settings.data_dir}[/dim]
• Config: [dim]{settings.config_dir}[/dim]
"""
    console.print(config_details)

def show_system_status():
    """Show system status and health checks."""
    console.print("[bold]System Status Check:[/bold]\n")
    
    # Check API key
    try:
        api_key = settings.get_api_key(settings.llm_config.active_provider)
        console.print("[green]✓[/green] API key configured")
    except ValueError:
        console.print("[red]✗[/red] API key missing")
    
    # Check directories
    required_dirs = [
        settings.data_dir,
        settings.data_dir / "models",
        settings.data_dir / "memory", 
        settings.data_dir / "logs"
    ]
    
    for dir_path in required_dirs:
        if dir_path.exists():
            console.print(f"[green]✓[/green] Directory exists: {dir_path}")
        else:
            console.print(f"[red]✗[/red] Directory missing: {dir_path}")

def test_llm_connection():
    """Test connection to the LLM provider."""
    console.print("[yellow]Testing LLM connection...[/yellow]")
    
    try:
        from groq import Groq
        
        # Get API key
        api_key = settings.get_api_key(settings.llm_config.active_provider)
        active_config = settings.get_active_llm_config()
        
        # Create client
        client = Groq(api_key=api_key)
        
        # Test simple completion
        completion = client.chat.completions.create(
            model=active_config.model,
            messages=[{"role": "user", "content": "Hello, respond with just 'OSCAR connection test successful'"}],
            max_tokens=50,
            temperature=0.1
        )
        
        response = completion.choices[0].message.content
        console.print(f"[green]✓[/green] LLM Response: {response}")
        
    except Exception as e:
        console.print(f"[red]✗[/red] LLM connection failed: {e}")

def test_full_agent():
    """Test all agent components."""
    console.print("[bold blue]🧪 Testing OSCAR Agent Components...[/bold blue]\n")
    
    try:
        from oscar.core.agent import OSCARAgent
        agent = OSCARAgent()
        test_results = agent.test_all_components()
        
        if test_results["overall"]["ready"]:
            console.print("\n[bold green]🎉 OSCAR is ready for natural language requests![/bold green]")
        else:
            console.print("\n[bold red]⚠️  Some issues detected. Check configuration.[/bold red]")
            
    except Exception as e:
        console.print(f"[red]✗[/red] Agent test failed: {e}")

def show_session_info():
    """Show current session information."""
    try:
        # This would typically come from a global agent instance
        console.print("[dim]Session info coming soon...[/dim]")
        console.print("Current session: Local CLI session")
        console.print(f"Started: Just now")
        console.print("Commands processed: 0")
        
    except Exception as e:
        console.print(f"[red]Error getting session info: {e}[/red]")

def process_user_request(user_input: str):
    """Process natural language user request through OSCAR agent."""
    try:
        from oscar.core.agent import OSCARAgent
        
        # Create agent instance (in real app, this would be persistent)
        agent = OSCARAgent()
        
        # Process the request
        result = agent.process_request(user_input)
        
        # Display results summary
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