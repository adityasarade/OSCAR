"""
OSCAR Safety Scanner - The Guardian
Provides safety checks, risk assessment, and human confirmation workflows.
"""

import re
import getpass
from typing import List, Dict, Any, Tuple
from enum import Enum
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.text import Text

from oscar.core.planner import AgentPlan, ActionStep
from oscar.config.settings import settings

console = Console()


class RiskLevel(Enum):
    """Risk level enumeration with colors."""
    LOW = ("low", "green")
    MEDIUM = ("medium", "yellow") 
    HIGH = ("high", "orange")
    DANGEROUS = ("dangerous", "red")
    
    def __init__(self, level: str, color: str):
        self.level = level
        self.color = color


class SafetyScanner:
    """
    Safety scanner that analyzes plans for dangerous operations
    and manages human-in-the-loop confirmation workflows.
    """
    
    def __init__(self):
        self.safety_config = settings.llm_config.safety
        self.safe_mode = settings.safe_mode
        self.dry_run_mode = settings.dry_run_mode
        
        # Risk level mapping
        self.risk_levels = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "dangerous": RiskLevel.DANGEROUS
        }
    
    def analyze_plan(self, plan: AgentPlan) -> Dict[str, Any]:
        """
        Analyze a complete plan for safety concerns.
        
        Args:
            plan: The agent plan to analyze
            
        Returns:
            Analysis results with recommendations
        """
        analysis = {
            "overall_risk": plan.risk_level,
            "step_analysis": [],
            "safety_flags": [],
            "recommendations": [],
            "requires_admin": False,
            "dangerous_steps": []
        }
        
        for step in plan.plan:
            step_analysis = self._analyze_step(step)
            analysis["step_analysis"].append(step_analysis)
            
            # Collect safety flags
            if step_analysis["flags"]:
                analysis["safety_flags"].extend(step_analysis["flags"])
            
            # Track dangerous steps
            if step_analysis["risk_level"] in ["high", "dangerous"]:
                analysis["dangerous_steps"].append(step.id)
            
            # Check if admin privileges are required
            if step_analysis["requires_admin"]:
                analysis["requires_admin"] = True
        
        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _analyze_step(self, step: ActionStep) -> Dict[str, Any]:
        """Analyze a single step for safety concerns."""
        command = step.command.lower()
        
        step_analysis = {
            "step_id": step.id,
            "risk_level": step.risk_level,
            "flags": [],
            "requires_admin": False,
            "patterns_matched": []
        }
        
        # Check dangerous patterns
        for pattern in self.safety_config.dangerous_patterns:
            if re.search(pattern, step.command, re.IGNORECASE):
                step_analysis["flags"].append(f"Dangerous pattern: {pattern}")
                step_analysis["patterns_matched"].append(pattern)
        
        # Check for admin requirements
        admin_indicators = ["sudo", "administrator", "runas", "privilege", "admin"]
        for indicator in admin_indicators:
            if indicator in command:
                step_analysis["requires_admin"] = True
                step_analysis["flags"].append("Requires administrative privileges")
                break
        
        # Check for system file access
        system_paths = ["/system", "/boot", "c:\\windows", "system32", "/etc", "/usr/bin"]
        for path in system_paths:
            if path.lower() in command:
                step_analysis["flags"].append(f"Accesses system directory: {path}")
        
        # Check for network operations
        network_indicators = ["curl", "wget", "download", "upload", "http", "ftp"]
        for indicator in network_indicators:
            if indicator in command:
                step_analysis["flags"].append("Network operation detected")
                break
        
        return step_analysis
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate safety recommendations based on analysis."""
        recommendations = []
        
        if analysis["overall_risk"] == "dangerous":
            recommendations.append("⚠️  DANGER: This plan contains potentially destructive operations")
            recommendations.append("🛡️  Consider running in dry-run mode first")
            recommendations.append("💾  Ensure you have recent backups")
        
        elif analysis["overall_risk"] == "high":
            recommendations.append("⚠️  HIGH RISK: This plan modifies system settings")
            recommendations.append("🔍  Review each step carefully before approval")
        
        if analysis["requires_admin"]:
            recommendations.append("🔑  Administrative privileges required")
        
        if len(analysis["dangerous_steps"]) > 0:
            recommendations.append(f"🚨  {len(analysis['dangerous_steps'])} steps require extra confirmation")
        
        if self.dry_run_mode:
            recommendations.append("🧪  DRY RUN MODE: No actual changes will be made")
        
        return recommendations
    
    def display_plan(self, plan: AgentPlan, analysis: Dict[str, Any]) -> None:
        """Display the plan with safety analysis in a beautiful format."""
        
        # Main plan panel
        plan_title = Text()
        plan_title.append("📋 Execution Plan", style="bold blue")
        
        risk_level = self.risk_levels[analysis["overall_risk"]]
        plan_title.append(f" (Risk: {risk_level.level.upper()})", style=f"bold {risk_level.color}")
        
        console.print(Panel(plan_title, border_style=risk_level.color))
        
        # LLM thoughts
        console.print(f"\n🤔 [bold]Agent Reasoning:[/bold]\n{plan.thoughts}\n")
        
        # Steps table
        table = Table(title="Action Steps", show_header=True, header_style="bold blue")
        table.add_column("ID", width=3)
        table.add_column("Tool", width=10)
        table.add_column("Command", width=40)
        table.add_column("Risk", width=8)
        table.add_column("Explanation", width=30)
        
        for i, step in enumerate(plan.plan):
            step_analysis = analysis["step_analysis"][i]
            risk_color = self.risk_levels[step_analysis["risk_level"]].color
            
            # Add warning emoji for high-risk steps
            risk_display = step_analysis["risk_level"].upper()
            if step_analysis["risk_level"] in ["high", "dangerous"]:
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
        
        # Recommendations
        if analysis["recommendations"]:
            console.print("\n💡 [bold yellow]Recommendations:[/bold yellow]")
            for rec in analysis["recommendations"]:
                console.print(f"  {rec}")
        
        console.print()
    
    def get_user_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Get user confirmation for plan execution.
        
        Returns:
            Tuple of (approved, reason)
        """
        
        # Display the plan
        self.display_plan(plan, analysis)
        
        # Different confirmation levels based on risk
        if analysis["overall_risk"] == "dangerous":
            return self._get_dangerous_confirmation(plan, analysis)
        elif analysis["overall_risk"] == "high":
            return self._get_high_risk_confirmation(plan, analysis)
        else:
            return self._get_standard_confirmation(plan, analysis)
    
    def _get_standard_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """Standard confirmation for low/medium risk plans."""
        
        # Show what will happen
        if self.dry_run_mode:
            console.print("[yellow]DRY RUN MODE: Commands will be simulated, not executed[/yellow]")
        
        # Simple yes/no confirmation
        approved = Confirm.ask(
            f"\n{plan.confirm_prompt}",
            default=False
        )
        
        reason = "User approved" if approved else "User rejected"
        return approved, reason
    
    def _get_high_risk_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """Enhanced confirmation for high-risk plans."""
        
        console.print("\n[bold yellow]⚠️  HIGH RISK OPERATION DETECTED[/bold yellow]")
        console.print("This plan will make significant system changes.")
        
        if not self.dry_run_mode:
            console.print("[red]⚠️  This will make REAL changes to your system![/red]")
        
        # Step-by-step confirmation for dangerous steps
        for step_id in analysis["dangerous_steps"]:
            step = next(s for s in plan.plan if s.id == step_id)
            step_approved = Confirm.ask(
                f"\nApprove step {step_id}: {step.command}?",
                default=False
            )
            if not step_approved:
                return False, f"User rejected step {step_id}"
        
        # Final confirmation
        final_approval = Confirm.ask(
            f"\n[bold]{plan.confirm_prompt}[/bold]",
            default=False
        )
        
        reason = "User approved high-risk plan" if final_approval else "User rejected final confirmation"
        return final_approval, reason
    
    def _get_dangerous_confirmation(self, plan: AgentPlan, analysis: Dict[str, Any]) -> Tuple[bool, str]:
        """Maximum security confirmation for dangerous plans."""
        
        console.print("\n[bold red]🚨 DANGEROUS OPERATION DETECTED 🚨[/bold red]")
        console.print("[red]This plan contains potentially destructive commands![/red]")
        
        if not self.dry_run_mode:
            console.print("\n[bold red]⚠️  WARNING: This will make IRREVERSIBLE changes![/bold red]")
            console.print("[yellow]Consider enabling dry-run mode first: oscar --dry-run[/yellow]")
        
        # Require typing "CONFIRM" for dangerous operations
        confirmation_word = Prompt.ask(
            "\n[bold]Type 'CONFIRM' to proceed with dangerous operation",
            default=""
        )
        
        if confirmation_word != "CONFIRM":
            return False, "User failed to type CONFIRM"
        
        # Additional admin password check in safe mode
        if self.safe_mode and not self.dry_run_mode:
            console.print("\n[yellow]Safe mode requires password verification for dangerous operations[/yellow]")
            try:
                password = getpass.getpass("Enter your system password: ")
                if not password:
                    return False, "No password provided"
            except KeyboardInterrupt:
                return False, "Password entry cancelled"
        
        # Final confirmation with explicit acknowledgment
        final_confirmation = Confirm.ask(
            "\n[bold red]I understand this is dangerous and irreversible. Proceed?[/bold red]",
            default=False
        )
        
        reason = "User confirmed dangerous operation" if final_confirmation else "User rejected dangerous operation"
        return final_confirmation, reason
    
    def create_safety_report(self, plan: AgentPlan, analysis: Dict[str, Any], approved: bool, reason: str) -> Dict[str, Any]:
        """Create a comprehensive safety report for audit logs."""
        
        return {
            "timestamp": self._get_timestamp(),
            "plan_id": hash(str(plan.plan)),  # Simple plan identifier
            "overall_risk": analysis["overall_risk"],
            "total_steps": len(plan.plan),
            "dangerous_steps": len(analysis["dangerous_steps"]),
            "safety_flags": len(analysis["safety_flags"]),
            "requires_admin": analysis["requires_admin"],
            "approved": approved,
            "approval_reason": reason,
            "dry_run_mode": self.dry_run_mode,
            "safe_mode": self.safe_mode,
            "flags": analysis["safety_flags"],
            "recommendations": analysis["recommendations"]
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()


# Convenience functions for easy import
def analyze_and_confirm_plan(plan: AgentPlan) -> Tuple[bool, Dict[str, Any]]:
    """
    Convenience function to analyze a plan and get user confirmation.
    
    Returns:
        Tuple of (approved, safety_report)
    """
    scanner = SafetyScanner()
    analysis = scanner.analyze_plan(plan)
    approved, reason = scanner.get_user_confirmation(plan, analysis)
    safety_report = scanner.create_safety_report(plan, analysis, approved, reason)
    
    return approved, safety_report