from __future__ import annotations

from typing import Optional


def build_user_prompt(
    action_instruction: str,
    output_format: str,
    text: str,
    extra_instruction: Optional[str] = None,
) -> str:
    """
    Build the user prompt in a consistent, inspectable format.

    extra_instruction is treated as the highest-priority per-run constraint.
    """
    action_instruction = (action_instruction or "").strip()
    output_format = (output_format or "").strip()
    text = text or ""
    extra = (extra_instruction or "").strip()

    parts = []

    if action_instruction:
        parts.append("Task:\n" + action_instruction)
    else:
        parts.append("Task:\nProcess the text according to the persona.")

    if extra:
        parts.append(
            "Extra instruction (highest priority):\n"
            + extra
            + "\n\n"
            + "If the extra instruction conflicts with persona style preferences, follow the extra instruction."
        )

    if output_format:
        parts.append("Output rules:\n" + output_format)
    else:
        parts.append("Output rules:\nReturn only the requested output.")

    parts.append("Text:\n```\n" + text + "\n```")

    return "\n\n".join(parts)


def build_system_prompt(persona_system: str) -> str:
    """
    System prompt is persona + lightweight guardrails.
    Keep it short so models still have room for the task and text.
    """
    persona_system = (persona_system or "").strip()

    guardrails = (
        "Rules:\n"
        "- Be accurate and do not invent facts.\n"
        "- Preserve meaning unless explicitly asked to change it.\n"
        "- Keep proper nouns, product names, and technical terms unchanged unless instructed.\n"
        "- Return only the requested output.\n"
    )

    if persona_system:
        return persona_system + "\n\n" + guardrails
    return guardrails
