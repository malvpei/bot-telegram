from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_media(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Only a local rendering error, never a credential-bearing provider request.
        raise ValueError("No se pudo completar el montaje. " + result.stderr[-1200:])
    return result


def media_duration(path: Path) -> float:
    result = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise ValueError("No se ha podido leer la duración del archivo.")
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


def timestamp(value: float) -> str:
    centiseconds = max(0, round(value * 100))
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def caption_groups(alignment: dict, offset: float = 0.25) -> list[dict]:
    """Use provider alignment, never guessed word times, for final subtitles."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    if not chars or not (len(chars) == len(starts) == len(ends)):
        raise ValueError("Faltan los tiempos reales de la voz. No se pueden verificar los subtítulos.")
    if any(not isinstance(n, (int, float)) or not math.isfinite(n) or n < 0 for n in starts + ends):
        raise ValueError("Los tiempos de la voz no son válidos.")
    if any(e < s for s, e in zip(starts, ends)) or any(starts[i] < starts[i - 1] for i in range(1, len(starts))):
        raise ValueError("Los tiempos de la voz no mantienen el orden del texto.")
    words, current, first, last = [], "", 0.0, 0.0
    for char, start, end in zip(chars, starts, ends):
        if char.isspace():
            if current:
                words.append((current, first, last))
                current = ""
        else:
            if not current:
                first = start
            current += char
            last = end
    if current:
        words.append((current, first, last))
    groups, batch = [], []
    for word in words:
        proposed = " ".join([w[0] for w in batch] + [word[0]])
        if batch and (len(proposed) > 43 or word[2] - batch[0][1] > 3.0):
            groups.append(batch)
            batch = []
        batch.append(word)
        if word[0].endswith((".", "?", "!", ";")) and len(" ".join(w[0] for w in batch)) >= 16:
            groups.append(batch)
            batch = []
    if batch:
        groups.append(batch)
    captions = []
    for index, group in enumerate(groups):
        start = group[0][1] + offset
        following = groups[index + 1][0][1] + offset if index + 1 < len(groups) else float("inf")
        end = min(group[-1][2] + offset + 0.10, following)
        captions.append({"text": " ".join(w[0] for w in group), "start": start, "end": max(end, start + .02)})
    return captions


def write_ass(path: Path, captions: list[dict]) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter SemiBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,90,150,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for caption in captions:
        # Escape ASS commands: script text is content, never formatting instructions.
        content = str(caption["text"]).replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")
        rows.append(f"Dialogue: 0,{timestamp(caption['start'])},{timestamp(caption['end'])},Default,,0,0,0,,{content}")
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def render_plan(plan: dict, sources: list[dict], directory: Path, *, voice: dict | None = None,
                music: Path | None = None) -> dict:
    """Frame-accurate visual edits; a single independent voice track is never cut."""
    directory.mkdir(parents=True, exist_ok=True)
    if not sources:
        raise ValueError("Faltan planos para montar el vídeo.")
    segments, duration = [], 0.0
    for index, source in enumerate(sources):
        path = Path(source["path"]).resolve()
        start, seconds = float(source.get("in", 0)), float(source["duration"])
        if not path.is_file() or not math.isfinite(start) or not math.isfinite(seconds) or start < 0 or seconds <= 0:
            raise ValueError("Uno de los planos no es válido.")
        available = media_duration(path)
        if start + seconds > available + 1 / 24:
            raise ValueError("Un plano es demasiado corto. Genera otra toma; no se congelará ni se acelerará.")
        frames = round(seconds * 24)
        seconds = frames / 24
        target = directory / f"segment_{index:02}.mp4"
        run_media(["-y", "-ss", str(start), "-i", str(path), "-frames:v", str(frames),
                   "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p",
                   "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-movflags", "+faststart", str(target)])
        segments.append(target)
        duration += seconds
    concat = directory / "segments.txt"
    concat.write_text("".join("file '" + p.name + "'\n" for p in segments))
    timeline = directory / "picture.mp4"
    run_media(["-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(timeline)])
    offset, captions = .25, []
    if voice:
        voice_path = Path(voice["audio_path"])
        spoken_duration = media_duration(voice_path)
        if spoken_duration + offset + .20 > duration:
            raise ValueError(f"La voz completa necesita {spoken_duration + .45:.1f} s y el montaje tiene {duration:.1f} s. Amplía la duración o acorta el texto.")
        alignment_data = json.loads(Path(voice["alignment_path"]).read_text())
        alignment = alignment_data.get("normalized_alignment") or alignment_data.get("alignment") or alignment_data
        captions = caption_groups(alignment, offset)
        if captions[-1]["end"] > duration - .05:
            raise ValueError("El último subtítulo no cabe completo en el montaje.")
    ass = directory / "captions.ass"
    write_ass(ass, captions)
    output = directory / "preview.mp4"
    args = ["-y", "-i", str(timeline)]
    if voice:
        args += ["-i", str(voice["audio_path"])]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    if music:
        args += ["-i", str(music)]
    # Relative subtitle filename avoids interpreting user-controlled filesystem text
    # as filter syntax. Run from the output folder rather than shell interpolation.
    font_directory = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "advice"
    vf = "subtitles=filename=captions.ass:fontsdir=" + str(font_directory).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    filters = [f"[0:v]{vf}[v]", "[1:a]aresample=48000,adelay=250:all=1,apad,alimiter=limit=0.95:level=false[voice]"]
    if music:
        filters += ["[voice]asplit=2[spoken][duckkey]", "[2:a]aresample=48000,volume=0.22,afade=t=in:d=0.08,afade=t=out:st=" + str(max(0, duration - .5)) + ":d=0.5[music]",
                    "[music][duckkey]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=250[bed]",
                    "[spoken][bed]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95:level=false[a]"]
        audio = "[a]"
    else:
        audio = "[voice]"
    args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", audio,
             "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(output)]
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", *args], cwd=directory,
                            capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise ValueError("Error en la mezcla final. " + result.stderr[-1200:])
    return {"path": str(output), "duration": duration, "captions": captions,
            "voice_complete": bool(voice), "caption_alignment": "provider" if voice else "none",
            "cut_policy": "Montaje visual a fotograma; voz continua independiente, sin estirar ni congelar planos."}
