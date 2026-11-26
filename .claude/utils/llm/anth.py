#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "anthropic",
#     "python-dotenv",
# ]
# ///

import json
import os
import subprocess
import sys
from dotenv import load_dotenv

# Default model for both API and CLI modes
DEFAULT_MODEL = "claude-3-5-haiku-20241022"


def _prompt_llm_api(prompt_text, max_tokens=100):
    """
    Prompt LLM using direct Anthropic API.

    Args:
        prompt_text (str): The prompt to send to the model
        max_tokens (int): Maximum tokens in response

    Returns:
        str: The model's response text, or None if error
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt_text}],
        )

        return message.content[0].text.strip()

    except Exception:
        return None


def _prompt_llm_cli(prompt_text, max_tokens=100):
    """
    Prompt LLM using Claude Code CLI (claude -p).

    Uses Claude Code's stored credentials (from 'claude login'),
    does not require ANTHROPIC_API_KEY environment variable.

    Args:
        prompt_text (str): The prompt to send to the model
        max_tokens (int): Maximum tokens in response (used for --max-turns estimation)

    Returns:
        str: The model's response text, or None if error
    """
    claude_path = os.getenv("CLAUDE_CODE_PATH", "claude")

    try:
        cmd = [
            claude_path,
            "-p",
            prompt_text,
            "--model",
            DEFAULT_MODEL,
            "--output-format",
            "json",
            "--max-turns",
            "1",  # Single turn for simple prompts
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        # Parse JSON output
        output = json.loads(result.stdout)

        # Extract result text from JSON response
        if isinstance(output, dict) and "result" in output:
            return output["result"].strip()
        elif isinstance(output, str):
            return output.strip()

        return None

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


def prompt_llm(prompt_text, max_tokens=100):
    """
    Base Anthropic LLM prompting method using fastest model.

    Uses CLAUDE_LLM_MODE environment variable to select implementation:
    - "api" (default): Direct Anthropic API calls
    - "cli": Claude Code CLI (claude -p)

    Args:
        prompt_text (str): The prompt to send to the model
        max_tokens (int): Maximum tokens in response

    Returns:
        str: The model's response text, or None if error
    """
    load_dotenv()

    mode = os.getenv("CLAUDE_LLM_MODE", "api").lower()

    if mode == "cli":
        return _prompt_llm_cli(prompt_text, max_tokens)
    else:
        return _prompt_llm_api(prompt_text, max_tokens)


def generate_completion_message():
    """
    Generate a completion message using Anthropic LLM.

    Returns:
        str: A natural language completion message, or None if error
    """
    engineer_name = os.getenv("ENGINEER_NAME", "").strip()

    if engineer_name:
        name_instruction = f"Sometimes (about 30% of the time) include the engineer's name '{engineer_name}' in a natural way."
        examples = f"""Examples of the style: 
- Standard: "Work complete!", "All done!", "Task finished!", "Ready for your next move!"
- Personalized: "{engineer_name}, all set!", "Ready for you, {engineer_name}!", "Complete, {engineer_name}!", "{engineer_name}, we're done!" """
    else:
        name_instruction = ""
        examples = """Examples of the style: "Work complete!", "All done!", "Task finished!", "Ready for your next move!" """

    prompt = f"""Generate a short, friendly completion message for when an AI coding assistant finishes a task. 

Requirements:
- Keep it under 10 words
- Make it positive and future focused
- Use natural, conversational language
- Focus on completion/readiness
- Do NOT include quotes, formatting, or explanations
- Return ONLY the completion message text
{name_instruction}

{examples}

Generate ONE completion message:"""

    response = prompt_llm(prompt)

    # Clean up response - remove quotes and extra formatting
    if response:
        response = response.strip().strip('"').strip("'").strip()
        # Take first line if multiple lines
        response = response.split("\n")[0].strip()

    return response


def generate_agent_name():
    """
    Generate a one-word agent name using Anthropic.

    Uses CLAUDE_LLM_MODE environment variable to select implementation.

    Returns:
        str: A single-word agent name, or fallback name if error
    """
    import random

    load_dotenv()

    # Example names to guide generation
    example_names = [
        "Phoenix", "Sage", "Nova", "Echo", "Atlas", "Cipher", "Nexus",
        "Oracle", "Quantum", "Zenith", "Aurora", "Vortex", "Nebula",
        "Catalyst", "Prism", "Axiom", "Helix", "Flux", "Synth", "Vertex"
    ]

    # If no API key and not using CLI mode, return random fallback
    mode = os.getenv("CLAUDE_LLM_MODE", "api").lower()
    if mode != "cli" and not os.getenv("ANTHROPIC_API_KEY"):
        return random.choice(example_names)

    # Create examples string
    examples_str = ", ".join(example_names[:10])  # Use first 10 as examples

    prompt_text = f"""Generate exactly ONE unique agent/assistant name.

Requirements:
- Single word only (no spaces, hyphens, or punctuation)
- Abstract and memorable
- Professional sounding
- Easy to pronounce
- Similar style to these examples: {examples_str}

Generate a NEW name (not from the examples). Respond with ONLY the name, nothing else.

Name:"""

    try:
        # Use the unified prompt_llm function with low max_tokens
        response = prompt_llm(prompt_text, max_tokens=20)

        if not response:
            raise Exception("No response from LLM")

        # Extract and clean the name
        name = response.strip()
        # Ensure it's a single word
        name = name.split()[0] if name else "Agent"
        # Remove any punctuation
        name = ''.join(c for c in name if c.isalnum())
        # Capitalize first letter
        name = name.capitalize() if name else "Agent"

        # Validate it's not empty and reasonable length
        if name and 3 <= len(name) <= 20:
            return name
        else:
            raise Exception("Invalid name generated")

    except Exception:
        # Return random fallback name
        return random.choice(example_names)


def main():
    """Command line interface for testing."""
    import json
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--completion":
            message = generate_completion_message()
            if message:
                print(message)
            else:
                print("Error generating completion message")
        elif sys.argv[1] == "--agent-name":
            # Generate agent name (no input needed)
            name = generate_agent_name()
            print(name)
        else:
            prompt_text = " ".join(sys.argv[1:])
            response = prompt_llm(prompt_text)
            if response:
                print(response)
            else:
                print("Error calling Anthropic API")
    else:
        print("Usage: ./anth.py 'your prompt here' or ./anth.py --completion or ./anth.py --agent-name")


if __name__ == "__main__":
    main()
