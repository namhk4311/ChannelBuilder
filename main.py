"""Demo standalone: gọi ElevenLabs TTS rồi play local. Không phải production code path."""
from elevenlabs.client import ElevenLabs
from elevenlabs.play import play

from config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL_ID, ELEVENLABS_VOICE_ID

elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)

audio = elevenlabs.text_to_speech.convert(
    text="Hello các con vợ, chúc các con vợ một ngày tốt lành hahahaha....",
    voice_id=ELEVENLABS_VOICE_ID,
    model_id=ELEVENLABS_MODEL_ID,
    output_format="mp3_44100_128",
)

play(audio)
