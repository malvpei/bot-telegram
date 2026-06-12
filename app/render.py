from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import SlidePlan, SlideRole, VideoPlan, VideoType


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
TYPE_3_TOOL_BADGES: dict[str, tuple[str, tuple[int, int, int], tuple[int, int, int]]] = {
    "shopify": ("Shopify", (255, 255, 255), (92, 156, 55)),
    "dropradar": ("Dropradar", (163, 245, 48), (20, 20, 20)),
    "chatgpt": ("ChatGPT", (104, 176, 154), (255, 255, 255)),
    "paypal": ("PayPal", (255, 255, 255), (0, 94, 166)),
    "stripe": ("Stripe", (99, 91, 255), (255, 255, 255)),
    "canva": ("Canva", (0, 196, 204), (255, 255, 255)),
    "capcut": ("CapCut", (255, 255, 255), (0, 0, 0)),
    "instagram": ("Instagram", (225, 48, 108), (255, 255, 255)),
    "tiktok": ("TikTok", (0, 0, 0), (255, 255, 255)),
}
TYPE_3_ROLE_TOOL_OPTIONS: dict[SlideRole, tuple[str, ...]] = {
    SlideRole.TOOL_STORE: ("shopify",),
    SlideRole.TOOL_PRODUCT_SEARCH: ("dropradar",),
    SlideRole.TOOL_SCRIPTS: ("chatgpt",),
    SlideRole.TOOL_PAYMENTS: ("paypal", "stripe"),
    SlideRole.TOOL_EDITING: ("canva", "capcut"),
    SlideRole.TOOL_MARKETING: ("instagram", "tiktok"),
}
TYPE_3_ICON_ALIASES: dict[str, tuple[str, ...]] = {
    "shopify": ("shopify",),
    "dropradar": ("dropradar",),
    "chatgpt": ("chatgpt",),
    "paypal": ("paypal", "paypall"),
    "stripe": ("stripe",),
    "canva": ("canva", "canvas"),
    "capcut": ("capcut",),
    "instagram": ("instagram", "istagram"),
    "tiktok": ("tiktok", "tikok"),
    "meta_ads": ("meta", "facebook"),
}
TYPE_3_ICON_VISUAL_SCALE: dict[str, float] = {
    "canva": 0.94,
    "capcut": 0.94,
    "chatgpt": 0.94,
    "instagram": 0.94,
    "tiktok": 0.94,
}
TYPE_3_ICON_TOP_RATIO: dict[str, float] = {
    "shopify": 0.441,
    "dropradar": 0.417,
    "chatgpt": 0.434,
    "paypal": 0.442,
    "stripe": 0.442,
    "canva": 0.434,
    "capcut": 0.421,
    "instagram": 0.429,
    "tiktok": 0.429,
}
TYPE_3_TEXT_STROKE_WIDTH = 3
TYPE_3_BODY_FONT_SIZE = 56
TYPE_4_TARGET_SECONDS = 7.5
TYPE_4_TITLE_STROKE_WIDTH = 4
TYPE_4_TEXT_STROKE_WIDTH = 3
TYPE_4_LABEL_FONT_SIZE = 39
TYPE_4_LABEL_MIN_FONT_SIZE = 27
TYPE_4_TEMPLATE_ROWS: tuple[
    tuple[str, str, str, int, int, int, int, int, int, int, int, int, int],
    ...
] = (
    ("Tienda:", "shopify", "Shopify", 95, 456, 205, 91, 368, 431, 142, 568, 475, 50),
    (
        "Productos\nganadores:",
        "dropradar",
        "Dropradar",
        83,
        620,
        262,
        122,
        381,
        596,
        142,
        568,
        663,
        50,
    ),
    ("Guiones:", "chatgpt", "ChatGPT", 96, 818, 211, 82, 354, 789, 142, 539, 846, 47),
    ("Pagos:", "stripe", "Stripe", 98, 981, 176, 82, 359, 961, 130, 549, 1008, 48),
    ("Organico:", "tiktok", "TikTok", 94, 1144, 232, 88, 372, 1138, 118, 554, 1179, 47),
    ("Ads:", "meta_ads", "Meta Ads", 120, 1329, 127, 82, 306, 1300, 170, 507, 1363, 45),
    ("Edicion:", "capcut", "CapCut", 92, 1504, 216, 82, 368, 1476, 130, 542, 1530, 47),
)


