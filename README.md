# HealthBridge Voice Intake Agent

A fully deployed voice AI agent that conducts insurance intake calls end-to-end — collecting structured customer information, applying state-specific eligibility rules, and emailing a completed intake record to the customer before handing off to a human advisor.

**Live demo:** Call `+1 (641) 535-3678` to speak with the agent.

Built over a weekend as a working prototype of agentic AI applied to insurance contact center automation.

---

## What It Does

When a customer calls in:

1. The agent greets them and collects 8 structured fields: name, budget, who the coverage is for, state, ages of all insured, pre-existing conditions, plan preference, and email
2. State-specific eligibility rules are applied in real time (minimum policyholder age, maximum dependent age) — violations are caught and handled gracefully
3. Complex coverage scenarios are handled: primary only, primary + spouse, primary + spouse + dependents, dependents only, and more — each with the correct follow-up questions
4. A summary is read back for confirmation before completing
5. A formatted intake record is emailed to the customer via SendGrid - only for proof of concept; not for production
6. The call is transferred to a human advisor with the completed record 

The whole thing runs on a single LLM call per conversational turn, with all safety logic running in orchestration code around it.

---

## Architecture

```
Inbound Call (Twilio)
      │
      ▼
Recording Consent Disclosure
(hardcoded — prepended before any LLM output)
      │
      ▼
Twilio STT → text
      │
      ▼
Input Safeguards (safeguards.py)        ← runs BEFORE LLM, cannot be prompt-injected
  ├── Crisis detection                  → immediate human transfer, hardcoded response
  ├── Prompt injection detection        → hardcoded deflection, LLM call skipped
  ├── Goodbye detection (context-aware) → hangup or continue based on current step
  ├── Silence timeout                   → escalate after 2 consecutive empty inputs
  └── Turn / retry limits               → escalate if session exceeds limits
      │
      ▼
IntakeSession (agent.py)
  ├── Step tracker          ← gates which parsing runs on each turn
  ├── State rules lookup    ← triggered only on the state step (state_rules.py)
  ├── LLM API call (Claude) ← one call per turn, full conversation history passed
  └── Field state tracker   ← structured JSON object updated each turn
      │
      ▼
Output Safeguards (safeguards.py)       ← runs AFTER LLM
  └── Output scanner → suppress response if sensitive content detected
      │
      ▼
Twilio TTS → customer hears response
      │
      ├── [Normal turn]      → listen for next input
      ├── [Goodbye]          → hangup
      ├── [Intake complete]  → send email (SendGrid) → transfer to human
      └── [Escalation]       → transfer to human immediately
```

---

## Key Design Decisions

**Single agent, not multi-agent.** The intake is a structured linear flow — one LLM with one system prompt handles the full conversation. Complexity lives in the orchestration layer (step tracking, tool calls, safeguards), not in multiple reasoning loops. A multi-agent architecture would add latency and failure surface without adding value here.

**LLM called once per turn.** The conversation history grows each turn (the context window pattern), but the LLM is never called more than once per customer utterance. State-specific rules, field tracking, and eligibility checks all happen in Python code around the LLM call. 

**Step-gated parsing.** State detection only runs when the agent is on the state step — preventing common words like "in" or "my" from being misread as state abbreviations (Indiana, Maine). Each parsing concern is gated to the step where it's relevant.

**Safeguards in orchestration, not prompt.** Crisis detection, prompt injection blocking, and output scanning all run in Python code before/after the LLM call. This means they cannot be overridden by a clever user input — the LLM never even sees the message in an injection attempt.

**Write-only record access.** The agent has no ability to read existing customer records. This is an intentional security boundary: if the LLM had read access, a prompt injection attack could exfiltrate customer data. New intake records are written to disk on completion; the LLM never has access to the database.

**Context-aware goodbye detection.** "That's all" and "no thank you" mean different things during a summary confirmation vs. after an ineligibility message. The goodbye detector splits phrases into unambiguous (always goodbye) and ambiguous (only goodbye outside confirmation steps) categories.

---

## Safeguards Reference

| Safeguard | Trigger | Behavior |
|---|---|---|
| Recording consent | Every call | Hardcoded disclosure before any LLM output |
| Crisis detection | Self-harm / distress keywords | Immediate human transfer, LLM bypassed |
| Prompt injection | "ignore instructions", "act as", etc. | Hardcoded deflection, LLM call skipped |
| Output scanner | System prompt / DB content in response | Response suppressed, human transfer |
| Goodbye (unambiguous) | "bye", "goodbye", "end the call" | Hangup in any context |
| Goodbye (ambiguous) | "that's all", "no thanks" | Hangup only outside confirmation steps |
| Silence timeout | 2 consecutive empty inputs | Human transfer |
| Turn limit | 40 total turns | Human transfer |
| Retry limit | 10 attempts on same step | Human transfer |

---

## File Structure

```
voice-intake-agent/
├── agent.py              # Core orchestration: step tracking, LLM loop, completion
├── safeguards.py         # All safety checks: crisis, injection, output, limits
├── state_rules.py        # State rules lookup tool + city→state resolution
├── state_rules.json      # Age requirements for all 50 states
├── twilio_server.py      # Production voice webhook (Flask + Twilio + SendGrid)
├── run_local.py          # CLI test runner — no Twilio needed
├── requirements.txt
├── Procfile              # Railway deployment config
└── logs/
    └── intake_*.json     # Completed intake records (write-only)
```

---

## Running Locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key
python run_local.py
```

Type responses as the customer. Type `status` at any point to inspect the current session state.

---

## Deploying Your Own Instance

The app is deployed on Railway. To deploy your own:

1. Fork this repo
2. Create a Railway project and connect the repo
3. Add a `Procfile` with: `web: gunicorn twilio_server:app`
4. Set environment variables in Railway:
   ```
   ANTHROPIC_API_KEY
   SENDGRID_API_KEY
   SENDGRID_FROM_EMAIL
   HUMAN_QUEUE_NUMBER   (optional — number to transfer completed calls to)
   ```
5. Get a Twilio number and point its webhook to `https://your-app.railway.app/voice/incoming`

---

## Future Work

**CRM deduplication** — before writing a new record, check if the caller's phone number already exists in the CRM. This lookup should stay in orchestration code (not the LLM) and the result passed to the human advisor at handoff, not surfaced to the agent, to preserve the write-only security boundary.

**Redis session store** — replace the in-memory `active_sessions` dict with Redis for multi-instance production deployment and call resume on drop.

**Mid-call handoff** — handle "let me pass you to my spouse" gracefully by re-collecting the primary contact name without restarting the full intake.

**Richer state rules** — extend `state_rules.json` to include plan availability, network types, open enrollment windows, and Medicaid eligibility thresholds per state.

**STT confidence gating** — route to human if Twilio's transcription confidence falls below a threshold, rather than passing potentially garbled text to the LLM. Currently disabled due to unreliable confidence scores for short answers and numbers.

**AI-assisted plan recommendation** — Before transferring to a specialist, have the agent generate a preliminary plan recommendation based on the collected intake data. The specialist receives both the intake record and the AI's suggested plan(s) as a starting point, reducing lookup time while keeping a human in the loop for final approval and sale.

---

## Stack

| Component | Tool |
|---|---|
| LLM | Claude (Anthropic) |
| Voice / telephony | Twilio |
| STT | Twilio Enhanced Speech |
| TTS | Twilio Polly.Joanna |
| Email | SendGrid |
| Web framework | Flask + Gunicorn |
| Hosting | Railway |