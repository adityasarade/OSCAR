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
    base_url: str = None  # Optional - Gemini doesn't use OpenAI-compatible endpoint
    model: str
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: int = 60


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
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        return LLMConfig(**config_data)
    
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
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY"
        }
        
        env_var = env_vars.get(provider.lower())
        if not env_var:
            raise ValueError(f"Unknown provider: {provider}")
        
        api_key = os.getenv(env_var)
        if not api_key:
            raise ValueError(f"API key not found for {provider}. Please set {env_var} in your .env file")
        
        return api_key
    
    def get_tavily_keys(self) -> list:
        """Get Tavily API keys for web search with fallback support."""
        keys = []
        for key_name in ["TAVILY_API_KEY1", "TAVILY_API_KEY2"]:
            key = os.getenv(key_name)
            if key:
                keys.append(key)
        return keys
    
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