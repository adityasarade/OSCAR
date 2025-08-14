"""
OSCAR Safety Scanner - Simplified safety analysis and confirmation
"""

import re
import getpass
from typing import Dict, Any, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.text import Text

from oscar.core.planner import AgentPlan, ActionStep
from oscar.config.settings import settings, SAFETY_PATTERNS

console = Console()


class SafetyScanner:
    """Simplified safety scanner with human confirmation workflows."""
    
    def __init__(self):
        self.safe_mode = settings.safe_mode
        self.dry_run_mode = settings.dry_run_mode
        
        # Risk level colors
        self.risk_colors = {
            "low": "green",
            "medium": "yellow", 
            "high": "orange",
            "dangerous": "red"
        }
    
    def analyze_plan(self, plan: AgentPlan) -> Dict[str, Any]:
        """Analyze a plan for safety concerns."""
        analysis = {
            "overall_risk": plan.risk_level,
            "dangerous_steps": [],
            "safety_flags": [],
            "requires_admin": False
        }
        
        for step in plan.plan:
            step_flags = self._analyze_step(step)
            
            if step_flags:
                analysis["safety_flags"].extend(step_flags)
                
            if step.risk_level in ["high", "dangerous"]:
                analysis["dangerous_steps"].append(step.id)
                
            if self._requires_admin(step.command):
                analysis["requires_admin"] = True
        
        return analysis
    
    def _analyze_step(self, step: ActionStep) -> list[str]:
        """Analyze a single step and return safety flags."""
        flags = []
        command = step.command.lower()
        
        # Check dangerous patterns
        for pattern in SAFETY_PATTERNS["dangerous_commands"]:
            if re.search(pattern, step.command, re.IGNORECASE):
                flags.append(f"Dangerous pattern detected in step {step.id}")
                break
        
        # Check for admin requirements
        if self._requires_admin(command):
            flags.append(f"Step {step.id} requires administrative privileges")
        
        # Check for system paths
        system_paths = ["/system", "/boot", "c:\\windows", "system32", "/etc"]
        for path in system_paths:
            if path.lower() in command:
                flags.append(f"Step {step.id} accesses system directory")
                break
        
        return flags
    
    def _requires_admin(self, command: str) -> bool:
        """Check if command requires admin privileges."""
        admin_indicators = ["sudo", "administrator", "runas", "admin"]
        return any(indicator in command.lower() for indicator in admin_indicators)
    
    def display_plan(self, plan: AgentPlan, analysis: Dict[str, Any]) -> None:
        """Display the plan with safety analysis."""
        # Plan title with risk level
        risk_color = self.risk_colors[analysis["overall_risk"]]
        title_text = Text()
        title_text.append("📋 Execution Plan", style="bold blue")
        title_text.append(f" (Risk: {analysis['overall_risk'].upper()})", style=f"bold {risk_color}")
        
        console.print(Panel(title_text, border_style=risk_color))
        
        # Agent reasoning
        console.print(f"\n🤔 [bold]Agent Reasoning:[/bold]\n{plan.thoughts}\n")
        
        # Steps table
        table = Table(title="Action Steps", show_header=True, header_style="bold blue")
        table.add_column("ID", width=3)
        table.add_column("Tool", width=10)
        table.add_column("Command", width=40)
        table.add_column("Risk", width=8)
        table.add_column("Explanation", width=30)
        
        for step in plan.plan:
            risk_color = self.risk_colors[step.risk_level]
            risk_display = step.risk_level.upper()
            
            if step.risk_level in ["high", "dangerous"]:
                risk_display = f"⚠️  {risk_display}"
            
            table.add_row(
                str(step.id),
                step.tool,
                step.command,
                f"[{risk_color}]{risk_display}[/{risk_color}]",
                step.explanation
            )
        
        console.print(table)
        
        # Safety flags
        if analysis["safety_flags"]:
            console.print("\n🚨 [bold red]Safety Flags:[/bold red]")
            for flag in analysis["safety_flags"]:
                console.print(f"  • {flag}")
        
        # Simple recommendations
        if analysis["overall_risk"] == "dangerous":
            console.print("\n⚠️  [bold red]DANGER: This plan contains potentially destructive operations[/bold red]")
        elif analysis["overall_risk"] == "high":
            console.print("\n⚠️  [bold yellow]HIGH RISK: Review each step carefully[/bold yellow]")
        
        if analysis["requires_admin"]:
            console.print("🔑  Administrative privileges required")
        
        if self.dry_run_mode:
            console.print("🧪  [yellow]DRY RUN MODE: No actual changes will be made[/yellow]")
        
        console.print()
    
    def get_user_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """Get user confirmation based on risk level."""
        # Display the plan
        self.display_plan(plan, analysis)
        
        # Route to appropriate confirmation level
        if analysis["overall_risk"] == "dangerous":
            return self._get_dangerous_confirmation(plan)
        elif analysis["overall_risk"] == "high":
            return self._get_high_risk_confirmation(plan, analysis)
        else:
            return self._get_standard_confirmation(plan)
    
    def _get_standard_confirmation(self, plan: AgentPlan) -> Tuple[bool, str]:
        """Standard confirmation for low/medium risk."""
        if self.dry_run_mode:
            console.print("[yellow]DRY RUN MODE: Commands will be simulated[/yellow]")
        
        approved = Confirm.ask(f"\n{plan.confirm_prompt}", default=False)
        return approved, "User approved" if approved else "User rejected"
    
    def _get_high_risk_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """Enhanced confirmation for high-risk plans."""
        console.print("\n[bold yellow]⚠️  HIGH RISK OPERATION[/bold yellow]")
        
        if not self.dry_run_mode:
            console.print("[red]This will make REAL changes to your system![/red]")
        
        # Confirm dangerous steps individually
        for step_id in analysis["dangerous_steps"]:
            step = next(s for s in plan.plan if s.id == step_id)
            step_approved = Confirm.ask(f"\nApprove step {step_id}: {step.command}?", default=False)
            if not step_approved:
                return False, f"User rejected step {step_id}"
        
        # Final confirmation
        final_approved = Confirm.ask(f"\n[bold]{plan.confirm_prompt}[/bold]", default=False)
        return final_approved, "User approved high-risk plan" if final_approved else "User rejected"
    
    def _get_dangerous_confirmation(self, plan: AgentPlan) -> Tuple[bool, str]:
        """Maximum security confirmation for dangerous operations."""
        console.print("\n[bold red]🚨 DANGEROUS OPERATION DETECTED 🚨[/bold red]")
        console.print("[red]This plan contains potentially destructive commands![/red]")
        
        if not self.dry_run_mode:
            console.print("\n[bold red]⚠️  WARNING: This will make IRREVERSIBLE changes![/bold red]")
        
        # Require typing "CONFIRM"
        confirmation_word = Prompt.ask(
            "\n[bold]Type 'CONFIRM' to proceed with dangerous operation",
            default=""
        )
        
        if confirmation_word != "CONFIRM":
            return False, "User failed to type CONFIRM"
        
        # Additional password check in safe mode
        if self.safe_mode and not self.dry_run_mode:
            console.print("\n[yellow]Safe mode requires password verification[/yellow]")
            try:
                password = getpass.getpass("Enter your system password: ")
                if not password:
                    return False, "No password provided"
            except KeyboardInterrupt:
                return False, "Password entry cancelled"
        
        # Final confirmation
        final_confirmed = Confirm.ask(
            "\n[bold red]I understand this is dangerous and irreversible. Proceed?[/bold red]",
            default=False
        )
        
        return final_confirmed, "User confirmed dangerous operation" if final_confirmed else "User rejected"
    
    def create_safety_report(self, plan: AgentPlan, analysis: Dict[str, Any], 
                           approved: bool, reason: str) -> Dict[str, Any]:
        """Create a simple safety report for audit logs."""
        return {
            "overall_risk": analysis["overall_risk"],
            "total_steps": len(plan.plan),
            "dangerous_steps": len(analysis["dangerous_steps"]),
            "approved": approved,
            "approval_reason": reason,
            "dry_run_mode": self.dry_run_mode,
            "safety_flags": analysis["safety_flags"]
        }


def analyze_and_confirm_plan(plan: AgentPlan) -> Tuple[bool, Dict[str, Any]]:
    """Convenience function to analyze and confirm a plan."""
    scanner = SafetyScanner()
    analysis = scanner.analyze_plan(plan)
    approved, reason = scanner.get_user_confirmation(plan, analysis)
    safety_report = scanner.create_safety_report(plan, analysis, approved, reason)
    
    return approved, safety_report