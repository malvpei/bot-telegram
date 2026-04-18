from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import SlidePlan, SlideRole, VideoPlan


LOGGER = logging.getLogger(__name__)


SYSTEM_FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "arialbd.ttf",
    "arial.ttf",
    "Arial.ttf",
    "Helvetica.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


class VideoRenderer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._gradient_overlay = self._build_gradient_overlay()
        self._font_dir = settings.fonts_dir

    def render(self, plan: VideoPlan, job_dir: Path) -> tuple[Path, Path]:
        job_dir.mkdir(parents=True, exist_ok=True)
        video_path = job_dir / "output.mp4"
        script_path = job_dir / "script.txt"

        fps = self.settings.fps
        total_frames = max(1, int(self.settings.slide_seconds * fps))
        transition_frames = max(1, int(self.settings.transition_seconds * fps))

        with imageio.get_writer(
            str(video_path),
            fps=fps,
            codec="libx264",
            macro_block_size=1,
            format="FFMPEG",
            quality=None,
            output_params=[
                "-preset", "medium",
                "-crf", "23",
                "-movflags", "+faststart",
            ],
        ) as writer:
            source_images = {
                slide.index: self._load_source_image(slide.media.local_path)
                for slide in plan.slides
            }

            for index, slide in enumerate(plan.slides):
                main_frames = total_frames
                if index < len(plan.slides) - 1:
                    main_frames = max(1, total_frames - transition_frames)

                for frame_index in range(main_frames):
                    progress = frame_index / max(main_frames - 1, 1)
                    frame = self._render_slide_frame(
                        slide,
                        source_images[slide.index],
                        progress,
                    )
                    writer.append_data(frame)

                if index < len(plan.slides) - 1:
                    current_final = self._render_slide_frame(
                        slide,
                        source_images[slide.index],
                        1.0,
                    )
                    next_slide = plan.slides[index + 1]
                    next_initial = self._render_slide_frame(
                        next_slide,
                        source_images[next_slide.index],
                        0.0,
                    )
                    for transition_index in range(transition_frames):
                        alpha = (transition_index + 1) / transition_frames
                        blended = (
                            current_final.astype(np.float32) * (1.0 - alpha)
                            + next_initial.astype(np.float32) * alpha
                        )
                        writer.append_data(blended.astype(np.uint8))

        script_path.write_text(self._build_script(plan), encoding="utf-8")
        self._enforce_size_limit(video_path)
        return video_path, script_path

    # ------------------------------------------------------------------
    # Frame composition
    # ------------------------------------------------------------------

    def _render_slide_frame(
        self,
        slide: SlidePlan,
        source_image: Image.Image,
        progress: float,
    ) -> np.ndarray:
        canvas = self._cover_image(source_image, progress)
        composed = Image.alpha_composite(canvas.convert("RGBA"), self._gradient_overlay)
        self._draw_text(composed, slide)
        return np.asarray(composed.convert("RGB"))

    def _cover_image(self, source: Image.Image, progress: float) -> Image.Image:
        width = self.settings.width
        height = self.settings.height
        scale = max(width / source.width, height / source.height)
        zoom = 1.0 + 0.06 * progress
        resized = source.resize(
            (
                max(1, int(source.width * scale * zoom)),
                max(1, int(source.height * scale * zoom)),
            ),
            Image.Resampling.LANCZOS,
        )

        extra_x = max(0, resized.width - width)
        extra_y = max(0, resized.height - height)
        offset_x = int(extra_x * (0.3 + 0.4 * progress))
        offset_y = int(extra_y * 0.5)
        return resized.crop((offset_x, offset_y, offset_x + width, offset_y + height))

    def _build_gradient_overlay(self) -> Image.Image:
        width = self.settings.width
        height = self.settings.height
        start_y = int(height * 0.48)

        mask = np.zeros((height, width), dtype=np.uint8)
        ramp = np.linspace(0, 220, max(height - start_y, 1), dtype=np.uint8)
        mask[start_y:, :] = ramp[:, None]

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay.putalpha(Image.fromarray(mask, mode="L"))
        return overlay

    def _load_source_image(self, image_path: Path) -> Image.Image:
        with Image.open(image_path) as image:
            return image.convert("RGB").copy()

    # ------------------------------------------------------------------
    # Text rendering
    # ------------------------------------------------------------------

    def _draw_text(self, image: Image.Image, slide: SlidePlan) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size

        account_label = (
            "Dropradar"
            if slide.media.source_account == "fixed"
            else f"@{slide.media.source_account}"
        )
        account_font = self._load_font(size=34, bold=True)
        draw.text(
            (70, 70),
            account_label,
            font=account_font,
            fill=(255, 222, 173),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

        if not slide.text:
            return

        max_text_width = width - 140
        bottom_margin = 220 if slide.role == SlideRole.HOOK else 190

        if slide.role == SlideRole.HOOK:
            font, lines = self._fit_text(
                slide.text,
                draw,
                max_width=max_text_width,
                max_height=int(height * 0.55),
                base_size=84,
                min_size=46,
                bold=True,
                stroke_width=4,
            )
            text_height = self._block_height(lines, font, draw, stroke_width=4)
            start_y = max(80, height - text_height - bottom_margin)
            self._draw_lines(
                draw,
                lines,
                font,
                start_y=start_y,
                width=width,
                fill=(255, 255, 255),
                stroke_width=4,
            )
            return

        first_line, body = self._split_slide_text(slide.text)
        title_font, title_lines = self._fit_text(
            first_line,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.18),
            base_size=52,
            min_size=34,
            bold=True,
            stroke_width=3,
        )
        body_font, body_lines = self._fit_text(
            body,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.40),
            base_size=60,
            min_size=34,
            bold=False,
            stroke_width=3,
        )

        title_height = self._block_height(title_lines, title_font, draw, stroke_width=3)
        body_height = self._block_height(body_lines, body_font, draw, stroke_width=3)
        total_height = title_height + 28 + body_height
        start_y = max(80, height - total_height - bottom_margin)

        self._draw_lines(
            draw,
            title_lines,
            title_font,
            start_y=start_y,
            width=width,
            fill=(255, 214, 102),
            stroke_width=3,
        )
        self._draw_lines(
            draw,
            body_lines,
            body_font,
            start_y=start_y + title_height + 28,
            width=width,
            fill=(255, 255, 255),
            stroke_width=3,
        )

    def _fit_text(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        *,
        max_width: int,
        max_height: int,
        base_size: int,
        min_size: int,
        bold: bool,
        stroke_width: int,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        size = base_size
        while size >= min_size:
            font = self._load_font(size=size, bold=bold)
            lines = self._wrap_text(text, font, max_width, draw, stroke_width=stroke_width)
            height = self._block_height(lines, font, draw, stroke_width=stroke_width)
            if height <= max_height:
                return font, lines
            size -= 4
        font = self._load_font(size=min_size, bold=bold)
        lines = self._wrap_text(text, font, max_width, draw, stroke_width=stroke_width)
        return font, lines

    def _split_slide_text(self, text: str) -> tuple[str, str]:
        parts = text.split("\n", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    def _draw_lines(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        font: ImageFont.ImageFont,
        *,
        start_y: int,
        width: int,
        fill: tuple[int, int, int],
        stroke_width: int,
    ) -> None:
        y = start_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=stroke_width)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            x = (width - line_width) // 2
            draw.text(
                (x, y),
                line,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0),
            )
            y += line_height + 16

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
        *,
        stroke_width: int,
    ) -> list[str]:
        wrapped_lines: list[str] = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                wrapped_lines.append("")
                continue
            line = words[0]
            for word in words[1:]:
                trial = f"{line} {word}"
                bbox = draw.textbbox((0, 0), trial, font=font, stroke_width=stroke_width)
                if bbox[2] - bbox[0] <= max_width:
                    line = trial
                else:
                    wrapped_lines.append(line)
                    line = word
            wrapped_lines.append(line)
        return wrapped_lines

    def _block_height(
        self,
        lines: list[str],
        font: ImageFont.ImageFont,
        draw: ImageDraw.ImageDraw,
        *,
        stroke_width: int,
    ) -> int:
        height = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=stroke_width)
            height += (bbox[3] - bbox[1]) + 16
        return max(height - 16, 0)

    def _load_font(self, *, size: int, bold: bool) -> ImageFont.ImageFont:
        suffix = "Bold" if bold else "Regular"
        if self._font_dir.exists():
            for font_file in sorted(self._font_dir.glob("*.ttf")):
                name = font_file.name.lower()
                if bold and ("bold" in name or "black" in name or "heavy" in name):
                    try:
                        return ImageFont.truetype(str(font_file), size=size)
                    except OSError:
                        continue
                if not bold and ("regular" in name or "book" in name) and "bold" not in name:
                    try:
                        return ImageFont.truetype(str(font_file), size=size)
                    except OSError:
                        continue
            # Fall back to any TTF in the folder.
            for font_file in sorted(self._font_dir.glob("*.ttf")):
                try:
                    return ImageFont.truetype(str(font_file), size=size)
                except OSError:
                    continue

        for candidate in SYSTEM_FONT_CANDIDATES:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue

        # Pillow >= 10.1 accepts a size on the bitmap default font, which keeps
        # text legible even when no TTF is available.
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # Older Pillow without size kwarg.
            LOGGER.warning(
                "No usable TrueType font found and Pillow default font does not "
                "accept size=%s. Text will be tiny — install a TTF or drop one "
                "into %s.",
                size,
                self._font_dir,
            )
            return ImageFont.load_default()

    # ------------------------------------------------------------------
    # Output management
    # ------------------------------------------------------------------

    def _build_script(self, plan: VideoPlan) -> str:
        chunks: list[str] = []
        for slide in plan.slides:
            header = f"[Slide {slide.index}] {slide.role.value}"
            source = f"Fuente: {slide.media.source_account}"
            chunks.append(f"{header}\n{source}\n{slide.text}")
        return "\n\n".join(chunks)

    def _enforce_size_limit(self, video_path: Path) -> None:
        limit_bytes = self.settings.max_video_size_mb * 1024 * 1024
        if limit_bytes <= 0:
            return
        try:
            current_size = video_path.stat().st_size
        except OSError:
            return
        if current_size <= limit_bytes:
            return

        LOGGER.info(
            "Video %s is %d bytes (> %d). Re-encoding with higher CRF.",
            video_path.name,
            current_size,
            limit_bytes,
        )
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        for crf in (28, 32, 36):
            tmp_path = video_path.with_suffix(".reencoded.mp4")
            cmd = [
                ffmpeg_path,
                "-y",
                "-i", str(video_path),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-an",
                str(tmp_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as error:
                LOGGER.warning("Re-encode with CRF %s failed: %s", crf, error)
                if tmp_path.exists():
                    tmp_path.unlink()
                return
            new_size = tmp_path.stat().st_size
            if new_size <= limit_bytes:
                shutil.move(str(tmp_path), str(video_path))
                LOGGER.info(
                    "Re-encoded %s to %d bytes with CRF %s.",
                    video_path.name,
                    new_size,
                    crf,
                )
                return
            tmp_path.unlink()

        LOGGER.warning(
            "Could not bring %s under %d bytes. The video may exceed Telegram's "
            "size cap and the upload may fail.",
            video_path.name,
            limit_bytes,
        )