def _scale_x(value: int, width: int) -> int:
    return max(1, int(round(value * width / 1080)))


def _scale_y(value: int, height: int) -> int:
    return max(1, int(round(value * height / 1920)))


def _format_filter_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


class VideoRenderer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._gradient_overlay = self._build_gradient_overlay()
        self._font_dir = settings.fonts_dir
        self._type_3_icons_dir = settings.root_dir / "tipo3" / "iconos"
        self._type_4_icons_dir = settings.root_dir / "tipo4" / "iconos"

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
                        plan.video_type,
                    )
                    writer.append_data(frame)

                if index < len(plan.slides) - 1:
                    current_final = self._render_slide_frame(
                        slide,
                        source_images[slide.index],
                        1.0,
                        plan.video_type,
                    )
                    next_slide = plan.slides[index + 1]
                    next_initial = self._render_slide_frame(
                        next_slide,
                        source_images[next_slide.index],
                        0.0,
                        plan.video_type,
                    )
                    for transition_index in range(transition_frames):
                        alpha = (transition_index + 1) / transition_frames
                        blended = (
                            current_final.astype(np.float32) * (1.0 - alpha)
                            + next_initial.astype(np.float32) * alpha
                        )
                        writer.append_data(blended.astype(np.uint8))

        self.write_script(plan, job_dir)
        self._enforce_size_limit(video_path)
        return video_path, script_path

    def render_slide_still(self, slide: SlidePlan, video_type: VideoType) -> Image.Image:
        source_image = self._load_source_image(slide.media.local_path)
        frame = self._render_slide_frame(slide, source_image, 1.0, video_type)
        return Image.fromarray(frame)

    def render_template_video(self, input_video: Path, job_dir: Path) -> Path:
        job_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = job_dir / "template_overlay.png"
        output_path = job_dir / "template_video.mp4"
        self.build_type_4_template_overlay().save(overlay_path)

        width = self.settings.width
        height = self.settings.height
        duration = self._video_duration_seconds(input_video)
        trim_start = max(0.0, duration - TYPE_4_TARGET_SECONDS) if duration else 0.0
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        filtergraph = (
            f"[0:v]trim=start={_format_filter_float(trim_start)}:"
            f"duration={_format_filter_float(TYPE_4_TARGET_SECONDS)},"
            "setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={self.settings.fps}[base];"
            "[1:v]format=rgba[overlay];"
            "[base][overlay]overlay=0:0:format=auto:shortest=1[v]"
        )
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_video),
            "-loop",
            "1",
            "-i",
            str(overlay_path),
            "-filter_complex",
            filtergraph,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            details = ""
            if isinstance(error, subprocess.CalledProcessError):
                details = error.stderr[-1200:] if error.stderr else ""
            raise RuntimeError(f"No pude renderizar el video plantilla. {details}") from error
        self._enforce_size_limit(output_path)
        return output_path

    def _video_duration_seconds(self, input_video: Path) -> float | None:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-i", str(input_video)],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return None
        match = re.search(
            r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
            result.stderr or "",
        )
        if not match:
            return None
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def build_type_4_template_overlay(self) -> Image.Image:
        image = Image.new(
            "RGBA",
            (self.settings.width, self.settings.height),
            (0, 0, 0, 0),
        )
        draw = ImageDraw.Draw(image)
        self._draw_type_4_title(draw, image.width, image.height)
        for row in TYPE_4_TEMPLATE_ROWS:
            self._draw_type_4_template_row(image, draw, row)
        return image

    def write_script(self, plan: VideoPlan, job_dir: Path) -> Path:
        job_dir.mkdir(parents=True, exist_ok=True)
        script_path = job_dir / "script.txt"
        script_path.write_text(self._build_script(plan), encoding="utf-8")
        return script_path

    # ------------------------------------------------------------------
    # Frame composition
    # ------------------------------------------------------------------

    def _render_slide_frame(
        self,
        slide: SlidePlan,
        source_image: Image.Image,
        progress: float,
        video_type: VideoType,
    ) -> np.ndarray:
        if video_type == VideoType.TYPE_3:
            return self._render_type_3_slide_frame(slide, source_image, progress)
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

    def _render_type_3_slide_frame(
        self,
        slide: SlidePlan,
        source_image: Image.Image,
        progress: float,
    ) -> np.ndarray:
        canvas = self._cover_image(source_image, progress).convert("RGBA")
        if slide.role == SlideRole.HOOK:
            return np.asarray(canvas.convert("RGB"))
        else:
            self._draw_type_3_tool_slide(canvas, slide)
        return np.asarray(canvas.convert("RGB"))

    def _draw_type_3_hook_text(self, image: Image.Image, text: str) -> None:
        if not text:
            return
        draw = ImageDraw.Draw(image)
        width, height = image.size
        hook_with_year = self._split_type_3_hook_year(text)
        if hook_with_year is not None:
            self._draw_type_3_hook_year_layout(draw, hook_with_year, width, height)
            return

        font, lines = self._fit_text(
            text,
            draw,
            max_width=width - 110,
            max_height=int(height * 0.34),
            base_size=66,
            min_size=42,
            bold=True,
            stroke_width=4,
        )
        text_height = self._block_height(lines, font, draw, stroke_width=4)
        start_y = max(72, int(height * 0.29) - text_height // 2)
        self._draw_lines(
            draw,
            lines,
            font,
            start_y=start_y,
            width=width,
            fill=(255, 255, 255),
            stroke_width=4,
        )
        arrow_font, arrow_lines = self._fit_text(
            ">>>",
            draw,
            max_width=width - 110,
            max_height=int(height * 0.08),
            base_size=72,
            min_size=42,
            bold=True,
            stroke_width=4,
        )
        self._draw_lines(
            draw,
            arrow_lines,
            arrow_font,
            start_y=start_y + text_height + int(height * 0.02),
            width=width,
            fill=(255, 255, 255),
            stroke_width=4,
        )

    def _split_type_3_hook_year(self, text: str) -> tuple[str, str] | None:
        marker = "2026"
        if marker not in text:
            return None
        prefix, _, _ = text.partition(marker)
        prefix = " ".join(prefix.split()).strip()
        if not prefix:
            return None
        return prefix, marker

    def _draw_type_3_hook_year_layout(
        self,
        draw: ImageDraw.ImageDraw,
        hook_parts: tuple[str, str],
        width: int,
        height: int,
    ) -> None:
        prefix, year = hook_parts
        max_width = width - 110
        badge_size = int(width * 0.058)
        badge_gap = int(width * 0.008)
        year_badges_width = badge_gap + (badge_size * 2) + badge_gap

        size = 66
        while size >= 42:
            font = self._load_font(size=size, bold=True)
            prefix_width, prefix_height = self._text_size(
                draw, prefix, font, stroke_width=4
            )
            year_width, year_height = self._text_size(
                draw, year, font, stroke_width=4
            )
            if (
                prefix_width <= max_width
                and year_width + year_badges_width <= max_width
            ):
                break
            size -= 2
        font = self._load_font(size=max(size, 42), bold=True)
        prefix_width, prefix_height = self._text_size(
            draw, prefix, font, stroke_width=4
        )
        year_width, year_height = self._text_size(
            draw, year, font, stroke_width=4
        )

        line_gap = int(height * 0.010)
        arrow_gap = int(height * 0.020)
        arrow_font = self._load_font(size=max(42, int(size * 0.92)), bold=True)
        arrow_width, arrow_height = self._text_size(
            draw, ">>>", arrow_font, stroke_width=4
        )
        second_line_height = max(year_height, badge_size)
        total_height = prefix_height + line_gap + second_line_height + arrow_gap + arrow_height
        y = max(72, int(height * 0.314) - total_height // 2)

        draw.text(
            ((width - prefix_width) // 2, y),
            prefix,
            font=font,
            fill=(255, 255, 255),
            stroke_width=4,
            stroke_fill=(0, 0, 0),
        )
        second_y = y + prefix_height + line_gap
        total_second_width = year_width + year_badges_width
        x = (width - total_second_width) // 2
        draw.text(
            (x, second_y),
            year,
            font=font,
            fill=(255, 255, 255),
            stroke_width=4,
            stroke_fill=(0, 0, 0),
        )
        badge_y = second_y + max(0, (year_height - badge_size) // 2)
        badge_x = x + year_width + badge_gap
        for offset in (0, badge_size + badge_gap):
            self._draw_type_3_check_badge(
                draw,
                badge_x + offset,
                badge_y,
                badge_size,
            )
        arrow_y = second_y + second_line_height + arrow_gap
        draw.text(
            ((width - arrow_width) // 2, arrow_y),
            ">>>",
            font=arrow_font,
            fill=(255, 255, 255),
            stroke_width=4,
            stroke_fill=(0, 0, 0),
        )

    def _draw_type_3_check_badge(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        size: int,
    ) -> None:
        radius = max(6, size // 8)
        draw.rounded_rectangle(
            (x, y, x + size, y + size),
            radius=radius,
            fill=(120, 184, 83),
        )
        line_width = max(6, size // 8)
        points = (
            (x + int(size * 0.24), y + int(size * 0.54)),
            (x + int(size * 0.42), y + int(size * 0.72)),
            (x + int(size * 0.76), y + int(size * 0.28)),
        )
        draw.line(points, fill=(255, 255, 255), width=line_width, joint="curve")

    def _draw_type_3_tool_slide(self, image: Image.Image, slide: SlidePlan) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        title, subtitle, cta = self._split_type_3_tool_text(slide.text)

        title_font = self._fit_single_line_text(
            title,
            draw,
            max_width=width - 80,
            base_size=72,
            min_size=46,
            bold=True,
            stroke_width=TYPE_3_TEXT_STROKE_WIDTH,
        )
        body_font = self._load_font(size=TYPE_3_BODY_FONT_SIZE, bold=True)
        body_lines = self._type_3_body_lines(
            subtitle,
            cta,
            draw=draw,
            font=body_font,
            max_width=width - 160,
        )
        title_lines = [title] if title else []
        title_height = self._block_height(
            title_lines,
            title_font,
            draw,
            stroke_width=TYPE_3_TEXT_STROKE_WIDTH,
        )
        title_y = int(height * 0.270) - title_height // 2
        self._draw_lines(
            draw,
            title_lines,
            title_font,
            start_y=max(70, title_y),
            width=width,
            fill=(255, 255, 255),
            stroke_width=TYPE_3_TEXT_STROKE_WIDTH,
        )
        if body_lines:
            self._draw_lines(
                draw,
                body_lines,
                body_font,
                start_y=int(height * 0.32),
                width=width,
                fill=(255, 255, 255),
                stroke_width=TYPE_3_TEXT_STROKE_WIDTH,
            )

        tool_key = self._type_3_tool_key(slide.role, slide.text)
        icon_box_size = int(width * 0.44)
        icon_top = int(height * TYPE_3_ICON_TOP_RATIO.get(tool_key, 0.434))
        self._draw_type_3_icon(image, slide.role, slide.text, width, icon_top, icon_box_size)

    def _fit_single_line_text(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        *,
        max_width: int,
        base_size: int,
        min_size: int,
        bold: bool,
        stroke_width: int,
    ) -> ImageFont.ImageFont:
        size = base_size
        while size >= min_size:
            font = self._load_font(size=size, bold=bold)
            line_width, _ = self._text_size(
                draw,
                text,
                font,
                stroke_width=stroke_width,
            )
            if line_width <= max_width:
                return font
            size -= 2
        return self._load_font(size=min_size, bold=bold)

    def _fit_prebroken_lines(
        self,
        lines: list[str],
        draw: ImageDraw.ImageDraw,
        *,
        max_width: int,
        max_height: int,
        base_size: int,
        min_size: int,
        bold: bool,
        stroke_width: int,
    ) -> ImageFont.ImageFont:
        size = base_size
        while size >= min_size:
            font = self._load_font(size=size, bold=bold)
            height = self._block_height(lines, font, draw, stroke_width=stroke_width)
            widths = [
                self._text_size(draw, line, font, stroke_width=stroke_width)[0]
                for line in lines
            ]
            if height <= max_height and (not widths or max(widths) <= max_width):
                return font
            size -= 2
        return self._load_font(size=min_size, bold=bold)

    def _type_3_body_lines(
        self,
        subtitle: str,
        cta: str,
        *,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        raw = " ".join(piece for piece in (subtitle, cta) if piece).strip()
        if not raw:
            return []
        lines: list[str] = []
        current = ""
        for word in raw.split():
            trial = word if not current else f"{current} {word}"
            trial_width, _ = self._text_size(
                draw,
                trial,
                font,
                stroke_width=TYPE_3_TEXT_STROKE_WIDTH,
            )
            if trial_width <= max_width or not current:
                current = trial
                continue
            lines.append(current)
            current = word
        if current:
            lines.append(current)
        return lines

    def _split_type_3_tool_text(self, text: str) -> tuple[str, str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else ""
        subtitle = lines[1] if len(lines) > 1 else ""
        cta = lines[2] if len(lines) > 2 else ""
        return title, subtitle, cta

    def _draw_type_3_badge(
        self,
        draw: ImageDraw.ImageDraw,
        role: SlideRole,
        text: str,
        width: int,
        height: int,
    ) -> None:
        tool_key = self._type_3_tool_key(role, text)
        label, fill, text_fill = TYPE_3_TOOL_BADGES.get(
            tool_key,
            ("Tool", (255, 255, 255), (0, 0, 0)),
        )
        badge_size = int(width * 0.38)
        x0 = (width - badge_size) // 2
        y0 = int(height * 0.48)
        x1 = x0 + badge_size
        y1 = y0 + badge_size
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=40,
            fill=fill,
            outline=(255, 255, 255),
            width=4,
        )
        font, lines = self._fit_text(
            label,
            draw,
            max_width=badge_size - 28,
            max_height=badge_size - 28,
            base_size=54,
            min_size=28,
            bold=True,
            stroke_width=0,
        )
        block_height = self._block_height(lines, font, draw, stroke_width=0)
        y = y0 + (badge_size - block_height) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            draw.text(
                (x0 + (badge_size - line_width) // 2, y),
                line,
                font=font,
                fill=text_fill,
            )
            y += (bbox[3] - bbox[1]) + 16

    def _draw_type_3_icon(
        self,
        image: Image.Image,
        role: SlideRole,
        text: str,
        width: int,
        y0: int,
        icon_size: int,
    ) -> None:
        tool_key = self._type_3_tool_key(role, text)
        icon_path = self._type_3_icon_path(role, text)
        if icon_path is None:
            draw = ImageDraw.Draw(image)
            self._draw_type_3_badge(draw, role, text, width, image.height)
            return
        with Image.open(icon_path) as raw_icon:
            icon = raw_icon.convert("RGBA")
        icon = self._fit_type_3_icon(
            icon,
            icon_size,
            visual_scale=TYPE_3_ICON_VISUAL_SCALE.get(tool_key, 1.0),
        )
        x = (width - icon_size) // 2
        image.alpha_composite(icon, (x, y0))

    def _fit_type_3_icon(
        self,
        icon: Image.Image,
        box_size: int,
        *,
        visual_scale: float = 1.0,
    ) -> Image.Image:
        alpha_bbox = icon.getbbox()
        if alpha_bbox is not None:
            icon = icon.crop(alpha_bbox)
        scale = min(box_size / icon.width, box_size / icon.height) * visual_scale
        icon = icon.resize(
            (
                max(1, int(round(icon.width * scale))),
                max(1, int(round(icon.height * scale))),
            ),
            Image.Resampling.LANCZOS,
        )
        fitted = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
        fitted.alpha_composite(
            icon,
            ((box_size - icon.width) // 2, (box_size - icon.height) // 2),
        )
        return fitted

    def _type_3_icon_path(self, role: SlideRole, text: str) -> Path | None:
        return self._icon_path_for_tool_key(self._type_3_tool_key(role, text))

    def _icon_path_for_tool_key(self, tool_key: str) -> Path | None:
        needles = TYPE_3_ICON_ALIASES.get(tool_key)
        if not needles:
            return None
        for icons_dir in (self._type_4_icons_dir, self._type_3_icons_dir):
            if not icons_dir.exists():
                continue
            for path in sorted(icons_dir.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file():
                    continue
                lowered = path.name.lower()
                if any(needle in lowered for needle in needles):
                    return path
        return None

    def _type_3_tool_key(self, role: SlideRole, text: str) -> str:
        options = TYPE_3_ROLE_TOOL_OPTIONS.get(role, ())
        lowered = text.lower()
        for tool_key in options:
            aliases = TYPE_3_ICON_ALIASES.get(tool_key, (tool_key,))
            if any(alias in lowered for alias in aliases):
                return tool_key
        if options:
            return options[0]
        return "tool"

    def _draw_type_4_title(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
    ) -> None:
        font = self._load_font(size=_scale_y(66, height), bold=True)
        line_gap = _scale_y(4, height)
        first_line = "Empieza tu negocio online"
        second_line = "en 24h"
        first_width, first_height = self._text_size(
            draw,
            first_line,
            font,
            stroke_width=TYPE_4_TITLE_STROKE_WIDTH,
        )
        second_width, second_height = self._text_size(
            draw,
            second_line,
            font,
            stroke_width=TYPE_4_TITLE_STROKE_WIDTH,
        )
        y = _scale_y(244, height)
        draw.text(
            ((width - first_width) // 2, y),
            first_line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TITLE_STROKE_WIDTH,
            stroke_fill=(0, 0, 0),
        )
        second_y = y + first_height + line_gap
        badge_size = _scale_x(58, width)
        badge_gap = _scale_x(20, width)
        second_group_width = second_width + badge_gap + badge_size
        second_x = (width - second_group_width) // 2
        draw.text(
            (second_x, second_y),
            second_line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TITLE_STROKE_WIDTH,
            stroke_fill=(0, 0, 0),
        )
        badge_x = second_x + second_width + badge_gap
        badge_y = second_y + max(0, (second_height - badge_size) // 2) + _scale_y(2, height)
        self._draw_type_3_check_badge(draw, badge_x, badge_y, badge_size)

    def _draw_type_4_template_row(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        row: tuple[str, str, str, int, int, int, int, int, int, int, int, int, int],
    ) -> None:
        (
            label,
            tool_key,
            name,
            label_x,
            label_y,
            label_w,
            label_h,
            icon_x,
            icon_y,
            icon_size,
            name_x,
            name_y,
            name_size,
        ) = row
        width, height = image.size
        label_box = (
            _scale_x(label_x, width),
            _scale_y(label_y, height),
            _scale_x(label_x + label_w, width),
            _scale_y(label_y + label_h, height),
        )
        radius = max(10, _scale_x(16, width))
        draw.rounded_rectangle(label_box, radius=radius, fill=(255, 255, 255))
        label_lines = label.splitlines()
        label_font = self._fit_prebroken_lines(
            label_lines,
            draw,
            max_width=(label_box[2] - label_box[0]) - _scale_x(28, width),
            max_height=(label_box[3] - label_box[1]) - _scale_y(18, height),
            base_size=_scale_y(TYPE_4_LABEL_FONT_SIZE, height),
            min_size=_scale_y(TYPE_4_LABEL_MIN_FONT_SIZE, height),
            bold=False,
            stroke_width=0,
        )
        self._draw_centered_lines_in_box(
            draw,
            label_lines,
            label_font,
            label_box,
            fill=(0, 0, 0),
            stroke_width=0,
            faux_bold_pixels=1,
        )

        scaled_icon_size = _scale_x(icon_size, width)
        icon_path = self._icon_path_for_tool_key(tool_key)
        if icon_path is None and tool_key == "meta_ads":
            self._draw_type_4_meta_icon(
                image,
                _scale_x(icon_x, width),
                _scale_y(icon_y, height),
                scaled_icon_size,
            )
        elif icon_path is not None:
            with Image.open(icon_path) as raw_icon:
                icon = raw_icon.convert("RGBA")
            icon = self._fit_type_3_icon(
                icon,
                scaled_icon_size,
                visual_scale=TYPE_3_ICON_VISUAL_SCALE.get(tool_key, 1.0),
            )
            image.alpha_composite(
                icon,
                (_scale_x(icon_x, width), _scale_y(icon_y, height)),
            )
        else:
            self._draw_type_4_fallback_icon(
                image,
                _scale_x(icon_x, width),
                _scale_y(icon_y, height),
                scaled_icon_size,
                tool_key,
            )

        name_font = self._fit_single_line_text(
            name,
            draw,
            max_width=width - _scale_x(name_x + 40, width),
            base_size=_scale_y(name_size, height),
            min_size=_scale_y(32, height),
            bold=False,
            stroke_width=TYPE_4_TEXT_STROKE_WIDTH,
        )
        draw.text(
            (_scale_x(name_x, width), _scale_y(name_y, height)),
            name,
            font=name_font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TEXT_STROKE_WIDTH,
            stroke_fill=(0, 0, 0),
        )
        draw.text(
            (_scale_x(name_x, width) + 1, _scale_y(name_y, height)),
            name,
            font=name_font,
            fill=(255, 255, 255),
        )

    def _draw_centered_lines_in_box(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        font: ImageFont.ImageFont,
        box: tuple[int, int, int, int],
        *,
        fill: tuple[int, int, int],
        stroke_width: int,
        faux_bold_pixels: int = 0,
    ) -> None:
        line_metrics = [
            draw.textbbox((0, 0), line or "A", font=font, stroke_width=stroke_width)
            for line in lines
        ]
        line_heights = [bbox[3] - bbox[1] for bbox in line_metrics]
        gap = max(4, int((box[3] - box[1]) * 0.04)) if len(lines) > 1 else 0
        total_height = sum(line_heights) + gap * max(0, len(lines) - 1)
        y = box[1] + ((box[3] - box[1]) - total_height) // 2
        for line, bbox, line_height in zip(lines, line_metrics, line_heights):
            line_width = bbox[2] - bbox[0]
            x = box[0] + ((box[2] - box[0]) - line_width) // 2
            draw.text(
                (x, y),
                line,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0),
            )
            if faux_bold_pixels:
                draw.text(
                    (x + faux_bold_pixels, y),
                    line,
                    font=font,
                    fill=fill,
                )
            y += line_height + gap

    def _draw_type_4_meta_icon(
        self,
        image: Image.Image,
        x: int,
        y: int,
        size: int,
    ) -> None:
        draw = ImageDraw.Draw(image)
        color = (24, 119, 242, 255)
        line_width = max(10, size // 13)
        left_box = (x + int(size * 0.05), y + int(size * 0.25), x + int(size * 0.52), y + int(size * 0.77))
        right_box = (x + int(size * 0.48), y + int(size * 0.25), x + int(size * 0.95), y + int(size * 0.77))
        draw.arc(left_box, start=205, end=520, fill=color, width=line_width)
        draw.arc(right_box, start=20, end=335, fill=color, width=line_width)

    def _draw_type_4_fallback_icon(
        self,
        image: Image.Image,
        x: int,
        y: int,
        size: int,
        label: str,
    ) -> None:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (x, y, x + size, y + size),
            radius=max(10, size // 8),
            fill=(255, 255, 255),
        )
        short_label = label[:2].upper()
        font = self._load_font(size=max(20, size // 3), bold=True)
        text_width, text_height = self._text_size(draw, short_label, font, stroke_width=0)
        draw.text(
            (x + (size - text_width) // 2, y + (size - text_height) // 2),
            short_label,
            font=font,
            fill=(0, 0, 0),
        )

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
            marker, _, rest = parts[0].strip().partition(" ")
            if marker.endswith(".") and marker[:-1].isdigit() and rest:
                return marker, rest
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

    def _text_size(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        *,
        stroke_width: int,
    ) -> tuple[int, int]:
        bbox = draw.textbbox((0, 0), text or "A", font=font, stroke_width=stroke_width)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

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

        system_candidates = (
            SYSTEM_FONT_CANDIDATES
            if bold
            else (
                "DejaVuSans.ttf",
                "arial.ttf",
                "Arial.ttf",
                "Helvetica.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "DejaVuSans-Bold.ttf",
                "arialbd.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            )
        )
        for candidate in system_candidates:
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

    def _enforce_size_limit(self, video_path: Path, *, preserve_audio: bool = False) -> None:
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
                "-map", "0:v:0",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
            ]
            if preserve_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "96k"])
            else:
                cmd.append("-an")
            cmd.append(str(tmp_path))
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
