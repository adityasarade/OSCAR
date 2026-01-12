"""
OSCAR Memory Adapter - Asterix-based persistent memory

Provides session context, user preferences, and knowledge persistence:
- Editable memory blocks for different context types
- Automatic state persistence across sessions
- Semantic search for relevant context retrieval
"""

from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from oscar.config.settings import settings


class OSCARMemoryAdapter:
    """
    Memory adapter using Asterix for persistent, editable memory.
    
    Memory Blocks:
    - session_context: Current session tasks and results
    - user_preferences: Learned user preferences
    - knowledge_base: Facts and information from searches
    """
    
    def __init__(self, agent_id: str = "oscar_memory"):
        self.agent_id = agent_id
        self.state_dir = settings.data_dir / "memory"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.agent = None
        self._init_agent()
    
    def _init_agent(self):
        """Initialize Asterix agent with memory blocks."""
        try:
            from asterix import Agent, BlockConfig
            
            # Memory block sizing rationale (qwen-qwq-32b has 131K context):
            # - session_context: 4000 chars (~1K tokens) - stores recent interactions
            # - knowledge_base: 3000 chars (~750 tokens) - stores search results/facts
            # - user_preferences: 1000 chars (~250 tokens) - stores learned preferences
            # Total: ~8K chars (~2K tokens) - small fraction of 131K, leaves room for planning
            self.agent = Agent(
                agent_id=self.agent_id,
                blocks={
                    "session_context": BlockConfig(size=4000, priority=1),
                    "knowledge_base": BlockConfig(size=3000, priority=2),
                    "user_preferences": BlockConfig(size=1000, priority=3),
                },
                model="qwen-qwq-32b"  # Match OSCAR's primary model
            )
            
            # Try to load existing state
            self._load_state()
            
        except ImportError:
            self.agent = None
        except Exception as e:
            self.agent = None
            print(f"Warning: Could not initialize Asterix memory: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if memory system is available."""
        return self.agent is not None
    
    def store_interaction(self, user_input: str, result: Dict[str, Any]) -> None:
        """Store an interaction in session context."""
        if not self.is_available:
            return
        
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            status = "✓" if result.get("success") else "✗"
            stage = result.get("stage", "unknown")
            
            entry = f"[{timestamp}] {status} {user_input[:50]}... ({stage})"
            
            # Get current context and append
            current = self.get_block("session_context") or ""
            lines = current.split("\n") if current else []
            lines.append(entry)
            
            # Keep only last 10 interactions
            if len(lines) > 10:
                lines = lines[-10:]
            
            self.update_block("session_context", "\n".join(lines))
            
        except Exception as e:
            print(f"Warning: Could not store interaction: {e}")
    
    def store_knowledge(self, topic: str, content: str) -> None:
        """Store knowledge from web searches or other sources."""
        if not self.is_available:
            return
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            entry = f"[{timestamp}] {topic}: {content[:200]}"
            
            current = self.get_block("knowledge_base") or ""
            # Prepend new knowledge (most recent first)
            updated = f"{entry}\n{current}".strip()
            
            # Truncate if too long
            if len(updated) > 2800:
                updated = updated[:2800] + "..."
            
            self.update_block("knowledge_base", updated)
            
        except Exception:
            pass
    
    def store_preference(self, preference: str) -> None:
        """Store a learned user preference."""
        if not self.is_available:
            return
        
        try:
            current = self.get_block("user_preferences") or ""
            if preference not in current:
                updated = f"{current}\n- {preference}".strip()
                self.update_block("user_preferences", updated)
        except Exception:
            pass
    
    def get_relevant_context(self, query: str = "") -> str:
        """Get relevant context for planning."""
        if not self.is_available:
            return "No memory available"
        
        try:
            memory = self.get_all_blocks()
            
            parts = []
            
            # Session context
            session = memory.get("session_context", "").strip()
            if session:
                parts.append(f"Recent actions:\n{session}")
            
            # User preferences
            prefs = memory.get("user_preferences", "").strip()
            if prefs:
                parts.append(f"User preferences:\n{prefs}")
            
            # Knowledge (only include if query seems related)
            knowledge = memory.get("knowledge_base", "").strip()
            if knowledge and query:
                # Simple relevance check - include if any word matches
                query_words = set(query.lower().split())
                if any(word in knowledge.lower() for word in query_words):
                    parts.append(f"Relevant knowledge:\n{knowledge[:500]}")
            
            return "\n\n".join(parts) if parts else "No relevant context"
            
        except Exception as e:
            return f"Memory error: {e}"
    
    def get_block(self, block_name: str) -> Optional[str]:
        """Get content of a specific memory block."""
        if not self.is_available:
            return None
        
        try:
            memory = self.agent.get_memory()
            return memory.get(block_name, "")
        except Exception:
            return None
    
    def get_all_blocks(self) -> Dict[str, str]:
        """Get all memory blocks."""
        if not self.is_available:
            return {}
        
        try:
            return self.agent.get_memory()
        except Exception:
            return {}
    
    def update_block(self, block_name: str, content: str) -> bool:
        """Update a specific memory block."""
        if not self.is_available:
            return False
        
        try:
            self.agent.update_memory(block_name, content)
            return True
        except Exception:
            return False
    
    def save(self) -> bool:
        """Save current state to disk."""
        if not self.is_available:
            return False
        
        try:
            self.agent.save_state()
            return True
        except Exception as e:
            print(f"Warning: Could not save memory state: {e}")
            return False
    
    def _load_state(self) -> bool:
        """Load saved state from disk."""
        try:
            # Asterix handles state loading automatically if state exists
            return True
        except Exception:
            return False
    
    def clear_session(self) -> None:
        """Clear session context (keep preferences and knowledge)."""
        if self.is_available:
            self.update_block("session_context", "")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of current memory state."""
        if not self.is_available:
            return {"available": False}
        
        memory = self.get_all_blocks()
        return {
            "available": True,
            "session_entries": len(memory.get("session_context", "").split("\n")),
            "preferences_count": memory.get("user_preferences", "").count("-"),
            "knowledge_size": len(memory.get("knowledge_base", ""))
        }


# Convenience function
def create_memory_adapter() -> OSCARMemoryAdapter:
    """Create and return a new memory adapter instance."""
    return OSCARMemoryAdapter()
