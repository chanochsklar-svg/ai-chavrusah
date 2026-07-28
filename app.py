import streamlit as st
import requests
from groq import Groq

# ----------------------------------------------------------------------------
# Page Setup
# ----------------------------------------------------------------------------
st.set_page_config(page_title="On-Demand AI Chavrusah", page_icon="📜", layout="centered")
st.title("📜 On-Demand AI Chavrusah")
st.caption("Your personal, conversational Torah study partner.")

# ----------------------------------------------------------------------------
# Secure Client Setup (ElevenLabs is optional — voice reply just gets skipped
# if it's not configured, instead of killing the whole app)
# ----------------------------------------------------------------------------
if "GROQ_API_KEY" not in st.secrets:
    st.error("Please configure GROQ_API_KEY in your Streamlit dashboard secrets.")
    st.stop()

if "client" not in st.session_state:
    st.session_state.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
client = st.session_state.client

ELEVENLABS_ENABLED = "ELEVENLABS_API_KEY" in st.secrets

# ----------------------------------------------------------------------------
# The Chavrusah Protocol
#
# This is the key change. Instead of a soft "ask good questions" suggestion,
# this is a strict, structural contract for how every single reply must be
# shaped. Long conversations dilute a system prompt's influence, so we also
# re-inject a short reminder of this contract before every model call (see
# `steering_reminder()` below) instead of relying on it being said once at
# the very start of the chat.
# ----------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are an expert, warm, patient AI Chavrusah (Torah study partner). You are studying
one specific line of text at a time with the user — never the whole passage at once.

Follow this protocol on every single turn, without exception:
1. Respond to what the user just said — briefly correct, affirm, or build on it in 2-4 sentences.
2. Never lecture for more than a short paragraph before stopping.
3. ALWAYS end your reply with exactly ONE probing question about the CURRENT line — asking the user
   to explain a word, infer a motive, compare a commentary, or predict what comes next.
4. Do NOT move on to the next line yourself. You will be told explicitly by the system when it is time
   to advance to a new line, along with that new line's text. Until then, keep probing the current line
   from different angles if the user's answers are shallow.
5. Keep tone conversational and spoken, like two people learning together at a table — not a lecture.

