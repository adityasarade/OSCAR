"""
OSCAR Agent Orchestrator - Simplified main agent logic

Role: Main orchestrator that manages the entire workflow

What it does:
- Takes the natural language request
- Coordinates with the LLM Planner to create a structured plan
- Runs safety checks
- Gets the confirmation
- Executes approved actions using tools
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from rich.console import Console

from oscar.core.planner import LLMPlanner, AgentPlan
from oscar.core.safety import analyze_and_confirm_plan
from oscar.config.settings import settings

console = Console()


class OSCARAgent:
    """
    Simplified OSCAR agent that orchestrates the workflow:
    Input → Planning → Safety → Confirmation → Execution
    """
    
    def __init__(self):
        self.planner = LLMPlanner()
        self.session_history: List[Dict[str, Any]] = []
        
        # Initialize tools
        self._init_tools()
        
        # Initialize audit logging
        self.audit_log_path = settings.data_dir / "logs" / "audit.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        console.print("[dim]OSCAR Agent initialized with tools ready[/dim]")
    
    def _init_tools(self):
        """Initialize and register all tools."""
        from oscar.tools.base import tool_registry, create_llm_client
        from oscar.tools.shell import ShellTool
        from oscar.tools.file_ops import FileOpsTool
        
        # Register basic tools
        tool_registry.register_tool(ShellTool())
        tool_registry.register_tool(FileOpsTool())
        
        # Register browser tool if Playwright is available
        try:
            from oscar.tools.browser import BrowserTool
            llm_client = create_llm_client()
            tool_registry.register_tool(BrowserTool(llm_client=llm_client))
        except ImportError:
            console.print("[yellow]Browser tool not available - install playwright[/yellow]")
        
        self.tools = tool_registry
    
    def process_request(self, user_input: str) -> Dict[str, Any]:
        """Process a complete user request through the pipeline."""
        
        result = {
            "user_input": user_input,
            "success": False,
            "stage": "input",
            "plan": None,
            "safety_report": None,
            "execution_result": None,
            "error": None
        }
        
        try:
            # Stage 1: Planning
            console.print("\n🧠 [bold blue]Planning...[/bold blue]")
            with console.status("[bold blue]Generating plan..."):
                result["stage"] = "planning"
                context = self._get_recent_context()
                plan = self.planner.create_plan(user_input, context)
                result["plan"] = plan
            
            console.print("[green]✓[/green] Plan generated successfully")
            
            # Stage 2: Safety Analysis & Confirmation
            # console.print("\n🛡️  [bold yellow]Safety Analysis...[/bold yellow]")
            result["stage"] = "safety"
            
            approved, safety_report = analyze_and_confirm_plan(plan)
            result["safety_report"] = safety_report
            
            if not approved:
                result["stage"] = "rejected"
                console.print("[yellow]⚠️  Plan rejected by user[/yellow]")
                self._log_interaction(result)
                return result
            
            console.print("[green]✓[/green] Plan approved by user")
            
            # Stage 3: Execution
            console.print("\n⚙️  [bold green]Executing...[/bold green]")
            result["stage"] = "execution"
            
            execution_result = self._execute_plan(plan)
            result["execution_result"] = execution_result
            
            if execution_result["success"]:
                result["success"] = True
                result["stage"] = "completed"
                console.print("[green]✓[/green] Execution completed successfully")
            else:
                result["stage"] = "execution_failed"
                console.print(f"[red]✗[/red] Execution failed: {execution_result.get('error')}")
            
        except Exception as e:
            result["error"] = str(e)
            result["stage"] = "error"
            console.print(f"[red]✗[/red] Error during {result['stage']}: {e}")
            
            if settings.debug_mode:
                import traceback
                traceback.print_exc()
        
        finally:
            # Log interaction and update history
            self._log_interaction(result)
            self._add_to_history(result)
        
        return result
    
    def _execute_plan(self, plan: AgentPlan) -> Dict[str, Any]:
        """Execute the approved plan using tools."""
        
        execution_result = {
            "success": False,
            "steps_completed": 0,
            "total_steps": len(plan.plan),
            "step_results": [],
            "error": None
        }
        
        try:
            # Dry-run mode simulation
            if settings.dry_run_mode:
                console.print("[yellow]🧪 DRY RUN MODE - Simulating execution[/yellow]")
                
                for step in plan.plan:
                    console.print(f"[dim]  Step {step.id}: {step.command} (simulated)[/dim]")
                    execution_result["step_results"].append({
                        "step_id": step.id,
                        "status": "simulated",
                        "output": f"[DRY RUN] Would execute: {step.command}"
                    })
                    execution_result["steps_completed"] += 1
                
                execution_result["success"] = True
                return execution_result
            
            # Real execution
            console.print("[green]🔧 Executing plan with tools...[/green]")
            
            for step in plan.plan:
                console.print(f"\n[blue]Step {step.id}:[/blue] {step.explanation}")
                console.print(f"[dim]Tool: {step.tool} | Command: {step.command}[/dim]")
                
                # Get appropriate tool
                tool = self.tools.get_tool(step.tool)
                if not tool:
                    tool = self.tools.suggest_tool_for_command(step.command)
                
                if not tool or not tool.is_available:
                    error_msg = f"Tool '{step.tool}' not available"
                    execution_result["step_results"].append({
                        "step_id": step.id,
                        "status": "failed",
                        "error": error_msg
                    })
                    execution_result["error"] = error_msg
                    break
                
                # Execute the step
                try:
                    with console.status(f"[green]Executing step {step.id}..."):
                        tool_result = tool.execute(step.command)
                    
                    # Display result
                    if tool_result.success:
                        console.print(f"[green]✓[/green] {tool_result.output}")
                    else:
                        console.print(f"[red]✗[/red] {tool_result.error}")
                    
                    # Store result
                    execution_result["step_results"].append({
                        "step_id": step.id,
                        "status": "success" if tool_result.success else "failed",
                        "output": tool_result.output,
                        "error": tool_result.error,
                        "execution_time": tool_result.execution_time
                    })
                    
                    if tool_result.success:
                        execution_result["steps_completed"] += 1
                    else:
                        execution_result["error"] = f"Step {step.id} failed: {tool_result.error}"
                        break
                        
                except Exception as e:
                    error_msg = f"Step {step.id} execution error: {str(e)}"
                    execution_result["step_results"].append({
                        "step_id": step.id,
                        "status": "error",
                        "error": error_msg
                    })
                    execution_result["error"] = error_msg
                    break
            
            # Determine overall success
            execution_result["success"] = (
                execution_result["steps_completed"] == execution_result["total_steps"]
                and execution_result["error"] is None
            )
            
        except Exception as e:
            execution_result["error"] = f"Execution engine error: {str(e)}"
            console.print(f"[red]Execution error: {e}[/red]")
        
        return execution_result
    
    def _get_recent_context(self) -> str:
        """Get context from recent interactions."""
        if not self.session_history:
            return "No previous interactions"
        
        recent = self.session_history[-3:]  # Last 3 interactions
        context_parts = []
        
        for interaction in recent:
            status = "completed" if interaction.get("success") else "failed"
            context_parts.append(f"- {interaction['user_input']}: {status}")
        
        return "Recent actions:\n" + "\n".join(context_parts)
    
    def _add_to_history(self, result: Dict[str, Any]) -> None:
        """Add interaction to session history."""
        self.session_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": result["user_input"],
            "success": result["success"],
            "stage": result["stage"]
        })
        
        # Keep only recent history (last 10 interactions)
        if len(self.session_history) > 10:
            self.session_history = self.session_history[-10:]
    
    def _log_interaction(self, result: Dict[str, Any]) -> None:
        """Log interaction to audit trail."""
        try:
            # Create simple audit entry
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_input": result["user_input"],
                "stage": result["stage"],
                "success": result["success"],
                "error": result.get("error")
            }
            
            # Add plan summary if available
            if result.get("plan"):
                audit_entry["plan_summary"] = {
                    "total_steps": len(result["plan"].plan),
                    "risk_level": result["plan"].risk_level
                }
            
            # Add execution summary if available
            if result.get("execution_result"):
                audit_entry["execution_summary"] = {
                    "steps_completed": result["execution_result"]["steps_completed"],
                    "total_steps": result["execution_result"]["total_steps"]
                }
            
            # Write to audit log
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry) + "\n")
                
        except Exception as e:
            console.print(f"[red]Warning: Failed to write audit log: {e}[/red]")
    
    def test_all_components(self) -> Dict[str, Any]:
        """Test all agent components."""
        test_results = {}
        
        # Test LLM Planner
        try:
            console.print("Testing LLM Planner...")
            planner_test = self.planner.test_connection()
            test_results["planner"] = {
                "status": "success" if planner_test["status"] == "success" else "error",
                "details": planner_test
            }
            console.print(f"[green]✓[/green] Planner: {planner_test['status']}")
        except Exception as e:
            test_results["planner"] = {"status": "error", "details": {"error": str(e)}}
            console.print(f"[red]✗[/red] Planner: {e}")
        
        # Test Tools
        try:
            console.print("Testing Available Tools...")
            available_tools = self.tools.get_available_tools()
            test_results["tools"] = {
                "status": "success" if available_tools else "error",
                "details": {"count": len(available_tools)}
            }
            console.print(f"[green]✓[/green] Tools: {len(available_tools)} available")
            for tool in available_tools:
                console.print(f"  • {tool.name}: {tool.description}")
        except Exception as e:
            test_results["tools"] = {"status": "error", "details": {"error": str(e)}}
            console.print(f"[red]✗[/red] Tools: {e}")
        
        # Test Configuration
        try:
            console.print("Testing Configuration...")
            test_results["configuration"] = {
                "status": "success",
                "details": {
                    "active_provider": settings.llm_config.active_provider,
                    "safe_mode": settings.safe_mode,
                    "dry_run": settings.dry_run_mode
                }
            }
            console.print("[green]✓[/green] Configuration: Valid")
        except Exception as e:
            test_results["configuration"] = {"status": "error", "details": {"error": str(e)}}
            console.print(f"[red]✗[/red] Configuration: {e}")
        
        # Overall status
        all_success = all(
            result["status"] == "success" 
            for result in test_results.values()
        )
        
        test_results["overall"] = {
            "status": "success" if all_success else "error",
            "ready": all_success
        }
        
        if all_success:
            console.print("\n[bold green]🎉 All components ready! OSCAR is fully operational.[/bold green]")
        else:
            console.print("\n[bold red]⚠️  Some components failed. Please check configuration.[/bold red]")
        
        return test_results


def create_agent() -> OSCARAgent:
    """Create and return a new OSCAR agent instance."""
    return OSCARAgent()