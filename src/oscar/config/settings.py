"""
OSCAR Configuration Management
Handles loading and validation of configuration from YAML and environment variables.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    base_url: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.1
    timeout: int = 30
    retry_attempts: int = 3

class SafetyConfig(BaseModel):
    """Safety configuration settings."""
    dangerous_patterns: list[str] = Field(default_factory=list)
    confirmation_required: list[str] = Field(default_factory=list)

class PromptsConfig(BaseModel):
    """Prompt templates configuration."""
    system_prompt: str
    planning_template: str

class LLMConfig(BaseModel):
    """Complete LLM configuration."""
    active_provider: str
    providers: Dict[str, LLMProviderConfig]
    prompts: PromptsConfig
    safety: SafetyConfig

class OSCARSettings:
    """Main configuration class for OSCAR."""
    
    def __init__(self):
        self.project_root = self._find_project_root()
        self.config_dir = self.project_root / "config"
        
        # If config dir doesn't exist at root, create it
        if not self.config_dir.exists():
            self.config_dir.mkdir(exist_ok=True)
        
        self.data_dir = Path(os.getenv("OSCAR_DATA_DIR", "./data"))
        
        # Ensure directories exist
        self.data_dir.mkdir(exist_ok=True)
        (self.data_dir / "models").mkdir(exist_ok=True)
        (self.data_dir / "memory").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)
        
        # Load configurations
        self.llm_config = self._load_llm_config()
        
    def _find_project_root(self) -> Path:
        """Find the project root directory by looking for key files."""
        current = Path(__file__).parent
        # Go up until we find the project root (contains requirements.txt or .git)
        while current != current.parent:
            if (current / "requirements.txt").exists() or (current / ".git").exists():
                return current
            current = current.parent
        
        # If not found, use current working directory
        cwd = Path.cwd()
        if (cwd / "requirements.txt").exists() or (cwd / ".git").exists():
            return cwd
        
        # Last resort: assume we're in src/oscar/config, so go up 3 levels
        return Path(__file__).parent.parent.parent.parent
    
    def _load_llm_config(self) -> LLMConfig:
        """Load LLM configuration from YAML file."""
        config_path = self.config_dir / "llm_config.yaml"
        
        if not config_path.exists():
            # Create default config if it doesn't exist
            self._create_default_config(config_path)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # Validate and parse configuration
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
                    "timeout": 30,
                    "retry_attempts": 3
                },
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4-turbo-preview",
                    "max_tokens": 2048,
                    "temperature": 0.1,
                    "timeout": 30,
                    "retry_attempts": 3
                }
            },
            "prompts": {
                "system_prompt": "You are OSCAR, an intelligent system automation assistant. Always respond with valid JSON containing: thoughts, plan, risk_level, confirm_prompt",
                "planning_template": "User request: {user_input}\n\nCreate a structured plan to accomplish this request safely."
            },
            "safety": {
                "dangerous_patterns": [
                    "rm\\s+-rf\\s+/",
                    "dd\\s+if=",
                    "format\\s+c:",
                    "del\\s+/s\\s+/q"
                ],
                "confirmation_required": [
                    "system files",
                    "registry", 
                    "sudo",
                    "delete"
                ]
            }
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
        env_var_map = {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY", 
            "gemini": "GEMINI_API_KEY"
        }
        
        env_var = env_var_map.get(provider.lower())
        if not env_var:
            raise ValueError(f"Unknown provider: {provider}")
        
        api_key = os.getenv(env_var)
        if not api_key:
            raise ValueError(f"API key not found for {provider}. Please set {env_var} in your .env file")
        
        return api_key
    
    @property
    def log_level(self) -> str:
        """Get logging level from environment."""
        return os.getenv("OSCAR_LOG_LEVEL", "INFO")
    
    @property
    def safe_mode(self) -> bool:
        """Check if safe mode is enabled."""
        return os.getenv("OSCAR_SAFE_MODE", "true").lower() == "true"
    
    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled."""
        return os.getenv("OSCAR_DEBUG", "false").lower() == "true"
    
    @property
    def dry_run_mode(self) -> bool:
        """Check if dry run mode is enabled."""
        return os.getenv("OSCAR_DRY_RUN", "false").lower() == "true"

# Global settings instance
settings = OSCARSettings()