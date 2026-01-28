"""AI-powered whitelist entry parser using Claude Haiku."""

import json
import logging
from dataclasses import dataclass

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class ParsedWhitelistEntry:
    """A parsed whitelist entry."""

    entry_type: str  # 'email' or 'domain'
    value: str  # The actual email or domain


def parse_whitelist_input(api_key: str, user_input: str) -> list[ParsedWhitelistEntry]:
    """Parse natural language whitelist input using Claude Haiku.

    Args:
        api_key: Anthropic API key
        user_input: User's natural language input describing what to whitelist

    Returns:
        List of parsed whitelist entries

    Examples:
        "add bi-scs.com and sonya@topwellzx.com"
        -> [ParsedWhitelistEntry('domain', 'bi-scs.com'),
            ParsedWhitelistEntry('email', 'sonya@topwellzx.com')]

        "whitelist all emails from acme corp (acme.com)"
        -> [ParsedWhitelistEntry('domain', 'acme.com')]
    """
    if not user_input.strip():
        return []

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """You are a whitelist entry parser. Extract email addresses and domains from user input.

Return a JSON array of objects with:
- "type": either "email" (for specific email addresses) or "domain" (for entire domains)
- "value": the email address or domain name (lowercase, no @ prefix for domains)

Rules:
- If input contains a full email address (has @), extract it as type "email"
- If input mentions a domain/company domain without @, extract as type "domain"
- Domain values should NOT have @ prefix (e.g., "example.com" not "@example.com")
- Handle common variations like "@domain.com", "domain.com", "emails from domain.com"
- Extract ALL email addresses and domains mentioned
- Ignore filler words and explanatory text

Examples:
Input: "@bi-scs.com or sonya@topwellzx.com"
Output: [{"type": "domain", "value": "bi-scs.com"}, {"type": "email", "value": "sonya@topwellzx.com"}]

Input: "add emails from acme.com and also bob@gmail.com"
Output: [{"type": "domain", "value": "acme.com"}, {"type": "email", "value": "bob@gmail.com"}]

Input: "whitelist my colleague jane.doe@company.org"
Output: [{"type": "email", "value": "jane.doe@company.org"}]

Input: "trust all mail from amazon.com, ups.com, fedex.com"
Output: [{"type": "domain", "value": "amazon.com"}, {"type": "domain", "value": "ups.com"}, {"type": "domain", "value": "fedex.com"}]

Respond ONLY with the JSON array, no other text."""

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}],
        )

        response_text = response.content[0].text.strip()

        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```") and not in_json:
                    in_json = True
                    continue
                elif line.startswith("```") and in_json:
                    break
                elif in_json:
                    json_lines.append(line)
            response_text = "\n".join(json_lines)

        result = json.loads(response_text)

        entries = []
        for item in result:
            entry_type = item.get("type", "").lower()
            value = item.get("value", "").lower().strip()

            # Validate entry type
            if entry_type not in ("email", "domain"):
                logger.warning(f"Invalid entry type from AI: {entry_type}")
                continue

            # Clean up domain (remove @ if AI included it)
            if entry_type == "domain" and value.startswith("@"):
                value = value[1:]

            # Basic validation
            if entry_type == "email" and "@" not in value:
                logger.warning(f"Invalid email from AI (no @): {value}")
                continue

            if not value:
                continue

            entries.append(ParsedWhitelistEntry(entry_type=entry_type, value=value))

        logger.info(f"AI parsed whitelist input: {user_input!r} -> {entries}")
        return entries

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response: {e}")
        logger.error(f"Response was: {response_text}")
        return []
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in whitelist parsing: {e}")
        return []
