from __future__ import annotations

from pathlib import Path


class LoopbackRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels

    def record_chunk(self, output_path: Path, seconds: int) -> Path:
        import numpy as np
        import soundcard as sc
        import soundfile as sf

        output_path.parent.mkdir(parents=True, exist_ok=True)
        speaker = sc.default_speaker()
        microphone = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        frames = seconds * self.sample_rate
        with microphone.recorder(samplerate=self.sample_rate, channels=self.channels) as recorder:
            audio = recorder.record(numframes=frames)
        audio = np.asarray(audio, dtype=np.float32)
        sf.write(output_path, audio, self.sample_rate)
        return output_path
