import streamlit as st
import requests
from google import genai
from google.genai import types

st.set_page_config(page_title="AI Chavrusah", page_icon="📜")

# Title of your app
st.title("📜 On-Demand AI Chavrusah")
st.caption("Learn Torah anytime, anywhere.")

# Securely initialize Gemini Client from deployment environment variables
if "GEMINI_API_KEY" in st.secrets:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Please configure your GEMINI_API_KEY in the dashboard secrets.")
    st.stop()

# Initialize session history so the app remembers the conversation
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    system_instruction = """
    You are a warm, brilliant, and deeply collaborative Yeshiva Chavrusah (study partner).
    You learn AS A PEER, not as a teacher. Translate phrases naturally, explain meaning simply,
    and share classic commentary (like Rashi). Keep it short and highly conversational.
    Warmly defer practical halachic questions to a Rabbi.
    """
    st.session_state.chat = client.chats.create(
        model="gemini-3.5-flash",
        config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.7)
    )

def fetch_sefaria(ref):
    url = f"https://www.sefaria.org/api/v3/texts/{ref.strip().replace(' ', '%20')}"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        en_text = ""
        # Check if version data exists safely
        if data.get("versions") and len(data["versions"]) > 0:
            text_data = data["versions"][0].get("text", [])
            if isinstance(text_data, list):
                # Flattens nested list blocks if Sefaria returns list-of-lists
                flat_list = [
                    " ".join(item) if isinstance(item, list) else str(item) 
                    for item in text_data
                ]
                en_text = " ".join(flat_list)
            else:
                en_text = str(text_data)
            return f"Source: {data.get('title', ref)}\n\nText: {en_text}"
    return "Text not found."

# 1. Text Selection Setup
text_to_study = st.text_input("What text would you like to learn today?", placeholder="e.g., Genesis 1, Pirkei Avot 1")

if text_to_study and "primed" not in st.session_state:
    with st.spinner("Fetching from Sefaria..."):
        source_material = fetch_sefaria(text_to_study)
        priming_prompt = f"Here is our text:\n\n{source_material}\n\nIntroduce yourself, read/translate the first line, and kick off our conversation."
        response = st.session_state.chat.send_message(priming_prompt)
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        st.session_state.primed = True

# 2. Render Chat Interface
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# 3. Audio & Text Interaction Input
user_input = st.chat_input("Type or use your keyboard's microphone button to talk out loud...")

if user_input:
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = st.session_state.chat.send_message(user_input)
            st.write(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
