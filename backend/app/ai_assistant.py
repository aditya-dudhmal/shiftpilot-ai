"""Optional LLM layer for the NL assistant.

Design decision: the LLM is an *optional proposer*, never the
validator. Flow:
  1. If no API key is configured -> rule parser only (demo mode).
  2. If a key is configured -> ask the LLM for a typed constraint,
     then run it through ``validate_llm_constraint`` — the same
     checks the rule parser applies. A bad LLM answer is rejected
     with a clear message; the rule parser is tried as a fallback.
  3. The validated constraint is stored and applied by CP-SAT.

This is also why the LLM prompt asks for JSON only, with a closed
vocabulary of kinds/days/shifts: free text from a model must not be
able to smuggle an unvalidated rule into the schedule. See
INTERVIEW_GUIDE.md ("How the AI assistant works") for the trade-offs.
"""
from __future__ import annotations

import json

from .config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_PROVIDER, OPENAI_API_KEY
from .nl_parser import parse_instruction, validate_llm_constraint

SYSTEM_PROMPT = """You translate a manager's scheduling instruction into ONE JSON object.
Allowed kinds: day_off, limit_evening_shifts, max_hours, min_hours, avoid_shift, prefer_shift.
Days: Monday..Sunday. Shifts: Morning, Midday, Evening.
Hours must be a multiple of 4, 4-40. Evening cap 0-7.
Return ONLY JSON, e.g. {"kind": "day_off", "employee_name": "Maya Patel", "payload": {"day": "Friday"}, "explanation": "..."}.
If you cannot map the instruction to one allowed kind, return {"kind": "unknown"}.
Use the employee's full name exactly as given in the roster."""


def _llm_parse(text, employees):
    roster = ", ".join(f"{e['name']} ({e['role']}, max {e['max_hours_per_week']}h)" for e in employees)
    provider = LLM_PROVIDER
    if provider == "auto":
        provider = "openai" if OPENAI_API_KEY else ("anthropic" if ANTHROPIC_API_KEY else "none")
    try:
        if provider == "openai" and OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=LLM_MODEL or "gpt-4o-mini",
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": f"Roster: {roster}\nInstruction: {text}"}],
                temperature=0, max_tokens=300)
            raw = resp.choices[0].message.content or ""
        elif provider == "anthropic" and ANTHROPIC_API_KEY:
            from anthropic import Anthropic
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=LLM_MODEL or "claude-3-5-haiku-latest",
                max_tokens=300, temperature=0, system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Roster: {roster}\nInstruction: {text}"}])
            raw = resp.content[0].text or ""
        else:
            return None
    except Exception as exc:  # LLM failure must not break the assistant.
        return {"_llm_error": str(exc)}
    try:
        candidate = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return {"_llm_error": "LLM returned non-JSON output."}
    candidate["source_text"] = text
    return candidate


def interpret(text, employees, week_start=""):
    """Return (parsed_dict, engine_used). engine is 'rules' | 'llm' | 'llm+rules'."""
    rule_result = parse_instruction(text, employees, week_start)
    # No key configured: demo mode, rules only.
    if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        return rule_result, "rules (demo mode — no API key)"
    candidate = _llm_parse(text, employees)
    if candidate is None:
        return rule_result, "rules (demo mode — no API key)"
    if "_llm_error" in candidate:
        # LLM failed; fall back to the deterministic parser rather
        # than failing the request.
        rule_result["note"] = f"LLM unavailable ({candidate['_llm_error'][:120]}); used the built-in parser."
        return rule_result, "rules (LLM fallback)"
    ok, validated = validate_llm_constraint(candidate, employees)
    if ok:
        validated["week_start"] = week_start
        return validated, "llm (validated)"
    # LLM proposed something invalid — prefer the rule parser's answer
    # if it succeeded, otherwise report the validation failure.
    if rule_result.get("ok"):
        return rule_result, "rules (LLM proposal rejected by validation)"
    return {"ok": False, "error": f"LLM proposal failed validation: {validated}"}, "llm (rejected)"
