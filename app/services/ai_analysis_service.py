import json
from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app.core.config import settings

SYSTEM_PROMPT = """You are Deploy Shield's AI validation analyst. Your job is to analyze deployment validation results and provide a clear, actionable explanation to developers.

You will receive the complete validation result including:
- All stage results (clone, code check, dependency check, dockerfile, docker build, container startup)
- Container logs if available
- Build logs if available
- Error messages

Your response MUST be structured as JSON with these fields:
{
  "summary": "One-line summary of the overall result (max 100 chars)",
  "status": "success" | "warning" | "failed",
  "details": "2-4 sentence explanation of what happened. Be specific - mention file names, line numbers, exact errors.",
  "fix_suggestion": "If there's an issue, explain exactly how to fix it. If all passed, give a short 'ready to deploy' message.",
  "issues": [
    {
      "stage": "which stage had the issue",
      "severity": "error" | "warning" | "info",
      "message": "what went wrong",
      "fix": "how to fix it"
    }
  ]
}

Rules:
- Be concise and specific. Don't be generic.
- If container crashed with SyntaxError, point to the exact error and file.
- If it's an env/database issue, say which variables are missing and how to provide them.
- If everything passed, still give useful info (e.g. "App builds in X, uses port Y, ready for deploy").
- Always respond with valid JSON only, no markdown formatting.
"""


def analyze_validation_result(validation_result: dict, env_vars: str = None) -> dict:
    """Run AI analysis on validation results using agno agent."""
    try:
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
            instructions=[SYSTEM_PROMPT],
            markdown=False,
        )

        env_context = ""
        if env_vars:
            provided_keys = [line.split("=")[0].strip() for line in env_vars.strip().split("\n") if "=" in line and not line.startswith("#")]
            env_context = f"\n\nIMPORTANT: The user HAS already provided these environment variables: {', '.join(provided_keys)}. Do NOT suggest adding env vars that are already provided. If the container still crashed, the issue is likely incorrect values, unreachable external services, or variables that are set but the service they connect to is not available during validation."
        else:
            env_context = "\n\nNote: The user did NOT provide any environment variables for this validation run."

        prompt = f"""Analyze this deployment validation result and provide a clear explanation:

{json.dumps(validation_result, indent=2, default=str)}{env_context}

Respond with JSON only."""

        response = agent.run(prompt)
        response_text = response.content.strip()

        # Clean up if wrapped in markdown code block
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        analysis = json.loads(response_text)
        return analysis

    except json.JSONDecodeError:
        return {
            "summary": "AI analysis completed but response parsing failed",
            "status": validation_result.get("success", False) and "success" or "failed",
            "details": response_text if 'response_text' in dir() else "Could not parse AI response",
            "fix_suggestion": "",
            "issues": [],
        }
    except Exception as e:
        return {
            "summary": "AI analysis unavailable",
            "status": "unknown",
            "details": f"AI analysis failed: {str(e)}",
            "fix_suggestion": "",
            "issues": [],
        }
