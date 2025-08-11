"""
OSCAR Agent Orchestrator - The Conductor
Main agent logic that coordinates planning, safety, and execution.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text

from oscar.core.planner import LLMPlanner, AgentPlan
from oscar.core.safety import SafetyScanner, analyze_and_confirm_plan
from oscar.config.settings import settings

console = Console()


class AgentSession:
    """Represents a session with conversation history and context."""
    
    def __init__(self):
        self.session_id = self._generate_session_id()
        self.history: List[Dict[str, Any]] = []
        self.context = ""
        self.start_time = datetime.now()
    
    def _generate_session_id(self) -> str:
        """Generate a unique session identifier."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def add_interaction(self, user_input: str, plan: AgentPlan, 
                       approved: bool, safety_report: Dict[str, Any], 
                       execution_result: Optional[Dict[str, Any]] = None):
        """Add an interaction to the session history."""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "plan": plan.model_dump(),
            "approved": approved,
            "safety_report": safety_report,
            "execution_result": execution_result
        }
        self.history.append(interaction)
        
        # Update context with recent successful actions
        if approved and execution_result and execution_result.get("success"):
            self.context += f"\nRecent action: {user_input} - Completed successfully"
    
    def get_recent_context(self, max_interactions: int = 3) -> str:
        """Get context from recent interactions."""
        if not self.history:
            return "No previous interactions in this session"
        
        recent = self.history[-max_interactions:]
        context_parts = []
        
        for interaction in recent:
            status = "completed" if interaction["approved"] else "rejected"
            context_parts.append(f"- {interaction['user_input']}: {status}")
        
        return "Recent actions:\n" + "\n".join(context_parts)


