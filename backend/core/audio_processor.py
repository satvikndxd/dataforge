"""
Audio Processing Module for multimodal evaluation.
Handles downloading audio, mock Spectrogram/CNN classification, and SpeechRecognition STT.
"""
import io
import logging
import random
import requests
import speech_recognition as sr
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def fetch_audio_bytes(url: str) -> bytes:
    """Download audio to raw bytes in memory."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.error(f"Failed to fetch audio from {url}: {e}")
        return b""

def spectrogram_cnn_classify(audio_bytes: bytes) -> dict:
    """
    Mocked Spectral Feature Extraction & Classification.
    Returns: {"class": "speech", "confidence": float}
    """
    if not audio_bytes:
        return {"class": "unknown", "confidence": 0.0}
        
    # Mocking logic: typically we return speech 80% of the time to ensure the demo works correctly
    is_speech = random.random() < 0.8
    confidence = round(random.uniform(0.7, 0.99), 3)
    
    return {
        "class": "speech" if is_speech else "music_or_noise",
        "confidence": confidence
    }

def perform_stt(audio_bytes: bytes, ext: str) -> str:
    """Run Speech-to-Text on the audio snippet."""
    if not audio_bytes:
        return ""
        
    try:
        audio_io = io.BytesIO(audio_bytes)
        
        # Convert to WAV for SpeechRecognition
        audio_segment = AudioSegment.from_file(audio_io, format=ext)
        out_wav = io.BytesIO()
        audio_segment.export(out_wav, format="wav")
        out_wav.seek(0)
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(out_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        return "" # unreadable/no clear speech
    except sr.RequestError as e:
        logger.error(f"Google STT service error: {e}")
        return ""
    except Exception as e:
        logger.error(f"STT conversion failed: {e}")
        return ""

def process_audio(url: str, context_transcript: str = "") -> dict:
    """
    Full audio pipeline.
    Returns the analysis metadata.
    """
    logger.info(f"Processing audio: {url}")
    audio_bytes = fetch_audio_bytes(url)
    
    # Classification
    classification = spectrogram_cnn_classify(audio_bytes)
    
    ext = "mp3" if ".mp3" in url.lower() else "wav"
    transcript = context_transcript
    
    # Speech-to-text
    if classification["class"] == "speech":
        stt_result = perform_stt(audio_bytes, ext)
        if stt_result:
            transcript = f"{transcript} {stt_result}".strip()
            
    return {
        "audio_url": url,
        "classification": classification["class"],
        "confidence": classification["confidence"],
        "transcript": transcript,
        "ext": ext
    }
