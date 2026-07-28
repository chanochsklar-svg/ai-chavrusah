import streamlit as st
import requests
from groq import Groq

# Page Setup - Clean, wide chat layout
st.set_page_config(page_title="On-Demand AI Chavrusah", page_icon="📜", layout="centered")
st.title("📜 On-Demand AI Chavrusah")
st.caption("Your personal, conversational Torah study partner.")

# Secure Client Setup
if "GROQ_API_KEY" in st.secrets and "ELEVENLABS_API_KEY" in st.secrets:
    if "client" not in st.session_state:
        st.session_state.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    client = st.session_state.client
else:
    st.error("Please configure both GROQ_API_KEY and ELEVENLABS_API_KEY in your Streamlit dashboard secrets.")
    st.stop()

# System Prompt for a true interactive Chavrusah
system_instruction = (
    "You are an expert, patient, and engaging AI Chavrusah (Torah study partner). "
    "Your goal is to learn Jewish texts deeply with the user in a natural, conversational back-and-forth dialogue. "
    "Ask thought-provoking questions, check for understanding, break down concepts clearly, and keep your responses "
    "concise and engaging so it feels like a real spoken study session."
)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": system_instruction}]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Reliable Sefaria Text Loader
def fetch_sefaria(ref):
    url = f"https://www.sefaria.org/api/v3/texts/{ref.strip().replace(' ', '%20')}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            en_text = ""
            if data.get("versions"):
                for v in data["versions"]:
                    if v.get("language") == "en":
                        text_data = v.get("text", [])
                        if isinstance(text_data, list):
                            flat_list = [
                                " ".join(item) if isinstance(item, list) else str(item) 
                                for item in text_data
                            ]
                            en_text = " ".join(flat_list)
                        else:
                            en_text = str(text_data)
                        break
            if en_text:
                return f"Source: {data.get('title', ref)}\n\nText: {en_text}"
    except Exception:
        pass
    return "Text not found or could not be loaded."

# ElevenLabs Speech Generation
def generate_elevenlabs_speech(text):
    voice_id = "JbEbCmsvCUsY6W7Z4v69" # George
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": st.secrets["ELEVENLABS_API_KEY"]
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.85}
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception:
        pass
    return None

# --- SIDEBAR FOR TEXT SELECTION (Keeps main screen clean for chat) ---
with st.sidebar:
    st.header("📚 Study Setup")
    text_to_study = st.text_input("What text to learn?", placeholder="e.g., Sukkah 2a, Genesis 1")
    
    if st.button("Load Text & Start Learning") and text_to_study:
        with st.spinner("Fetching text from Sefaria..."):
            source_material = fetch_sefaria(text_to_study)
            priming_prompt = f"Here is our text source:\n\n{source_material}\n\nIntroduce yourself briefly, explain the first line, and ask me a thought-provoking opening question to start our learning."
            st.session_state.messages.append({"role": "user", "content": priming_prompt})
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=st.session_state.messages,
                temperature=0.7,
            )
            bot_reply = response.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            st.session_state.chat_history.append(("assistant", bot_reply))
            st.rerun()

# --- MAIN CHAT INTERFACE ---
# Display clean conversational history
for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.write(text)

# Unified Input Container (Audio + Text like a real chat app)
st.write("---")
col1, col2 = st.columns([1, 5])

with col1:
    audio_file = st.audio_input("🎤", key="voice_input")

with col2:
    user_typed = st.chat_input("Type your response or question here...")

user_message = None

# Process Voice input if recorded
if audio_file is not None:
    if st.session_state.get("last_audio") != audio_file:
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

# Handle back-and-forth message cycle
if user_message:
    # Append user message
    st.session_state.chat_history.append(("user", user_message))
    st.session_state.messages.append({"role": "user", "content": user_message})
    
    with st.chat_message("user"):
        st.write(user_message)

    # Generate assistant reply
    with st.spinner("Chavrusah is thinking..."):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=st.session_state.messages,
            temperature=0.7,
        )
        latest_bot_reply = response.choices[0].message.content
        
    st.session_state.messages.append({"role": "assistant", "content": latest_bot_reply})
    st.session_state.chat_history.append(("assistant", latest_bot_reply))
    
    with st.chat_message("assistant"):
        st.write(latest_bot_reply)
        # Generate and play voice response automatically
        audio_bytes = generate_elevenlabs_speech(latest_bot_reply)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)

    st.rerun()