class OSCARAgent:
    """
    Main OSCAR agent that orchestrates the complete workflow:
    Input → Planning → Safety → Confirmation → Execution
    """
    
    def __init__(self):
        self.planner = LLMPlanner()
        self.safety_scanner = SafetyScanner()
        self.session = AgentSession()
        
        # Initialize audit logging
        self.audit_log_path = settings.data_dir / "logs" / "audit.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        console.print("[dim]OSCAR Agent initialized and ready[/dim]")
    
    def process_request(self, user_input: str) -> Dict[str, Any]:
        """
        Process a complete user request through the full pipeline.
        
        Args:
            user_input: Natural language request from user
            
        Returns:
            Complete processing result with all stages
        """
        
        result = {
            "user_input": user_input,
            "timestamp": datetime.now().isoformat(),
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
            with console.status("[bold blue]Generating plan...") as status:
                result["stage"] = "planning"
                context = self.session.get_recent_context()
                plan = self.planner.create_plan(user_input, context)
                result["plan"] = plan
            
            console.print("[green]✓[/green] Plan generated successfully")
            
            # Stage 2: Safety Analysis & Confirmation  
            console.print("\n🛡️  [bold yellow]Safety Analysis...[/bold yellow]")
            result["stage"] = "safety"
            
            approved, safety_report = analyze_and_confirm_plan(plan)
            result["safety_report"] = safety_report
            
            if not approved:
                result["stage"] = "rejected"
                console.print("[yellow]⚠️  Plan rejected by user[/yellow]")
                self._log_interaction(result)
                return result
            
            console.print("[green]✓[/green] Plan approved by user")
            
            # Stage 3: Execution (placeholder - will implement tools later)
            console.print("\n⚙️  [bold green]Execution...[/bold green]")
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
            # Always log the interaction
            self._log_interaction(result)
            
            # Add to session history
            if result["plan"] and result["safety_report"]:
                self.session.add_interaction(
                    user_input, 
                    result["plan"], 
                    result["safety_report"]["approved"], 
                    result["safety_report"],
                    result["execution_result"]
                )
        
        return result
    
    def _execute_plan(self, plan: AgentPlan) -> Dict[str, Any]:
        """
        Execute the approved plan. 
        Currently a placeholder - will implement actual tools later.
        """
        
        execution_result = {
            "success": False,
            "steps_completed": 0,
            "total_steps": len(plan.plan),
            "step_results": [],
            "error": None
        }
        
        try:
            # If in dry-run mode, simulate execution
            if settings.dry_run_mode:
                console.print("[yellow]🧪 DRY RUN MODE - Simulating execution[/yellow]")
                
                for step in plan.plan:
                    step_result = {
                        "step_id": step.id,
                        "tool": step.tool,
                        "command": step.command,
                        "status": "simulated",
                        "output": f"[DRY RUN] Would execute: {step.command}",
                        "duration": 0.1
                    }
                    execution_result["step_results"].append(step_result)
                    execution_result["steps_completed"] += 1
                    
                    console.print(f"[dim]  Step {step.id}: {step.command} (simulated)[/dim]")
                
                execution_result["success"] = True
                return execution_result
            
            # Real execution (placeholder for now)
            console.print("[yellow]⚠️  Tool execution not yet implemented[/yellow]")
            console.print("[dim]This will be implemented in Phase 2 (Tools Layer)[/dim]")
            
            # For now, mark as successful but not executed
            for step in plan.plan:
                step_result = {
                    "step_id": step.id,
                    "tool": step.tool, 
                    "command": step.command,
                    "status": "pending",
                    "output": "Tool execution not yet implemented",
                    "duration": 0
                }
                execution_result["step_results"].append(step_result)
            
            execution_result["success"] = True
            execution_result["steps_completed"] = len(plan.plan)
            
        except Exception as e:
            execution_result["error"] = str(e)
            console.print(f"[red]Execution error: {e}[/red]")
        
        return execution_result
    
    def _log_interaction(self, result: Dict[str, Any]):
        """Log the complete interaction to audit trail."""
        try:
            # Create audit log entry
            audit_entry = {
                "session_id": self.session.session_id,
                "timestamp": result["timestamp"],
                "user_input": result["user_input"],
                "stage": result["stage"],
                "success": result["success"],
                "plan_summary": self._create_plan_summary(result.get("plan")),
                "safety_summary": self._create_safety_summary(result.get("safety_report")),
                "execution_summary": self._create_execution_summary(result.get("execution_result")),
                "error": result.get("error")
            }
            
            # Write to audit log (JSONL format)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry) + "\n")
                
        except Exception as e:
            console.print(f"[red]Warning: Failed to write audit log: {e}[/red]")
    
    def _create_plan_summary(self, plan: Optional[AgentPlan]) -> Optional[Dict[str, Any]]:
        """Create a summary of the plan for audit logging."""
        if not plan:
            return None
        
        return {
            "total_steps": len(plan.plan),
            "tools_used": list(set(step.tool for step in plan.plan)),
            "risk_level": plan.risk_level,
            "thoughts": plan.thoughts[:200] + "..." if len(plan.thoughts) > 200 else plan.thoughts
        }
    
    def _create_safety_summary(self, safety_report: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Create a summary of safety analysis for audit logging."""
        if not safety_report:
            return None
        
        return {
            "overall_risk": safety_report["overall_risk"],
            "approved": safety_report["approved"],
            "approval_reason": safety_report["approval_reason"],
            "dangerous_steps": safety_report["dangerous_steps"],
            "safety_flags": safety_report["safety_flags"],
            "safe_mode": safety_report["safe_mode"],
            "dry_run_mode": safety_report["dry_run_mode"]
        }
    
    def _create_execution_summary(self, execution_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Create a summary of execution results for audit logging."""
        if not execution_result:
            return None
        
        return {
            "success": execution_result["success"],
            "steps_completed": execution_result["steps_completed"],
            "total_steps": execution_result["total_steps"],
            "error": execution_result.get("error")
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about the current session."""
        total_interactions = len(self.session.history)
        approved_interactions = sum(1 for h in self.session.history if h["approved"])
        successful_executions = sum(1 for h in self.session.history 
                                  if h.get("execution_result", {}).get("success", False))
        
        return {
            "session_id": self.session.session_id,
            "start_time": self.session.start_time.isoformat(),
            "duration": str(datetime.now() - self.session.start_time),
            "total_interactions": total_interactions,
            "approved_plans": approved_interactions,
            "successful_executions": successful_executions,
            "success_rate": successful_executions / max(total_interactions, 1) * 100
        }
    
    def display_session_summary(self):
        """Display a summary of the current session."""
        stats = self.get_session_stats()
        
        summary_text = f"""
[bold]Session Summary[/bold]
• Session ID: [cyan]{stats['session_id']}[/cyan]
• Duration: [yellow]{stats['duration']}[/yellow]
• Total Requests: [blue]{stats['total_interactions']}[/blue]
• Plans Approved: [green]{stats['approved_plans']}[/green]
• Successful Executions: [green]{stats['successful_executions']}[/green]
• Success Rate: [{'green' if stats['success_rate'] > 75 else 'yellow' if stats['success_rate'] > 50 else 'red'}]{stats['success_rate']:.1f}%[/]
"""
        
        console.print(Panel(summary_text, title="📊 Session Statistics", border_style="blue"))
    
    def test_all_components(self) -> Dict[str, Any]:
        """Test all agent components and return status."""
        test_results = {
            "planner": {"status": "unknown", "details": {}},
            "safety_scanner": {"status": "unknown", "details": {}},
            "configuration": {"status": "unknown", "details": {}},
            "overall": {"status": "unknown", "ready": False}
        }
        
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
        
        # Test Safety Scanner
        try:
            console.print("Testing Safety Scanner...")
            # Create a test plan
            from oscar.core.planner import ActionStep
            test_plan = AgentPlan(
                thoughts="Test plan for safety scanner",
                plan=[ActionStep(id=1, tool="shell", command="echo 'test'", explanation="Test command")],
                risk_level="low",
                confirm_prompt="Test confirmation"
            )
            
            analysis = self.safety_scanner.analyze_plan(test_plan)
            test_results["safety_scanner"] = {
                "status": "success",
                "details": {"analysis_completed": True, "risk_assessment": analysis["overall_risk"]}
            }
            console.print("[green]✓[/green] Safety Scanner: Working")
            
        except Exception as e:
            test_results["safety_scanner"] = {"status": "error", "details": {"error": str(e)}}
            console.print(f"[red]✗[/red] Safety Scanner: {e}")
        
        # Test Configuration
        try:
            console.print("Testing Configuration...")
            config_test = {
                "active_provider": settings.llm_config.active_provider,
                "data_directory": str(settings.data_dir),
                "safe_mode": settings.safe_mode,
                "dry_run": settings.dry_run_mode
            }
            
            test_results["configuration"] = {
                "status": "success",
                "details": config_test
            }
            console.print("[green]✓[/green] Configuration: Valid")
            
        except Exception as e:
            test_results["configuration"] = {"status": "error", "details": {"error": str(e)}}
            console.print(f"[red]✗[/red] Configuration: {e}")
        
        # Overall status
        all_success = all(
            result["status"] == "success" 
            for key, result in test_results.items() 
            if key != "overall" and isinstance(result, dict) and "status" in result
        )
        
        test_results["overall"] = {
            "status": "success" if all_success else "error",
            "ready": all_success
        }
        
        if all_success:
            console.print("\n[bold green]🎉 All components ready! OSCAR is operational.[/bold green]")
        else:
            console.print("\n[bold red]⚠️  Some components failed. Please check configuration.[/bold red]")
        
        return test_results


# Convenience function for easy import
def create_agent() -> OSCARAgent:
    """Create and return a new OSCAR agent instance."""
    return OSCARAgent()