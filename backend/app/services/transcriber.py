import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

_model = None


def get_whisper_model():
    """Load and cache the WhisperModel (base, CPU, int8)."""
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("WhisperModel loaded.")
        return _model
    except ImportError:
        logger.info("faster-whisper not installed — Whisper transcription unavailable.")
        return None
    except Exception as exc:
        logger.warning(f"Failed to load WhisperModel: {exc}")
        return None


def transcribe_url(url: str) -> Optional[str]:
    """Download audio from a URL via yt-dlp and transcribe with Whisper.

    Returns the transcript text, or None on any failure.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.info("yt-dlp not installed — audio download unavailable.")
        return None

    model = get_whisper_model()
    if model is None:
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": audio_path,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "128",
                    }
                ],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find the downloaded file
            downloaded = [
                f for f in os.listdir(tmpdir)
                if f.startswith("audio.") and not f.endswith(".%(ext)s")
            ]
            if not downloaded:
                logger.warning(f"No audio file found after yt-dlp download for {url}")
                return None

            filepath = os.path.join(tmpdir, downloaded[0])
            segments, _info = model.transcribe(filepath, beam_size=5)
            text = " ".join(seg.text for seg in segments).strip()
            return text if text else None

    except Exception as exc:
        logger.warning(f"Whisper transcription failed for {url}: {exc}")
        return None


def transcribe_youtube(video_id: str) -> Optional[str]:
    """Transcribe a YouTube video by its video ID."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    return transcribe_url(url)
