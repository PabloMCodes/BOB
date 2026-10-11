"""Embed a short mono PCM16 WAV in the standalone controller sketch.

Generate the source locally with eSpeak NG 1.50:
  espeak-ng -v en-us -s 145 -w /tmp/missing-ppe.wav 'Missing P P E.'
  python -m tools.embed_bench_speech /tmp/missing-ppe.wav

The WAV stays outside Git. The sketch contains signed 8-bit PCM in flash,
resampled to 16 kHz and scaled at playback to peak <= 8000 in PCM16 units.
Uses Python 3.10's standard library; no runtime TTS or audio transfer is needed.
"""
import argparse
from array import array
import audioop
import hashlib
from pathlib import Path
import sys
import wave


START = '// BEGIN GENERATED MISSING PPE SPEECH'
END = '// END GENERATED MISSING PPE SPEECH'
SKETCH = Path(__file__).resolve().parents[1] / 'hardware/esp32/BOB_ControllerBench/BOB_ControllerBench.ino'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav', type=Path)
    args = parser.parse_args()
    with wave.open(str(args.wav), 'rb') as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
            parser.error('input must be uncompressed mono PCM16 WAV')
        if not 0 < wav.getnframes() / wav.getframerate() <= 10:
            parser.error('input must contain at most ten seconds of speech')
        pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1,
                               wav.getframerate(), 16000, None)
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    peak = max(abs(sample) for sample in samples)
    if peak == 0:
        parser.error('input is silent')
    values = [round(sample * 125 / peak) for sample in samples]
    digest = hashlib.sha256(bytes(value & 255 for value in values)).hexdigest()
    lines = [', '.join(str(value) for value in values[i:i + 24]) + ','
             for i in range(0, len(values), 24)]
    block = '\n'.join([
        START,
        '// "Missing P P E." — generated locally with eSpeak NG 1.50, en-us, 145 wpm.',
        f'// Mono signed PCM8, 16000 Hz, {len(values)} samples. Playback gain: 64.',
        f'// PCM SHA-256: {digest}',
        'static const int8_t MISSING_PPE_PCM[] PROGMEM = {',
        *lines,
        '};',
        END,
    ])
    source = SKETCH.read_text()
    start = source.index(START)
    end = source.index(END, start) + len(END)
    SKETCH.write_text(source[:start] + block + source[end:])
    print(f'Embedded {len(values)} bytes ({len(values) / 16000:.2f}s), SHA-256 {digest}')


if __name__ == '__main__':
    main()
