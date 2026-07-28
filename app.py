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
# ElevenLabs (optional) — voice list is pulled live from the user's own
# ElevenLabs account so the picker always matches what's actually available
# to them, rather than a hardcoded guess. Defined early since session-state
# initialization below needs to call fetch_elevenlabs_voices().
# ----------------------------------------------------------------------------
DEFAULT_VOICE_ID = "JbEbCmsvCUsY6W7Z4v69"  # George — used if nothing is selected yet


def fetch_elevenlabs_voices():
    if not ELEVENLABS_ENABLED:
        return []
    try:
        res = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": st.secrets["ELEVENLABS_API_KEY"]},
            timeout=10,
        )
        if res.status_code == 200:
            voices = res.json().get("voices", [])
            return [(v.get("name", v["voice_id"]), v["voice_id"]) for v in voices]
    except Exception:
        pass
    return []


def generate_elevenlabs_speech(text, voice_id=None):
    if not ELEVENLABS_ENABLED:
        return None
    voice_id = voice_id or st.session_state.get("voice_id", DEFAULT_VOICE_ID)
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
SYSTEM_INSTRUCTION = """You are an expert, patient, and rigorous AI Chavrusah (Torah study partner). You are studying
one specific line of text at a time with the user — never the whole passage at once. The user may bring any text:
Chumash with Rashi, Mishnah, Talmud, or others — follow whatever they bring up.

Follow this protocol on every single turn, without exception:
1. Respond to what the user just said — briefly affirm, correct, or build on it in 2-4 sentences.
2. Never lecture for more than a short paragraph before stopping.
3. ALWAYS end your reply with exactly ONE probing question about the CURRENT line — asking the user
   to explain a word, infer a motive, compare a commentary, or predict what comes next.
4. Do NOT move on to the next line yourself. You will be told explicitly by the system when it is time
   to advance to a new line, along with that new line's text. Until then, keep probing the current line
   from different angles if the user's answers are shallow.
5. Keep tone conversational and spoken, like two people learning together at a table — not a lecture.
6. Mirror the user's language: if their most recent message is written in Hebrew, reply entirely in Hebrew;
   if it's in English, reply entirely in English. You will be given both the English translation and the
   original Hebrew of the current line — feel free to quote short Hebrew phrases from the original even
   when replying in English, to point at a specific word, but keep your own reply in the user's language.

Accuracy is non-negotiable: when citing a named commentator (Rashi, Tosafot, Ramban, etc.), a halachic ruling,
or translating a Hebrew/Aramaic term, be precise. If you are not confident of the exact wording, source, or
citation, say so plainly rather than inventing or guessing — never present speculation as settled halacha or
established commentary.

You are a study partner, not an answer key. If the user gives a weak, partial, or logically shaky answer,
challenge it directly — point out the gap or tension, and push them to defend or refine their reasoning
before you supply the fuller explanation yourself. Pause and check that they've actually understood before
moving forward; don't just keep talking past a shaky answer.
"""


def steering_reminder(segment_ref: str, en_text: str, he_text: str, is_new_segment: bool) -> str:
    """A short, ephemeral system-role reminder injected right before each API
    call (not permanently stored in the visible history). Keeps the model
    anchored to the protocol and to the exact line currently being studied,
    which counters instruction drift as the conversation grows."""
    source_parts = []
    if en_text:
        source_parts.append(f'English: "{en_text}"')
    if he_text:
        source_parts.append(f'Hebrew: "{he_text}"')
    source_block = " | ".join(source_parts) if source_parts else "(source text unavailable)"

    language_note = "Reply in whichever language — Hebrew or English — the user's last message was written in."

    if is_new_segment:
        return (
            f"[SYSTEM STATE] You may now advance. The new current line is {segment_ref}. "
            f"Source text — {source_block}. Briefly bridge from the prior discussion, introduce this line, "
            f"and end with one question about it, per the protocol. {language_note}"
        )
    return (
        f"[SYSTEM STATE] Current line remains {segment_ref}. Source text — {source_block}. Do not advance. "
        f"Respond per the protocol: brief reaction, then exactly one question about this line. {language_note}"
    )


# ----------------------------------------------------------------------------
# Session State
# ----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "segments" not in st.session_state:
    st.session_state.segments = []  # list of (ref, english_text, hebrew_text)
if "segment_index" not in st.session_state:
    st.session_state.segment_index = 0
