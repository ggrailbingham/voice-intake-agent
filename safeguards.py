"""
safeguards.py
-------------
Pre- and post-LLM safety checks. All checks run in orchestration code,
independent of the LLM, so they cannot be overridden by prompt injection.

Three layers:
1. Input screening  — runs BEFORE the LLM call
2. Output screening — runs AFTER the LLM response
3. Session limits   — enforced by the orchestration loop
"""

import re

# ── 1. Crisis / sensitive escalation ──────────────────────────────────────────

CRISIS_PATTERNS = [
    r'\b(kill myself|killing myself)\b',
    r'\b(end my life|end it all)\b',
    r'\b(want to die|wanting to die)\b',
    r'\b(hurt myself|hurting myself|self.harm)\b',
    r'\b(suicide|suicidal)\b',
    r'\b(don\'t want to (be here|live|exist))\b',
    r'\b(no reason to (live|go on))\b',
    r'\b(not worth (living|it) anymore)\b',
]

_CRISIS_RE = re.compile("|".join(CRISIS_PATTERNS), re.IGNORECASE)

CRISIS_RESPONSE = (
    "I want to make sure you get the right support right now. "
    "Let me connect you with someone who can help."
)

def check_crisis(user_input: str) -> bool:
    """Returns True if input contains crisis signals."""
    return bool(_CRISIS_RE.search(user_input))


# ── 2. Prompt injection detection ─────────────────────────────────────────────

INJECTION_PATTERNS = [
    r'ignore (all |your |previous |prior )?(instructions|rules|prompt|system)',
    r'forget (all |your |previous |prior )?(instructions|rules|prompt|system)',
    r'disregard (all |your |previous |prior )?(instructions|rules)',
    r'you are now',
    r'new (instructions|rules|persona|role|system prompt)',
    r'pretend (you are|to be|you\'re)',
    r'act as (if you are|though you are|a )',
    r'your (true |real |actual )(self|purpose|goal|instructions)',
    r'(show|display|print|output|reveal|repeat|tell me) (the |your )?(system prompt|instructions|rules|context|database|records|customer data)',
    r'(read|access|query|fetch|retrieve|look up) (the |all )?(customer|user|record|database|data)',
    r'developer mode',
    r'jailbreak',
    r'(bypass|override|disable) (your |the )?(safety|filter|rule|restriction|limit)',
]

_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

INJECTION_RESPONSE = (
    "I'm only able to help with your insurance intake today. "
    "Shall we continue where we left off?"
)

def check_injection(user_input: str) -> bool:
    """Returns True if input looks like a prompt injection attempt."""
    return bool(_INJECTION_RE.search(user_input))


# ── 3. Output scanning ─────────────────────────────────────────────────────────

OUTPUT_BLOCK_PATTERNS = [
    r'system prompt',
    r'my instructions (are|say|state|include)',
    r'(customer|user) (record|database|data)',
    r'\b\d{3}-\d{2}-\d{4}\b',   # SSN pattern
    r'\b\d{16}\b',               # Credit card pattern
]

_OUTPUT_BLOCK_RE = re.compile("|".join(OUTPUT_BLOCK_PATTERNS), re.IGNORECASE)

OUTPUT_BLOCK_RESPONSE = (
    "I'm sorry, I wasn't able to process that. Let me connect you with a specialist."
)

def check_output(agent_response: str) -> bool:
    """Returns True if agent output contains something that should be blocked."""
    return bool(_OUTPUT_BLOCK_RE.search(agent_response))


# ── 4. Session limits ──────────────────────────────────────────────────────────

MAX_TURNS = 40
MAX_RETRIES_PER_STEP = 10
SILENCE_TIMEOUT_TURNS = 2

TURN_LIMIT_RESPONSE = (
    "I want to make sure you get the best help possible. "
    "Let me connect you with one of our specialists now."
)

RETRY_LIMIT_RESPONSE = (
    "Let me connect you with a specialist who can assist you further."
)


# ── 5. Recording consent ───────────────────────────────────────────────────────

TWO_PARTY_CONSENT_STATES = {
    "CA", "CT", "FL", "IL", "MD", "MA", "MI", "MT", "NV", "NH",
    "OR", "PA", "WA"
}

def requires_two_party_consent(state_code: str) -> bool:
    return state_code.upper() in TWO_PARTY_CONSENT_STATES

RECORDING_CONSENT_DISCLOSURE = (
    "This call may be recorded for quality and training purposes. "
    "By continuing, you consent to this recording. "
)


# ── 6. Goodbye / call end detection ───────────────────────────────────────────

# Unambiguous — goodbye in any context
UNAMBIGUOUS_GOODBYE_PATTERNS = [
    r'\b(goodbye|good-bye|good bye)\b',
    r'\bbye\b',
    r'\bend the call\b',
    r'\bhang up\b',
    r'\bnot interested\b',
    r'\bdon\'t need (this|help|assistance)\b',
]

# Ambiguous — only treated as goodbye outside of confirmation steps
AMBIGUOUS_GOODBYE_PATTERNS = [
    r'\bthat\'s all\b',
    r'\bthat is all\b',
    r'\bi\'m done\b',
    r'\bno thank you\b',
    r'\bno thanks\b',
]

_UNAMBIGUOUS_RE = re.compile("|".join(UNAMBIGUOUS_GOODBYE_PATTERNS), re.IGNORECASE)
_AMBIGUOUS_RE = re.compile("|".join(AMBIGUOUS_GOODBYE_PATTERNS), re.IGNORECASE)

# During these steps, ambiguous phrases are treated as confirmation, not goodbye
CONFIRMATION_STEPS = {"ages", "hmo_preference", "summary"}

GOODBYE_RESPONSE = (
    "Thank you for calling HealthBridge Insurance. Have a great day — goodbye!"
)

def check_goodbye(user_input: str, current_step: str = "") -> bool:
    """
    Returns True if the customer is ending the call.
    Unambiguous phrases (bye, goodbye) always trigger.
    Ambiguous phrases (that's all, no thanks) only trigger outside confirmation steps.
    """
    if _UNAMBIGUOUS_RE.search(user_input):
        return True
    if current_step not in CONFIRMATION_STEPS:
        if _AMBIGUOUS_RE.search(user_input):
            return True
    return False