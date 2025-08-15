"""
OSCAR Configuration Management
Simplified configuration loading and validation.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    base_url: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.1
    timeout: int = 30


class LLMConfig(BaseModel):
    """Complete LLM configuration."""
    active_provider: str
    providers: Dict[str, LLMProviderConfig]
    system_prompt: str
    planning_template: str


class OSCARSettings:
    """Main configuration class for OSCAR."""
    
    def __init__(self):
        # Project structure: src/oscar/config/settings.py
        self.config_dir = Path(__file__).parent
        self.project_root = self.config_dir.parent.parent.parent
        self.data_dir = Path(os.getenv("OSCAR_DATA_DIR", "./data"))
        
        # Ensure data directories exist
        self._create_data_dirs()
        
        # Load LLM configuration
        self.llm_config = self._load_llm_config()
    
    def _create_data_dirs(self):
        """Create required data directories."""
        for subdir in ["models", "memory", "logs", "downloads"]:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    def _load_llm_config(self) -> LLMConfig:
        """Load LLM configuration from YAML file."""
        config_path = self.config_dir / "llm_config.yaml"
        
        if not config_path.exists():
            self._create_default_config(config_path)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        return LLMConfig(**config_data)
    
    def _create_default_config(self, config_path: Path):
        """Create a default configuration file."""
        default_config = {
            "active_provider": "groq",
            "providers": {
                "groq": {
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "openai/gpt-oss-120b",
                    "max_tokens": 2048,
                    "temperature": 0.1,
                    "timeout": 30
                },
                "openai": {
                    "base_url": "https://api.openai.com/v1", 
                    "model": "gpt-4o-mini",
                    "max_tokens": 2048,
                    "temperature": 0.1,
                    "timeout": 30
                }
            },
            "system_prompt": """You are OSCAR, an intelligent system automation assistant. You help users accomplish tasks by creating structured, safe plans.

            Rules:
            1. Always respond with valid JSON containing: thoughts, plan, risk_level, confirm_prompt
            2. Break complex tasks into clear, sequential steps
            3. Each step should have: id, tool, command/action, explanation
            4. Risk levels: low, medium, high, dangerous
            5. Be conservative with risk assessment
            6. Include clear explanations for each step

            Available tools: shell, browser, file_ops

            Current OS: {os_type}
            Current working directory: {cwd}""",
                        
                        "planning_template": """User request: {user_input}

            Context from previous actions: {context}

            Create a structured plan to accomplish this request safely. Consider the user's operating system and current context."""
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
    
    def get_active_llm_config(self) -> LLMProviderConfig:
        """Get configuration for the currently active LLM provider."""
        active_provider = self.llm_config.active_provider
        if active_provider not in self.llm_config.providers:
            raise ValueError(f"Active provider '{active_provider}' not found in config")
        
        return self.llm_config.providers[active_provider]
    
    def get_api_key(self, provider: str) -> str:
        """Get API key for the specified provider from environment variables."""
        env_vars = {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY"
        }
        
        env_var = env_vars.get(provider.lower())
        if not env_var:
            raise ValueError(f"Unknown provider: {provider}")
        
        api_key = os.getenv(env_var)
        if not api_key:
            raise ValueError(f"API key not found for {provider}. Please set {env_var} in your .env file")
        
        return api_key
    
    # Simple property getters
    @property
    def log_level(self) -> str:
        return os.getenv("OSCAR_LOG_LEVEL", "INFO")
    
    @property
    def safe_mode(self) -> bool:
        return os.getenv("OSCAR_SAFE_MODE", "true").lower() == "true"
    
    @property
    def debug_mode(self) -> bool:
        return os.getenv("OSCAR_DEBUG", "false").lower() == "true"
    
    @property
    def dry_run_mode(self) -> bool:
        return os.getenv("OSCAR_DRY_RUN", "false").lower() == "true"


# Global settings instance
settings = OSCARSettings()

# Centralized safety patterns (used by all components)
SAFETY_PATTERNS = {
    "dangerous_commands": [
        r"\brm\s+-rf\s+/.*",               # Remove root dir
        r"\bdel\s+/s\s+/q\b",              # Windows delete
        r"\bformat\s+c:\b",                # Format drive
        r"\bdd\s+if=.*",                   # Disk overwrite
        r":\(\)\s*\{\s*:\|\s*:\s*;\s*\}\s*;",  # Fork bomb
        r"\bsudo\s+rm\s+-rf\s+/.*",        # Sudo rm -rf /
        r"\bdiskpart\b",                   # Diskpart tool
        r"\bfdisk\b"                       # fdisk tool
    ],
    "high_risk_keywords": [
        "shutdown", "reboot", "mkfs", "chmod 777", "chown root"
    ],
    "medium_risk_keywords": [
        "kill", "service stop", "systemctl stop", "rmdir", "mv /"
    ]
}