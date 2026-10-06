import math
import struct
from pathlib import Path
import lameenc

rate = 44100
pcm = bytearray()
for index in range(int(rate * 0.85)):
    t = index / rate
    envelope = (1 - math.exp(-t / 0.004)) * math.exp(-t * 7) * min(1, (0.85 - t) / 0.04)
    tone = math.sin(2 * math.pi * 880 * t) + 0.22 * math.sin(2 * math.pi * 1760 * t)
    pcm.extend(struct.pack('<h', int(32767 * 0.22 * envelope * tone)))
encoder = lameenc.Encoder()
encoder.set_bit_rate(128)
encoder.set_in_sample_rate(rate)
encoder.set_channels(1)
encoder.set_quality(2)
encoder.silence()
target = Path(__file__).resolve().parents[1] / 'frontend/static/sounds/arrival.mp3'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(encoder.encode(bytes(pcm)) + encoder.flush())
