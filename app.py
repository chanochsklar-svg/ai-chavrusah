import streamlit as st
import requests
from groq import Groq

# Page Setup
st.set_page_config(page_title="On-Demand AI Chavrusah", page_icon="📜")
st.title("📜 On-Demand AI Chavrusah")
st.caption("Learn Torah anytime, anywhere.")

# Secure Client Memory Setup
if "GROQ_API_KEY" in st.secrets:
    if "client" not in st.session_state:
        st.session_state.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    client = st.session_state.client
else:
    st.error("Please configure your GROQ_API_KEY in the dashboard secrets.")
    st.stop()

# Fixed System Prompt
system_instruction = (
    "You are an expert, patient, and engaging AI Chavrusah (Torah study partner). "
    "Your goal is to learn Jewish texts deeply with the user, following the classical traditional style of study. "
    "Maintain an encouraging, analytical, and thoughtful tone. Focus heavily on textual clarity, conceptual flow, "
    "and extracting practical life wisdom from the text."
)

# Initialize Session Message Arrays
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
        st.session_state.primed = True

# Display Ongoing Chat History
for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.write(text)

st.write("---")
st.subheader("🎤 Speak or Type Your Answer")

# Audio Input Widgets
audio_file = st.audio_input("Click the circle icon to record your voice:")
user_typed = st.chat_input("Or type your response here...")

user_message = None

# Audio Processing via Whisper
if audio_file is not None:
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

# Process message and generate text response
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
        bot_reply = response.choices[0].message.content
        
    with st.chat_message("assistant"):
        st.write(bot_reply)
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    st.session_state.chat_history.append(("assistant", bot_reply))

# --- STABLE MULTILINGUAL AUDIO CONTROLS PANEL ---
st.write("### 🎛️ Audio Controls")

speech_text = st.session_state.chat_history[-1][1] if st.session_state.chat_history else ""
escaped_reply = speech_text.replace("'", "\\'").replace('"', '\\"').replace("\n", " ")

audio_panel_html = f"""
<div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; border: 1px solid #ddd; font-family: sans-serif;">
    <label style="font-weight: bold; display: block; margin-bottom: 5px;">🗣️ Choose & Preview a Voice (Supports English & Hebrew Engines):</label>
    <div style="display: flex; gap: 10px; margin-bottom: 12px;">
        <select id="voiceSelect" style="flex: 3; padding: 8px; border-radius: 4px; border: 1px solid #ccc;"></select>
        <button id="btnTest" style="flex: 1; padding: 8px; background-color: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">🔊 Test Voice</button>
    </div>
    
    <div style="display: flex; gap: 10px;">
        <button id="btnPause" style="flex: 1; padding: 10px; background-color: #ffc107; color: black; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">⏸️ Pause</button>
        <button id="btnResume" style="flex: 1; padding: 10px; background-color: #28a745; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">▶️ Resume</button>
        <button id="btnStop" style="flex: 1; padding: 10px; background-color: #dc3545; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">🛑 Stop</button>
    </div>
</div>

<script>
    var synth = window.speechSynthesis;
    var voiceSelect = document.getElementById('voiceSelect');
    var rawText = "{escaped_reply}";
    
    var savedVoiceIndex = localStorage.getItem('selectedVoiceIndex') || "";

    // Phonic filter maps hard CH sounds into a structure English natural voice modules can pronounce
    function fixTransliteration(text) {{
        return text
            .replace(/Chavrusah/gi, "Khav-roo-sah")
            .replace(/Chavruta/gi, "Khav-roo-tah")
            .replace(/Sukkah/gi, "Soo-kah")
            .replace(/Sukkos/gi, "Soo-kos")
            .replace(/Perek/gi, "Peh-reck")
            .replace(/Sugya/gi, "Soog-yah")
            .replace(/Hashem/gi, "Hah-shem")
            .replace(/ch([aeiou])/gi, "kh$1"); // Converts generic leading 'ch' words to rough 'kh'
    }}

    function populateVoiceList() {{
        var voices = synth.getVoices();
        voiceSelect.innerHTML = '';
        
        // Sort premium/natural voices to the top (Google, Apple, Microsoft natural strings)
        voices.sort(function(a, b) {{
            var aName = a.name.toLowerCase();
            var bName = b.name.toLowerCase();
            if (aName.includes('natural') || aName.includes('google')) return -1;
            if (bName.includes('natural') || bName.includes('google')) return 1;
            return 0;
        }});

        voices.forEach(function(voice, i) {{
            // Pull BOTH English and Hebrew speech modules
            if (voice.lang.includes('en') || voice.lang.includes('he')) {{
                var option = document.createElement('option');
                var labelPrefix = voice.lang.includes('he') ? "🇮🇱 " : "🇺🇸 ";
                option.textContent = labelPrefix + voice.name + ' (' + voice.lang + ')';
                option.value = i;
                if (savedVoiceIndex !== "" && savedVoiceIndex == i) {{
                    option.selected = true;
                }}
                voiceSelect.appendChild(option);
            }}
        }});
    }}

    populateVoiceList();
    if (synth.onvoiceschanged !== undefined) {{
        synth.onvoiceschanged = populateVoiceList;
    }}

    voiceSelect.addEventListener('change', function() {{
        localStorage.setItem('selectedVoiceIndex', voiceSelect.value);
        synth.cancel();
    }});

    // Test Voice Configuration Preview Action
    document.getElementById('btnTest').addEventListener('click', function() {{
        synth.cancel();
        var testText = "Testing this audio configuration. Baruch Hashem, learning Torah with clarity.";
        var voices = synth.getVoices();
        var selectedVoice = voices[voiceSelect.value];
        
        // If it's a native Hebrew voice player, use clean Hebrew test text instead
        if(selectedVoice && selectedVoice.lang.includes('he')) {{
            testText = "בָּרוּךְ הַשֵּׁם, בְּדִיקַת מַעֲרֶכֶת הַקּוֹל שֶׁלְּךָ עָבְרָה בְּהַצְלָחָה.";
        }} else {{
            testText = fixTransliteration(testText);
        }}
        
        var testUtterance = new SpeechSynthesisUtterance(testText);
        if(selectedVoice) {{
            testUtterance.voice = selectedVoice;
        }}
        synth.speak(testUtterance);
    }});

    // Streamlined execution loop for incoming conversation blocks
    if (rawText.trim() !== "" && !window.hasSpoken) {{
        synth.cancel();
        var voices = synth.getVoices();
        var selectedVoice = voices[voiceSelect.value];
        
        var processedText = rawText;
        if (selectedVoice && !selectedVoice.lang.includes('he')) {{
            processedText = fixTransliteration(rawText);
        }}

        var currentUtterance = new SpeechSynthesisUtterance(processedText);
        if(selectedVoice) {{
            currentUtterance.voice = selectedVoice;
        }}
        synth.speak(currentUtterance);
        window.hasSpoken = true;
    }}

    // Media Control Action Handlers
    document.getElementById('btnPause').addEventListener('click', function() {{ synth.pause(); }});
    document.getElementById('btnResume').addEventListener('click', function() {{ synth.resume(); }});
    document.getElementById('btnStop').addEventListener('click', function() {{ synth.cancel(); }});
</script>
"""

st.components.v1.html(audio_panel_html, height=140)
