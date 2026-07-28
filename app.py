import streamlit as st
import requests
from groq import Groq

# Page Setup
st.set_page_config(page_title="On-Demand AI Chavrusah", page_icon="📜")
st.title("📜 On-Demand AI Chavrusah")
st.caption("Learn Torah anytime, anywhere.")

# Secure Client Setup
if "GROQ_API_KEY" in st.secrets and "ELEVENLABS_API_KEY" in st.secrets:
    if "client" not in st.session_state:
        st.session_state.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    client = st.session_state.client
else:
    st.error("Please configure both GROQ_API_KEY and ELEVENLABS_API_KEY in the dashboard secrets.")
    st.stop()

# System Prompt
system_instruction = (
    "You are an expert, patient, and engaging AI Chavrusah (Torah study partner). "
    "Your goal is to learn Jewish texts deeply with the user, following the classical traditional style of study. "
    "Maintain an encouraging, analytical, and thoughtful tone. Focus heavily on textual clarity, conceptual flow, "
    "and extracting practical life wisdom from the text."
)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": system_instruction}]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Sefaria Text Loader Block
def fetch_sefaria(ref):
    url = f"https://www.sefaria.org/api/v3/texts/{ref.strip().replace(' ', '%20')}"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        en_text = ""
        if data.get("versions") and len(data["versions"]) > 0:
            text_data = data["versions"][0].get("text", [])
            if isinstance(text_data, list):
                flat_list = [
                    " ".join(item) if isinstance(item, list) else str(item) 
                    for item in text_data
                ]
                en_text = " ".join(flat_list)
            else:
                en_text = str(text_data)
            return f"Source: {data.get('title', ref)}\n\nText: {en_text}"
    return "Text not found."

# Text Selection Setup
text_to_study = st.text_input("What text would you like to learn today?", placeholder="e.g., Sukkah 2a, Genesis 1")

# Helper function to generate real human speech via ElevenLabs with Safety Net
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
        "voice_settings": {
            "stability": 0.6,
            "similarity_boost": 0.85
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception:
        pass 
    return None

# Initialize text context/priming
if text_to_study and "primed" not in st.session_state:
    with st.spinner("Fetching from Sefaria..."):
        source_material = fetch_sefaria(text_to_study)
        priming_prompt = f"Here is our text:\n\n{source_material}\n\nIntroduce yourself, read/translate the first line, and kick off our conversation."
        st.session_state.messages.append({"role": "user", "content": priming_prompt})
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=st.session_state.messages,
            temperature=0.7,
        )
        bot_reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": bot_reply})
        st.session_state.chat_history.append(("assistant", bot_reply))
        
        # Generate initial audio for the priming message
        audio_bytes = generate_elevenlabs_speech(bot_reply)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
            
        st.session_state.primed = True

# Display Ongoing Chat History
for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.write(text)

st.write("---")
st.subheader("🎤 Speak or Type Your Answer")

# Inputs
audio_file = st.audio_input("Click the circle icon to record your voice:", key="audio_input")
user_typed = st.chat_input("Or type your response here...")

user_message = None

# Handle Audio Input Transcription via Groq Whisper
if audio_file is not None:
    # Use session state to prevent reprocessing the exact same audio file on rerun
    if st.session_state.get("last_audio_file") != audio_file:
        st.session_state.last_audio_file = audio_file
        with st.spinner("Transcribing your voice..."):
            try:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("audio.wav", audio_file.read()),
                )
                user_message = transcription.text
            except Exception as e:
                st.error(f"Voice processing error: {e}")

if user_typed:
    user_message = user_typed

# Process message and generate text response if a new user input exists
if user_message:
    with st.chat_message("user"):
        st.write(user_message)
    st.session_state.chat_history.append(("user", user_message))
    st.session_state.messages.append({"role": "user", "content": user_message})

    with st.spinner("Chavrusah is thinking..."):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=st.session_state.messages,
            temperature=0.7,
        )
        latest_bot_reply = response.choices[0].message.content
        
    with st.chat_message("assistant"):
        st.write(latest_bot_reply)
        
    st.session_state.messages.append({"role": "assistant", "content": latest_bot_reply})
    st.session_state.chat_history.append(("assistant", latest_bot_reply))

    # Generate speech only for the newly minted reply
    with st.spinner("🔊 Generating natural human voice narration..."):
        audio_bytes = generate_elevenlabs_speech(latest_bot_reply)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
        else:
            st.warning("Voice engine unavailable. Reading chat in text mode!")
