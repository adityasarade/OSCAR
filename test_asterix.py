from asterix import Agent, BlockConfig
import os

def test_asterix():
    """Test basic Asterix functionality"""
    print("Testing Asterix installation...")
    
    # Test without Qdrant (core features only)
    try:
        agent = Agent(
            agent_id="test_agent",
            blocks={
                "test_block": BlockConfig(size=1000, priority=1)
            },
            model="openai/gpt-oss-120b"  # Using Groq model
        )
        print("✓ Asterix agent created successfully")
        
        # Test memory operations
        agent.update_memory("test_block", "Test content")
        memory = agent.get_memory()
        print(f"✓ Memory operations working: {memory['test_block']}")
        
        # Test state persistence
        agent.save_state()
        print("✓ State persistence working")
        
        print("\n✅ Asterix is ready to integrate!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_asterix()