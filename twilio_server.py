"""
twilio_server.py
----------------
Production voice layer. Handles inbound calls via Twilio webhooks.

On completion: sends intake summary via SendGrid, then transfers to human.
On escalation: transfers to human immediately.
On goodbye:    hangs up.

Environment variables:
  ANTHROPIC_API_KEY         (required)
  TWILIO_ACCOUNT_SID        (required)
  TWILIO_AUTH_TOKEN         (required)
  SENDGRID_API_KEY          (required for email)
  SENDGRID_FROM_EMAIL       (required for email — must be verified in SendGrid)
  HUMAN_QUEUE_NUMBER        (optional — phone/SIP to transfer to)
  FLASK_SECRET_KEY          (optional)
"""

import os
import re
import json
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial

from agent import IntakeSession

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")

active_sessions: dict[str, IntakeSession] = {}

VOICE = "Polly.Joanna"
LANGUAGE = "en-US"
HUMAN_QUEUE_NUMBER = os.environ.get("HUMAN_QUEUE_NUMBER")


# ── TwiML builders ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Strip internal system tokens before sending to TTS."""
    if "INTAKE_COMPLETE:" in text:
        text = text.split("INTAKE_COMPLETE:")[0].strip()
    # Strip any leftover JSON blocks
    text = re.sub(r'\{[^{}]*\}', '', text, flags=re.DOTALL).strip()
    return text.strip()


def twiml_listen(text: str) -> str:
    """Say something and listen for a response."""
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice/respond",
        method="POST",
        speech_timeout="auto",
        language=LANGUAGE,
        speech_model="phone_call",
        enhanced="true",
        hints=(
            "one, two, three, four, five, six, seven, eight, nine, ten, "
            "twenty, thirty, forty, fifty, hundred, thousand, "
            "dollars, per month, monthly, budget, "
            "HMO, PPO, no preference, "
            "yes, no, correct, that's right, "
            "California, Texas, New York, Florida, "
            "at sign, dot com, dot net, gmail, yahoo, outlook"
        )
    )
    gather.say(_clean_text(text), voice=VOICE)
    response.append(gather)
    response.say("I didn't catch that — could you please repeat?", voice=VOICE)
    response.redirect("/voice/respond")
    return str(response)


def twiml_hangup(text: str) -> str:
    response = VoiceResponse()
    response.say(_clean_text(text), voice=VOICE)
    response.hangup()
    return str(response)


def twiml_transfer(text: str) -> str:
    response = VoiceResponse()
    response.say(_clean_text(text), voice=VOICE)
    if HUMAN_QUEUE_NUMBER:
        dial = Dial()
        dial.number(HUMAN_QUEUE_NUMBER)
        response.append(dial)
    else:
        response.say("Connecting you now. Please hold.", voice=VOICE)
        response.hangup()
    return str(response)


# ── Email via SendGrid ─────────────────────────────────────────────────────────

def send_intake_email(record: dict) -> bool:
    """
    Sends intake summary to the customer via SendGrid.
    Requires SENDGRID_API_KEY and SENDGRID_FROM_EMAIL env vars.
    The from email must be verified as a Single Sender in SendGrid.
    """
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
    except ImportError:
        print("[EMAIL] sendgrid package not installed.")
        return False

    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL")

    if not api_key or not from_email:
        print("[EMAIL] SendGrid not configured — skipping.")
        return False

    to_email = record.get("email")
    if not to_email:
        print("[EMAIL] No email in record — skipping.")
        return False

    first_name = record.get("first_name", "there")

    body = "\n".join([
        f"Hi {first_name},",
        "",
        "Thank you for calling HealthBridge Insurance.",
        "A specialist will be in touch with you shortly.",
        "",
        "── Your Intake Summary ──────────────────────────────",
        f"Name:            {record.get('first_name')} {record.get('last_name')}",
        f"Coverage type:   {record.get('coverage_type')}",
        f"State:           {record.get('state')}",
        f"Monthly budget:  {record.get('budget_monthly')}",
        f"Plan preference: {record.get('hmo_preference')}",
        f"Total insured:   {record.get('total_insured')}",
        "",
        "If anything looks incorrect, please let your specialist know.",
        "",
        "── Full Record ───────────────────────────────────────",
        json.dumps(record, indent=2),
        "",
        "HealthBridge Insurance",
    ])

    try:
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        mail = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=f"Your HealthBridge Insurance Intake Summary — {first_name}",
            plain_text_content=body
        )
        response = sg.send(mail)
        print(f"[EMAIL] Sent to {to_email} — status: {response.status_code}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")
        return False


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/voice/incoming", methods=["POST"])
def incoming_call():
    call_sid = request.form.get("CallSid", "unknown")
    caller = request.form.get("From", "unknown")
    print(f"\n[CALL] Incoming from {caller} — SID: {call_sid}")

    intake = IntakeSession(session_id=call_sid[:8])
    active_sessions[call_sid] = intake

    opening = intake.get_opening_line()
    print(f"[AGENT] {opening}")
    return twiml_listen(opening)