You are a study partner, not an answer key. If the user gives a weak or partial answer, gently push back
and ask them to go deeper before you supply the full explanation yourself.
"""


def steering_reminder(segment_ref: str, segment_text: str, is_new_segment: bool) -> str:
    """A short, ephemeral system-role reminder injected right before each API
    call (not permanently stored in the visible history). Keeps the model
    anchored to the protocol and to the exact line currently being studied,
    which counters instruction drift as the conversation grows."""
    if is_new_segment:
        return (
            f"[SYSTEM STATE] You may now advance. The new current line is {segment_ref}: "
            f"\"{segment_text}\". Briefly bridge from the prior discussion, introduce this line, "
            f"and end with one question about it, per the protocol."
        )
    return (
        f"[SYSTEM STATE] Current line remains {segment_ref}: \"{segment_text}\". Do not advance. "
        f"Respond per the protocol: brief reaction, then exactly one question about this line."
    )


# ----------------------------------------------------------------------------
# Session State
# ----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "segments" not in st.session_state:
    st.session_state.segments = []  # list of (ref, text)
if "segment_index" not in st.session_state:
    st.session_state.segment_index = 0
if "title" not in st.session_state:
    st.session_state.title = ""

MAX_HISTORY_MESSAGES = 16  # trim what we send to the API to fight context dilution


def trimmed_messages():
    """Always send the system prompt + the steering reminder + only the most
    recent turns, rather than the entire growing transcript. This keeps the
    protocol close to the end of the prompt, where models weight it most."""
    system_msg = st.session_state.messages[0]
    rest = st.session_state.messages[1:]
    return [system_msg] + rest[-MAX_HISTORY_MESSAGES:]


# ----------------------------------------------------------------------------
# Sefaria: fetch text as discrete segments, not one flattened blob
# ----------------------------------------------------------------------------
def fetch_sefaria_segments(ref):
    url = f"https://www.sefaria.org/api/v3/texts/{ref.strip().replace(' ', '%20')}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return None, []
        data = res.json()
        title = data.get("title", ref)
        for v in data.get("versions", []):
            if v.get("language") == "en":
                text_data = v.get("text", [])
                if isinstance(text_data, list):
                    segments = []
                    for i, item in enumerate(text_data, start=1):
                        seg_text = " ".join(item) if isinstance(item, list) else str(item)
                        seg_text = seg_text.strip()
                        if seg_text:
                            segments.append((f"{ref}:{i}", seg_text))
                    return title, segments
                else:
                    return title, [(ref, str(text_data).strip())]
        return title, []
    except Exception:
        return None, []


# ----------------------------------------------------------------------------
# ElevenLabs (optional)
# ----------------------------------------------------------------------------
def generate_elevenlabs_speech(text):
    if not ELEVENLABS_ENABLED:
        return None
    voice_id = "JbEbCmsvCUsY6W7Z4v69"  # George
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": st.secrets["ELEVENLABS_API_KEY"],
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.85},
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception:
        pass
    return None


def call_model(is_new_segment: bool):
    ref, text = st.session_state.segments[st.session_state.segment_index]
    reminder = {"role": "system", "content": steering_reminder(ref, text, is_new_segment)}
    api_messages = trimmed_messages() + [reminder]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=api_messages,
        temperature=0.6,
    )
    return response.choices[0].message.content


# ----------------------------------------------------------------------------
# Sidebar: text selection + manual line advance
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("📚 Study Setup")
    text_to_study = st.text_input("What text to learn?", placeholder="e.g., Genesis 1, Sukkah 2a")

    if st.button("Load Text & Start Learning") and text_to_study:
        with st.spinner("Fetching text from Sefaria..."):
            title, segments = fetch_sefaria_segments(text_to_study)
            if not segments:
                st.error("Text not found or could not be loaded.")
            else:
                st.session_state.segments = segments
                st.session_state.segment_index = 0
                st.session_state.title = title
                st.session_state.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
                st.session_state.chat_history = []

                ref, seg_text = segments[0]
                opening_prompt = (
                    f"We are beginning to study {title}. Introduce the topic in one sentence, "
                    f"then follow the protocol for the current line."
                )
                st.session_state.messages.append({"role": "user", "content": opening_prompt})
                bot_reply = call_model(is_new_segment=True)
                st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                st.session_state.chat_history.append(("assistant", bot_reply))
                st.rerun()

    if st.session_state.segments:
        total = len(st.session_state.segments)
        idx = st.session_state.segment_index
        st.write(f"**{st.session_state.title}**")
        st.write(f"Line {idx + 1} of {total}")
        st.progress((idx + 1) / total)

        if st.button("⏭ Advance to next line") and idx + 1 < total:
            st.session_state.segment_index += 1
            ref, seg_text = st.session_state.segments[st.session_state.segment_index]
            advance_note = {"role": "user", "content": "Let's move to the next line."}
            st.session_state.messages.append(advance_note)
            bot_reply = call_model(is_new_segment=True)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            st.session_state.chat_history.append(("assistant", bot_reply))
            st.rerun()

# ----------------------------------------------------------------------------
# Main chat interface
# ----------------------------------------------------------------------------
if not st.session_state.segments:
    st.info("Enter a text reference in the sidebar to begin studying.")
    st.stop()

for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.write(text)

st.write("---")
col1, col2 = st.columns([1, 5])
with col1:
    audio_file = st.audio_input("🎤", key="voice_input")
with col2:
    user_typed = st.chat_input("Type your response or question here...")

user_message = None

if audio_file is not None and st.session_state.get("last_audio") != audio_file:
    st.session_state.last_audio = audio_file
    with st.spinner("Listening..."):
        try:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=("audio.wav", audio_file.read()),
            )
            user_message = transcription.text
        except Exception as e:
            st.error(f"Audio transcription error: {e}")

if user_typed:
    user_message = user_typed

# A small, deterministic advance trigger: if the user's own words signal
# they're ready to move on, treat it the same as clicking the sidebar button.
ADVANCE_PHRASES = {"next", "next line", "let's move on", "move on", "continue", "keep going", "next verse"}

if user_message:
    st.session_state.chat_history.append(("user", user_message))
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.write(user_message)

    wants_advance = user_message.strip().lower() in ADVANCE_PHRASES
    can_advance = st.session_state.segment_index + 1 < len(st.session_state.segments)

    if wants_advance and can_advance:
        st.session_state.segment_index += 1

    with st.spinner("Chavrusah is thinking..."):
        latest_bot_reply = call_model(is_new_segment=wants_advance and can_advance)

    st.session_state.messages.append({"role": "assistant", "content": latest_bot_reply})
    st.session_state.chat_history.append(("assistant", latest_bot_reply))

    with st.chat_message("assistant"):
        st.write(latest_bot_reply)
        audio_bytes = generate_elevenlabs_speech(latest_bot_reply)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
        elif not ELEVENLABS_ENABLED:
            st.caption("🔇 Voice narration off — add ELEVENLABS_API_KEY to enable it.")

    st.rerun()