if "title" not in st.session_state:
    st.session_state.title = ""
if "voice_options" not in st.session_state:
    st.session_state.voice_options = fetch_elevenlabs_voices() if ELEVENLABS_ENABLED else []
if "voice_id" not in st.session_state:
    st.session_state.voice_id = (
        st.session_state.voice_options[0][1] if st.session_state.voice_options else DEFAULT_VOICE_ID
    )

MAX_HISTORY_MESSAGES = 16  # trim what we send to the API to fight context dilution


def trimmed_messages():
    """Always send the system prompt + the steering reminder + only the most
    recent turns, rather than the entire growing transcript. This keeps the
    protocol close to the end of the prompt, where models weight it most."""
    system_msg = st.session_state.messages[0]
    rest = st.session_state.messages[1:]
    return [system_msg] + rest[-MAX_HISTORY_MESSAGES:]


# ----------------------------------------------------------------------------
# Sefaria: fetch text as discrete segments, in BOTH English and Hebrew, so the
# model always has the original alongside the translation regardless of which
# language the user studies in.
# ----------------------------------------------------------------------------
def _fetch_sefaria_version(url, version_param, ref):
    """Fetch one language version and return (title, list_of_segment_strings)."""
    try:
        res = requests.get(url, params={"version": version_param}, timeout=10)
        if res.status_code != 200:
            return None, []
        data = res.json()
        title = data.get("title", ref)
        versions = data.get("versions", [])
        if not versions:
            return title, []
        text_data = versions[0].get("text", [])
        if isinstance(text_data, list):
            return title, [
                (" ".join(item) if isinstance(item, list) else str(item)).strip()
                for item in text_data
            ]
        else:
            seg_text = str(text_data).strip()
            return title, [seg_text] if seg_text else []
    except Exception:
        return None, []


def fetch_sefaria_segments(ref):
    url = f"https://www.sefaria.org/api/v3/texts/{ref.strip().replace(' ', '%20')}"
    title_en, en_list = _fetch_sefaria_version(url, "english", ref)
    title_he, he_list = _fetch_sefaria_version(url, "hebrew", ref)
    title = title_en or title_he or ref

    total = max(len(en_list), len(he_list))
    if total == 0:
        return None, []

    segments = []
    for i in range(total):
        en_text = en_list[i] if i < len(en_list) else ""
        he_text = he_list[i] if i < len(he_list) else ""
        if en_text or he_text:
            segments.append((f"{ref}:{i + 1}", en_text, he_text))
    return title, segments


def call_model(is_new_segment: bool):
    ref, en_text, he_text = st.session_state.segments[st.session_state.segment_index]
    reminder = {"role": "system", "content": steering_reminder(ref, en_text, he_text, is_new_segment)}
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

    if ELEVENLABS_ENABLED:
        st.subheader("🔊 Voice")
        if st.session_state.voice_options:
            names = [name for name, _ in st.session_state.voice_options]
            id_by_name = dict(st.session_state.voice_options)
            current_name = next(
                (n for n, vid in st.session_state.voice_options if vid == st.session_state.voice_id),
                names[0],
            )
            chosen_name = st.selectbox("Choose a voice", names, index=names.index(current_name))
            st.session_state.voice_id = id_by_name[chosen_name]
        else:
            st.caption("Couldn't load your ElevenLabs voice list — using a default voice.")

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

                ref, en_text, he_text = segments[0]
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
            ref, en_text, he_text = st.session_state.segments[st.session_state.segment_index]
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

_cur_ref, _cur_en, _cur_he = st.session_state.segments[st.session_state.segment_index]
with st.expander(f"📖 Current line — {_cur_ref}", expanded=True):
    if _cur_he:
        st.markdown(
            f"<div style='direction: rtl; text-align: right; font-size: 1.15em;'>{_cur_he}</div>",
            unsafe_allow_html=True,
        )
    if _cur_en:
        st.write(_cur_en)

for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.write(text)

st.write("---")
col1, col2 = st.columns([1, 5])
with col1:
    audio_file = st.audio_input("🎤", key="voice_input")
with col2:
    user_typed = st.chat_input("Type in Hebrew or English...")

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
ADVANCE_PHRASES = {
    "next", "next line", "let's move on", "move on", "continue", "keep going", "next verse",
    "הבא", "המשך", "בוא נמשיך", "קדימה", "לשורה הבאה", "השורה הבאה",
}

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