@app.route("/voice/respond", methods=["POST"])
def handle_response():
    call_sid = request.form.get("CallSid", "unknown")
    speech_result = request.form.get("SpeechResult", "").strip()
    confidence_raw = request.form.get("Confidence", "1.0")

    try:
        confidence = float(confidence_raw)
    except ValueError:
        confidence = 1.0

    print(f"\n[CUSTOMER] \"{speech_result}\" (confidence: {confidence:.2f})")

    intake = active_sessions.get(call_sid)
    if not intake:
        print(f"[WARNING] No session for {call_sid} — creating new one")
        intake = IntakeSession(session_id=call_sid[:8])
        active_sessions[call_sid] = intake

    agent_response = intake.process_turn(speech_result)
    print(f"[AGENT] {agent_response}")

    # Customer said goodbye
    if intake.call_ended:
        _cleanup_session(call_sid, reason="customer_goodbye")
        return twiml_hangup(agent_response)

    # Intake complete — send email then transfer
    if intake.complete:
        print(f"[SYSTEM] Intake complete — sending email and transferring")
        if intake.final_record:
            send_intake_email(intake.final_record)
        _cleanup_session(call_sid, reason="complete")
        return twiml_transfer(agent_response)

    # Escalation
    if intake.escalated:
        print(f"[SYSTEM] Escalating — reason: {intake.escalation_reason}")
        _cleanup_session(call_sid, reason=f"escalated_{intake.escalation_reason}")
        return twiml_transfer(agent_response)

    return twiml_listen(agent_response)


@app.route("/voice/status", methods=["POST"])
def call_status():
    call_sid = request.form.get("CallSid")
    status = request.form.get("CallStatus")
    duration = request.form.get("CallDuration", "unknown")
    print(f"[STATUS] Call {call_sid} ended — status: {status}, duration: {duration}s")

    if call_sid in active_sessions:
        intake = active_sessions.pop(call_sid)
        if not intake.complete and not intake.call_ended and not intake.escalated:
            print(f"[WARNING] Call dropped mid-intake at step: {intake.current_step}")

    return "", 204


@app.route("/health")
def health():
    return {
        "status": "ok",
        "active_sessions": len(active_sessions),
        "human_queue_configured": bool(HUMAN_QUEUE_NUMBER),
        "email_configured": bool(os.environ.get("SENDGRID_API_KEY")),
    }


def _cleanup_session(call_sid: str, reason: str):
    intake = active_sessions.pop(call_sid, None)
    if intake:
        status = intake.get_status()
        print(f"[CLEANUP] Session {call_sid} closed — reason: {reason}, "
              f"turns: {status['total_turns']}, "
              f"fields filled: {len(status['fields_filled'])}/12")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\nHealthBridge Intake Server starting on port {port}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set")
    if not os.environ.get("SENDGRID_API_KEY"):
        print("NOTE: SENDGRID_API_KEY not set — emails will not be sent")
    if not HUMAN_QUEUE_NUMBER:
        print("NOTE: HUMAN_QUEUE_NUMBER not set — calls will hang up after transfer message")
    app.run(host="0.0.0.0", port=port)