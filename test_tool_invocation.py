#!/usr/bin/env python
"""
Quick test to verify whether @use_function_invocation is actually invoking tools.
Run: uv run python test_tool_invocation.py
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from agent_framework import ChatAgent, ChatMessage
from monocle.agents import create_chat_agent
from monocle.models import NoteMetadata
from monocle.vault import VaultLayer
from monocle.index.memory import MemoryIndex
from monocle.config import Settings
import tempfile


async def test_tool_invocation():
    """Test whether ChatAgent actually invokes tools when the model returns a tool call."""
    
    # Create minimal, real dependencies  
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = VaultLayer(tmpdir)
        index = MemoryIndex()
        settings = Settings()
        
        # Mock AI provider that returns a create_note tool call
        mock_ai = AsyncMock()
        mock_ai._provider_name = "test"
        
        # This is what the AI should return: a tool call to create_note
        tool_call_json = json.dumps({
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "create_note",
                    "arguments": json.dumps({
                        "title": "Test Note",
                        "body": "Test body",
                        "note_type": "idea",
                        "domain": "personal",
                        "tags": []
                    })
                }
            }]
        })
        
        # Stream returns the tool call JSON
        async def mock_stream(*args, **kwargs):
            yield tool_call_json
            
        mock_ai.chat = AsyncMock(return_value=mock_stream())
        mock_ai.transcribe = AsyncMock()
        mock_ai.embed = AsyncMock(return_value=[0.0] * 1536)
        
        # Create the agent
        agent = create_chat_agent(
            ai=mock_ai,
            vault=vault,
            index=index,
            settings=settings,
        )
        
        # Send a message that should trigger tool invocation
        messages = [ChatMessage(role="user", text="Create a note about test")]
        
        # Collect all updates from the stream
        updates = []
        async for update in agent.run_stream(messages):
            updates.append(update)
            print(f"Update: {update}")
        
        # Print what we got
        print(f"\nTotal updates: {len(updates)}")
        for i, update in enumerate(updates):
            print(f"Update {i}: contents={update.contents}")
            for content in update.contents:
                print(f"  - {type(content).__name__}: {content}")
        
        # Check if we got a FunctionResultContent (which means the tool was invoked)
        has_function_result = any(
            'FunctionResultContent' in str(type(content))
            for update in updates
            for content in update.contents
        )
        
        # Check if the note was actually created in the vault
        vault_notes = list(vault.rglob("*.md"))
        vault_notes = [n for n in vault_notes if not n.name.endswith(".error.md")]
        
        print(f"\nFunction result found: {has_function_result}")
        print(f"Notes in vault: {len(vault_notes)}")
        
        if vault_notes:
            for note_file in vault_notes:
                print(f"  - {note_file}")
                
        # The test passes if:
        # 1. We got a FunctionResultContent (tool was invoked)
        # 2. A note was created in the vault
        
        if has_function_result and vault_notes:
            print("\n✅ Tool invocation working correctly!")
            return True
        else:
            print("\n❌ Tool invocation NOT working!")
            print(f"   Has result: {has_function_result}")
            print(f"   Has vault note: {len(vault_notes) > 0}")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_tool_invocation())
    exit(0 if result else 1)
