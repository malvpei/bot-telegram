from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import cv2
import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import Settings
from app.models import Language, SlidePlan, SlideRole, VideoPlan, VideoType


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
TYPE_3_TEXT_STROKE_WIDTH = 4
TYPE_3_BODY_FONT_SIZE = 58
TYPE_4_TARGET_SECONDS = 7.5
TYPE_4_TITLE_STROKE_WIDTH = 4
TYPE_4_TEXT_STROKE_WIDTH = 3
TYPE_4_LABEL_FONT_SIZE = 39
TYPE_4_LABEL_MIN_FONT_SIZE = 27
TEXT_CARD_FILL = (255, 255, 255, 246)
TEXT_CARD_TEXT = (0, 0, 0)
TEXT_FACE_AVOID_WEIGHT = 150.0
TEXT_EYE_AVOID_WEIGHT = 120.0
TEXT_HEAD_AVOID_WEIGHT = 55.0
TEXT_BODY_AVOID_WEIGHT = 2.5
TEXT_CARD_EDGE_MARGIN = 84
TEXT_CARD_PADDING_X = 46
TEXT_CARD_PADDING_Y = 16
TEXT_CARD_TITLE_PADDING_Y = 22
TEXT_CARD_LINE_OVERLAP = 12
TEXT_CARD_GROUP_GAP = 20
TEXT_CARD_FAUX_BOLD_PIXELS = 1
TYPE_4_TITLE_LINES: dict[Language, tuple[str, str]] = {
    Language.ES: ("Empieza tu negocio online", "en 24h"),
    Language.EN: ("Start your online business", "in 24h"),
}
TYPE_4_TEMPLATE_LABELS: dict[Language, dict[str, str]] = {
    Language.ES: {
        "store": "Tienda:",
        "products": "Productos\nganadores:",
        "scripts": "Guiones:",
        "payments": "Pagos:",
        "organic": "Organico:",
        "ads": "Ads:",
        "editing": "Edicion:",
    },
    Language.EN: {
        "store": "Store:",
        "products": "Winning\nproducts:",
        "scripts": "Scripts:",
        "payments": "Payments:",
        "organic": "Organic:",
        "ads": "Ads:",
        "editing": "Editing:",
    },
}
TYPE_4_TEMPLATE_ROWS: tuple[
    tuple[str, str, str, int, int, int, int, int, int, int, int, int, int],
    ...
] = (
    ("store", "shopify", "Shopify", 95, 456, 205, 91, 368, 431, 142, 568, 475, 50),
    (
        "products",
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
    ("scripts", "chatgpt", "ChatGPT", 96, 818, 211, 82, 354, 789, 142, 539, 846, 47),
    ("payments", "stripe", "Stripe", 98, 981, 176, 82, 359, 961, 130, 549, 1008, 48),
    ("organic", "tiktok", "TikTok", 94, 1144, 232, 88, 372, 1138, 118, 554, 1179, 47),
    ("ads", "meta_ads", "Meta Ads", 120, 1329, 127, 82, 306, 1300, 170, 507, 1363, 45),
    ("editing", "capcut", "CapCut", 92, 1504, 216, 82, 368, 1476, 130, 542, 1530, 47),
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
        self._face_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._eye_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
        self._people_detector = cv2.HOGDescriptor()
        self._people_detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

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

    def render_template_video(
        self,
        input_video: Path,
        job_dir: Path,
        language: Language = Language.ES,
    ) -> Path:
        job_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = job_dir / "template_overlay.png"
        output_path = job_dir / "template_video.mp4"
        template_language = self._type_4_language(language)
        self.build_type_4_template_overlay(template_language).save(overlay_path)

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

    def build_type_4_template_overlay(
        self,
        language: Language = Language.ES,
    ) -> Image.Image:
        template_language = self._type_4_language(language)
        image = Image.new(
            "RGBA",
            (self.settings.width, self.settings.height),
            (0, 0, 0, 0),
        )
        draw = ImageDraw.Draw(image)
        self._draw_type_4_title(draw, image.width, image.height, template_language)
        labels = TYPE_4_TEMPLATE_LABELS[template_language]
        for row in TYPE_4_TEMPLATE_ROWS:
            self._draw_type_4_template_row(image, draw, row, labels)
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
        image_progress = 0.0 if slide.fixed_asset else progress
        canvas = (
            self._fit_fixed_image(source_image)
            if slide.fixed_asset
            else self._cover_image(source_image, image_progress)
        )
        composed = canvas.convert("RGBA")
        if not slide.fixed_asset:
            composed = Image.alpha_composite(composed, self._gradient_overlay)
        self._draw_text(composed, slide, video_type)
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

    def _fit_fixed_image(self, source: Image.Image) -> Image.Image:
        width = self.settings.width
        height = self.settings.height
        background = self._cover_image(source, 0.0).filter(ImageFilter.GaussianBlur(18))
        scale = min(width / source.width, height / source.height)
        resized = source.resize(
            (
                max(1, int(source.width * scale)),
                max(1, int(source.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )
        x = (width - resized.width) // 2
        y = (height - resized.height) // 2
        background.paste(resized, (x, y))
        return background

    def _render_type_3_slide_frame(
        self,
        slide: SlidePlan,
        source_image: Image.Image,
        progress: float,
    ) -> np.ndarray:
        canvas = self._cover_image(source_image, progress).convert("RGBA")
        if slide.role == SlideRole.HOOK:
            self._draw_hook_text(canvas, slide.text)
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
        edge_margin = _scale_x(TEXT_CARD_EDGE_MARGIN, width)
        padding_x = _scale_x(TEXT_CARD_PADDING_X, width)
        padding_y = _scale_y(TEXT_CARD_PADDING_Y, height)
        connected_line_gap = -_scale_y(TEXT_CARD_LINE_OVERLAP, height)

        title_font = self._fit_single_line_text(
            title,
            draw,
            max_width=width - edge_margin * 2 - padding_x * 2,
            base_size=72,
            min_size=46,
            bold=False,
            stroke_width=0,
        )
        body_font = self._load_font(size=TYPE_3_BODY_FONT_SIZE, bold=False)
        body_lines = self._type_3_body_lines(
            subtitle,
            cta,
            draw=draw,
            font=body_font,
            max_width=width - edge_margin * 2 - padding_x * 2,
        )
        title_lines = [title] if title else []
        title_height = self._pill_lines_height(
            title_lines,
            title_font,
            draw,
            padding_y=padding_y,
            line_gap=0,
        )
        title_y = int(height * 0.270) - title_height // 2
        self._draw_pill_lines(
            draw,
            title_lines,
            title_font,
            start_y=max(70, title_y),
            canvas_width=width,
            padding_x=padding_x,
            padding_y=padding_y,
            line_gap=0,
        )
        if body_lines:
            self._draw_connected_pill_lines(
                draw,
                body_lines,
                body_font,
                start_y=int(height * 0.32),
                canvas_width=width,
                padding_x=padding_x,
                padding_y=padding_y,
                line_gap=connected_line_gap,
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

    @staticmethod
    def _type_4_language(language: Language) -> Language:
        try:
            parsed = Language(language)
        except (TypeError, ValueError):
            return Language.ES
        return parsed if parsed in TYPE_4_TITLE_LINES else Language.ES

    def _draw_type_4_title(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        language: Language,
    ) -> None:
        font = self._load_font(size=_scale_y(66, height), bold=True)
        line_gap = _scale_y(4, height)
        first_line, second_line = TYPE_4_TITLE_LINES[self._type_4_language(language)]
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
        labels: dict[str, str],
    ) -> None:
        (
            label_key,
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
        label = labels.get(label_key, label_key)
        width, height = image.size
        label_box = (
            _scale_x(label_x, width),
            _scale_y(label_y, height),
            _scale_x(label_x + label_w, width),
            _scale_y(label_y + label_h, height),
        )
        self._draw_white_label_pill(
            draw,
            label,
            label_box,
            radius=max(10, _scale_x(16, width)),
            horizontal_padding=_scale_x(28, width),
            vertical_padding=_scale_y(18, height),
            base_size=_scale_y(TYPE_4_LABEL_FONT_SIZE, height),
            min_size=_scale_y(TYPE_4_LABEL_MIN_FONT_SIZE, height),
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
            x = box[0] + ((box[2] - box[0]) - line_width) // 2 - bbox[0]
            draw_y = y - bbox[1]
            draw.text(
                (x, draw_y),
                line,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0),
            )
            if faux_bold_pixels:
                draw.text(
                    (x + faux_bold_pixels, draw_y),
                    line,
                    font=font,
                    fill=fill,
                )
            y += line_height + gap

    def _draw_white_label_pill(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        box: tuple[int, int, int, int],
        *,
        radius: int,
        horizontal_padding: int,
        vertical_padding: int,
        base_size: int,
        min_size: int,
    ) -> None:
        draw.rounded_rectangle(box, radius=radius, fill=(255, 255, 255))
        lines = text.splitlines()
        font = self._fit_prebroken_lines(
            lines,
            draw,
            max_width=(box[2] - box[0]) - horizontal_padding,
            max_height=(box[3] - box[1]) - vertical_padding,
            base_size=base_size,
            min_size=min_size,
            bold=False,
            stroke_width=0,
        )
        self._draw_centered_lines_in_box(
            draw,
            lines,
            font,
            box,
            fill=(0, 0, 0),
            stroke_width=0,
            faux_bold_pixels=1,
        )

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

    def _draw_text(
        self,
        image: Image.Image,
        slide: SlidePlan,
        video_type: VideoType,
    ) -> None:
        if not slide.text:
            return

        if slide.role == SlideRole.HOOK:
            self._draw_hook_text(image, slide.text)
            return

        if self._uses_hook_paragraph_style(slide, video_type):
            self._draw_hook_paragraph_text(image, slide.text)
            return

        self._draw_caption_card_text(image, slide.text, slide=slide)

    def _uses_hook_paragraph_style(
        self,
        slide: SlidePlan,
        video_type: VideoType,
    ) -> bool:
        if video_type != VideoType.TYPE_2:
            return False
        if slide.role not in {SlideRole.TIP1, SlideRole.TIP2, SlideRole.TIP3, SlideRole.TIP4}:
            return False
        text = slide.text.strip()
        return (
            "\n" not in text
            and len(text) <= 130
            and bool(re.match(r"^\d+\.\s+\S+", text))
        )

    def _draw_hook_text(self, image: Image.Image, text: str) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size

        stroke_width = max(2, _scale_x(4, width))
        font, lines = self._fit_hook_two_lines(
            text,
            draw,
            max_width=width - _scale_x(120, width),
            max_height=int(height * 0.30),
            base_size=self._scaled_text_size(96, minimum=34),
            min_size=self._scaled_text_size(42, minimum=18),
            stroke_width=stroke_width,
        )
        text_height = self._block_height(lines, font, draw, stroke_width=stroke_width)
        block_width = min(
            width - _scale_x(80, width),
            self._block_width(lines, font, draw, stroke_width=stroke_width)
            + _scale_x(40, width),
        )
        start_y = self._safe_text_start_y(
            image,
            block_width=block_width,
            block_height=text_height,
            preferred_centers=(0.38, 0.42, 0.34, 0.46, 0.50, 0.30, 0.54),
        )
        self._draw_lines(
            draw,
            lines,
            font,
            start_y=start_y,
            width=width,
            fill=(255, 255, 255),
            stroke_width=stroke_width,
        )

    def _draw_hook_paragraph_text(self, image: Image.Image, text: str) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        stroke_width = max(2, _scale_x(4, width))
        line_gap = _scale_y(8, height)
        font, lines = self._fit_text(
            text.strip(),
            draw,
            max_width=width - _scale_x(160, width),
            max_height=int(height * 0.34),
            base_size=self._scaled_text_size(46, minimum=20),
            min_size=self._scaled_text_size(24, minimum=13),
            bold=True,
            stroke_width=stroke_width,
            line_gap=line_gap,
        )
        text_height = self._block_height(
            lines,
            font,
            draw,
            stroke_width=stroke_width,
            line_gap=line_gap,
        )
        block_width = min(
            width - _scale_x(80, width),
            self._block_width(lines, font, draw, stroke_width=stroke_width)
            + _scale_x(40, width),
        )
        start_y = self._safe_text_start_y(
            image,
            block_width=block_width,
            block_height=text_height,
            preferred_centers=(0.40, 0.44, 0.36, 0.48, 0.52, 0.32, 0.56),
        )
        self._draw_lines(
            draw,
            lines,
            font,
            start_y=start_y,
            width=width,
            fill=(255, 255, 255),
            stroke_width=stroke_width,
            line_gap=line_gap,
        )

    def _fit_hook_two_lines(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        *,
        max_width: int,
        max_height: int,
        base_size: int,
        min_size: int,
        stroke_width: int,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        words = text.split()
        if len(words) < 2:
            return self._fit_text(
                text,
                draw,
                max_width=max_width,
                max_height=max_height,
                base_size=base_size,
                min_size=min_size,
                bold=True,
                stroke_width=stroke_width,
            )

        for size in range(base_size, min_size - 1, -2):
            font = self._load_font(size=size, bold=True)
            best_lines: list[str] | None = None
            best_score: float | None = None
            for split_at in range(1, len(words)):
                lines = [
                    " ".join(words[:split_at]),
                    " ".join(words[split_at:]),
                ]
                widths = [
                    self._text_size(
                        draw,
                        line,
                        font,
                        stroke_width=stroke_width,
                    )[0]
                    for line in lines
                ]
                if max(widths) > max_width:
                    continue
                height = self._block_height(lines, font, draw, stroke_width=stroke_width)
                if height > max_height:
                    continue
                score = abs(widths[0] - widths[1]) + max(widths) * 0.05
                if best_score is None or score < best_score:
                    best_score = score
                    best_lines = lines
            if best_lines is not None:
                return font, best_lines

        font = self._load_font(size=min_size, bold=True)
        return font, self._wrap_text(text, font, max_width, draw, stroke_width=stroke_width)[:2]

    def _draw_caption_card_text(
        self,
        image: Image.Image,
        text: str,
        *,
        slide: SlidePlan | None = None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        first_line, body = self._split_slide_text(text)
        edge_margin = _scale_x(TEXT_CARD_EDGE_MARGIN, width)
        padding_x = _scale_x(TEXT_CARD_PADDING_X, width)
        padding_y = _scale_y(TEXT_CARD_PADDING_Y, height)
        title_padding_y = _scale_y(TEXT_CARD_TITLE_PADDING_Y, height)
        connected_line_gap = -_scale_y(TEXT_CARD_LINE_OVERLAP, height)
        block_gap = _scale_y(TEXT_CARD_GROUP_GAP, height)
        max_text_width = max(1, width - (edge_margin * 2) - (padding_x * 2))

        title_font, title_lines = self._fit_text(
            first_line,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.18),
            base_size=self._scaled_text_size(39, minimum=17),
            min_size=self._scaled_text_size(30, minimum=14),
            bold=False,
            stroke_width=0,
        )
        body_font, body_lines = self._fit_text(
            body,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.40),
            base_size=self._scaled_text_size(37, minimum=16),
            min_size=self._scaled_text_size(28, minimum=13),
            bold=False,
            stroke_width=0,
        )

        groups: list[tuple[list[str], ImageFont.ImageFont, int, bool, int]] = []
        if first_line.strip():
            groups.append((title_lines, title_font, 0, False, title_padding_y))
        if body.strip():
            groups.append((body_lines, body_font, connected_line_gap, True, padding_y))
        if not groups:
            return

        group_heights = [
            self._pill_lines_height(
                lines,
                font,
                draw,
                padding_y=group_padding_y,
                line_gap=line_gap,
            )
            for lines, font, line_gap, _connected, group_padding_y in groups
        ]
        total_height = sum(group_heights) + block_gap * max(0, len(groups) - 1)
        block_width = min(
            width - (edge_margin * 2),
            max(
                self._pill_lines_width(
                    lines,
                    font,
                    draw,
                    padding_x=padding_x,
                )
                for lines, font, _line_gap, _connected, _group_padding_y in groups
            ),
        )
        start_y = self._safe_text_start_y(
            image,
            block_width=block_width,
            block_height=total_height,
            preferred_centers=self._caption_preferred_centers(slide),
        )
        start_y = self._clamp_fixed_screen_caption_y(
            slide,
            start_y,
            total_height,
            canvas_height=height,
        )

        y = start_y
        for index, (lines, font, line_gap, connected, group_padding_y) in enumerate(groups):
            if connected:
                y = self._draw_connected_pill_lines(
                    draw,
                    lines,
                    font,
                    start_y=y,
                    canvas_width=width,
                    padding_x=padding_x,
                    padding_y=group_padding_y,
                    line_gap=line_gap,
                )
            else:
                y = self._draw_pill_lines(
                    draw,
                    lines,
                    font,
                    start_y=y,
                    canvas_width=width,
                    padding_x=padding_x,
                    padding_y=group_padding_y,
                    line_gap=line_gap,
                )
            if index < len(groups) - 1:
                y += block_gap

    def _caption_preferred_centers(
        self,
        slide: SlidePlan | None,
    ) -> tuple[float, ...]:
        if (
            slide is not None and slide.fixed_asset and slide.role == SlideRole.TIP3
        ):
            return (0.42, 0.40, 0.44, 0.38, 0.36)
        if (
            slide is not None and slide.fixed_asset and slide.role == SlideRole.FEBRUARY
        ):
            return (0.24, 0.20, 0.30, 0.16, 0.36)
        return (0.50, 0.54, 0.46, 0.60, 0.40, 0.66, 0.34)

    def _clamp_fixed_screen_caption_y(
        self,
        slide: SlidePlan | None,
        start_y: int,
        block_height: int,
        *,
        canvas_height: int,
    ) -> int:
        if (
            slide is None
            or not slide.fixed_asset
            or slide.role != SlideRole.TIP3
        ):
            return start_y
        screen_top = int(canvas_height * 0.525)
        margin = _scale_y(54, canvas_height)
        max_start_y = max(0, screen_top - margin - block_height)
        return min(start_y, max_start_y)

    def _scaled_text_size(self, base_size: int, *, minimum: int) -> int:
        return max(minimum, _scale_x(base_size, self.settings.width))

    def _pill_lines_width(
        self,
        lines: list[str],
        font: ImageFont.ImageFont,
        draw: ImageDraw.ImageDraw,
        *,
        padding_x: int,
    ) -> int:
        if not lines:
            return 0
        return max(
            self._text_size(draw, line, font, stroke_width=0)[0] + padding_x * 2
            for line in lines
        )

    def _pill_lines_height(
        self,
        lines: list[str],
        font: ImageFont.ImageFont,
        draw: ImageDraw.ImageDraw,
        *,
        padding_y: int,
        line_gap: int,
    ) -> int:
        if not lines:
            return 0
        heights = [
            self._text_size(draw, line, font, stroke_width=0)[1] + padding_y * 2
            for line in lines
        ]
        return sum(heights) + line_gap * max(0, len(lines) - 1)

    def _draw_pill_lines(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        font: ImageFont.ImageFont,
        *,
        start_y: int,
        canvas_width: int,
        padding_x: int,
        padding_y: int,
        line_gap: int,
    ) -> int:
        y = start_y
        radius = max(6, _scale_x(12, canvas_width))
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=0)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            box_width = line_width + padding_x * 2
            box_height = line_height + padding_y * 2
            x = (canvas_width - box_width) // 2
            box = (x, y, x + box_width, y + box_height)
            draw.rounded_rectangle(box, radius=radius, fill=TEXT_CARD_FILL)
            text_x = x + padding_x - bbox[0]
            text_y = y + padding_y - bbox[1]
            self._draw_card_text(
                draw,
                (text_x, text_y),
                line,
                font,
                canvas_width=canvas_width,
            )
            y += box_height + line_gap
        return y - line_gap

    def _draw_connected_pill_lines(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        font: ImageFont.ImageFont,
        *,
        start_y: int,
        canvas_width: int,
        padding_x: int,
        padding_y: int,
        line_gap: int,
    ) -> int:
        boxes: list[tuple[tuple[int, int, int, int], tuple[int, int], str]] = []
        y = start_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=0)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            box_width = line_width + padding_x * 2
            box_height = line_height + padding_y * 2
            x = (canvas_width - box_width) // 2
            box = (x, y, x + box_width, y + box_height)
            text_pos = (x + padding_x - bbox[0], y + padding_y - bbox[1])
            boxes.append((box, text_pos, line))
            y += box_height + line_gap

        if not boxes:
            return start_y

        self._draw_connected_card_background(draw, boxes, canvas_width)
        for _box, text_pos, line in boxes:
            self._draw_card_text(
                draw,
                text_pos,
                line,
                font,
                canvas_width=canvas_width,
            )
        return boxes[-1][0][3]

    def _draw_connected_card_background(
        self,
        draw: ImageDraw.ImageDraw,
        boxes: list[tuple[tuple[int, int, int, int], tuple[int, int], str]],
        canvas_width: int,
    ) -> None:
        mask_height = max(box[3] for box, _text_pos, _line in boxes) + _scale_x(8, canvas_width)
        mask = Image.new("L", (canvas_width, mask_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        for box, _text_pos, _line in boxes:
            mask_draw.rectangle(box, fill=255)

        smooth_radius = max(2, _scale_x(3, canvas_width))
        mask = mask.filter(ImageFilter.GaussianBlur(smooth_radius))
        mask = mask.point(lambda value: 255 if value >= 128 else 0)
        draw.bitmap((0, 0), mask, fill=TEXT_CARD_FILL)

    def _draw_card_text(
        self,
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        text: str,
        font: ImageFont.ImageFont,
        *,
        canvas_width: int,
    ) -> None:
        draw.text(position, text, font=font, fill=TEXT_CARD_TEXT)
        faux_bold = _scale_x(TEXT_CARD_FAUX_BOLD_PIXELS, canvas_width)
        if faux_bold > 0:
            draw.text(
                (position[0] + faux_bold, position[1]),
                text,
                font=font,
                fill=TEXT_CARD_TEXT,
            )

    def _block_width(
        self,
        lines: list[str],
        font: ImageFont.ImageFont,
        draw: ImageDraw.ImageDraw,
        *,
        stroke_width: int,
    ) -> int:
        if not lines:
            return 0
        return max(
            self._text_size(draw, line, font, stroke_width=stroke_width)[0]
            for line in lines
        )

    def _safe_text_start_y(
        self,
        image: Image.Image,
        *,
        block_width: int,
        block_height: int,
        preferred_centers: tuple[float, ...],
    ) -> int:
        width, height = image.size
        top_margin = max(16, _scale_y(70, height))
        bottom_margin = max(16, _scale_y(110, height))
        min_y = top_margin
        max_y = max(min_y, height - block_height - bottom_margin)
        regions = self._text_avoid_regions(image)
        centers = list(preferred_centers)
        centers.extend(value / 100.0 for value in range(18, 84, 4))
        candidates: list[int] = []
        def add_candidate(y: int) -> None:
            y = max(min_y, min(max_y, y))
            if y not in candidates:
                candidates.append(y)

        for center in centers:
            y = int(round(center * height - block_height / 2))
            add_candidate(y)
        for y in self._clear_gap_text_candidates(
            block_width=block_width,
            block_height=block_height,
            canvas_width=width,
            canvas_height=height,
            min_y=min_y,
            max_y=max_y,
            avoid_regions=regions,
        ):
            add_candidate(y)
        if min_y not in candidates:
            candidates.append(min_y)
        if max_y not in candidates:
            candidates.append(max_y)

        primary_center = preferred_centers[0] if preferred_centers else 0.55
        luminance = np.asarray(image.convert("L"), dtype=np.float32)
        best_y = min(
            candidates,
            key=lambda y: self._text_position_score(
                y,
                block_width=block_width,
                block_height=block_height,
                canvas_width=width,
                canvas_height=height,
                avoid_regions=regions,
                preferred_center=primary_center,
                luminance=luminance,
            ),
        )
        return best_y

    def _clear_gap_text_candidates(
        self,
        *,
        block_width: int,
        block_height: int,
        canvas_width: int,
        canvas_height: int,
        min_y: int,
        max_y: int,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]],
    ) -> list[int]:
        x = max(0, (canvas_width - block_width) // 2)
        text_left = x
        text_right = min(canvas_width, x + block_width)
        margin = _scale_y(18, canvas_height)
        forbidden: list[tuple[int, int]] = []
        for region, _weight in avoid_regions:
            if region[2] <= text_left or region[0] >= text_right:
                continue
            start = max(min_y, region[1] - block_height - margin)
            end = min(max_y, region[3] + margin)
            if end > start:
                forbidden.append((start, end))
        if not forbidden:
            return []

        forbidden.sort()
        merged: list[list[int]] = []
        for start, end in forbidden:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        candidates: list[int] = []
        gap_start = min_y
        for start, end in merged:
            if start > gap_start:
                candidates.extend(self._gap_candidate_positions(gap_start, start))
            gap_start = max(gap_start, end)
        if gap_start < max_y:
            candidates.extend(self._gap_candidate_positions(gap_start, max_y))
        return candidates

    def _gap_candidate_positions(self, start: int, end: int) -> list[int]:
        if end <= start:
            return []
        center = (start + end) // 2
        return [center, start, end]

    def _text_position_score(
        self,
        y: int,
        *,
        block_width: int,
        block_height: int,
        canvas_width: int,
        canvas_height: int,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]],
        preferred_center: float,
        luminance: np.ndarray,
    ) -> float:
        x = max(0, (canvas_width - block_width) // 2)
        box = (x, y, min(canvas_width, x + block_width), min(canvas_height, y + block_height))
        box_area = max(1, self._box_area(box))
        center = (box[1] + box[3]) / 2.0 / max(canvas_height, 1)
        score = abs(center - preferred_center) * 2.2
        score += abs(center - 0.5) * 0.45
        score += self._background_clutter_score(luminance, box) * 0.6
        for region, weight in avoid_regions:
            overlap = self._intersection_area(box, region)
            if overlap <= 0:
                continue
            region_area = max(1, self._box_area(region))
            score += weight * max(overlap / box_area, overlap / region_area)
        return score

    def _background_clutter_score(
        self,
        luminance: np.ndarray,
        box: tuple[int, int, int, int],
    ) -> float:
        left, top, right, bottom = box
        crop = luminance[top:bottom, left:right]
        if crop.size < 16:
            return 0.0
        if crop.shape[0] > 180 or crop.shape[1] > 180:
            scale = min(180 / crop.shape[0], 180 / crop.shape[1])
            crop = cv2.resize(
                crop,
                (
                    max(1, int(crop.shape[1] * scale)),
                    max(1, int(crop.shape[0] * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )
        contrast = float(np.std(crop)) / 80.0
        edge_x = float(np.mean(np.abs(np.diff(crop, axis=1)))) / 26.0 if crop.shape[1] > 1 else 0.0
        edge_y = float(np.mean(np.abs(np.diff(crop, axis=0)))) / 26.0 if crop.shape[0] > 1 else 0.0
        return min(3.0, contrast + edge_x + edge_y)

    def _text_avoid_regions(
        self,
        image: Image.Image,
    ) -> list[tuple[tuple[int, int, int, int], float]]:
        width, height = image.size
        try:
            rgb = np.asarray(image.convert("RGB"))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        except cv2.error:
            return []

        regions: list[tuple[tuple[int, int, int, int], float]] = []
        for x, y, w, h in self._detect_render_faces(gray):
            face = self._expanded_box(
                (int(x), int(y), int(x + w), int(y + h)),
                width,
                height,
                x_pad=int(w * 0.38),
                y_pad=int(h * 0.38),
            )
            regions.append((face, TEXT_FACE_AVOID_WEIGHT))

        for x, y, w, h in self._detect_render_eyes(gray):
            eye_face = self._expanded_box(
                (
                    int(x - w * 1.4),
                    int(y - h * 1.2),
                    int(x + w * 2.4),
                    int(y + h * 3.6),
                ),
                width,
                height,
                x_pad=int(w * 0.45),
                y_pad=int(h * 0.45),
            )
            regions.append((eye_face, TEXT_EYE_AVOID_WEIGHT))

        for x, y, w, h in self._detect_render_people(rgb):
            body = self._expanded_box(
                (int(x), int(y), int(x + w), int(y + h)),
                width,
                height,
                x_pad=int(w * 0.12),
                y_pad=int(h * 0.04),
            )
            head = self._expanded_box(
                (
                    int(x + w * 0.15),
                    int(y),
                    int(x + w * 0.85),
                    int(y + h * 0.33),
                ),
                width,
                height,
                x_pad=int(w * 0.14),
                y_pad=int(h * 0.08),
            )
            regions.append((body, TEXT_BODY_AVOID_WEIGHT))
            regions.append((head, TEXT_HEAD_AVOID_WEIGHT))
        return regions

    def _detect_render_faces(self, gray: np.ndarray) -> np.ndarray:
        if self._face_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        height, width = gray.shape[:2]
        min_size = max(24, _scale_x(42, width))
        detected = self._face_detector.detectMultiScale(
            gray,
            scaleFactor=1.16,
            minNeighbors=4,
            minSize=(min_size, min_size),
        )
        if len(detected) == 0:
            return np.empty((0, 4), dtype=np.int32)
        return np.asarray(detected, dtype=np.int32)

    def _detect_render_eyes(self, gray: np.ndarray) -> np.ndarray:
        if self._eye_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        height, width = gray.shape[:2]
        min_size = max(10, _scale_x(22, width))
        detected = self._eye_detector.detectMultiScale(
            gray,
            scaleFactor=1.10,
            minNeighbors=5,
            minSize=(min_size, min_size),
        )
        if len(detected) == 0:
            return np.empty((0, 4), dtype=np.int32)
        return np.asarray(detected, dtype=np.int32)

    def _detect_render_people(self, rgb: np.ndarray) -> np.ndarray:
        height, width = rgb.shape[:2]
        scale = min(1.0, 840.0 / max(height, width, 1))
        if scale < 1.0:
            resized = cv2.resize(
                rgb,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            resized = rgb
        boxes, weights = self._people_detector.detectMultiScale(
            resized,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        if len(boxes) == 0:
            return np.empty((0, 4), dtype=np.int32)
        if len(weights) > 0:
            boxes = np.asarray(
                [
                    box
                    for box, weight in zip(boxes, weights)
                    if float(weight) >= 0.22
                ],
                dtype=np.float32,
            )
            if len(boxes) == 0:
                return np.empty((0, 4), dtype=np.int32)
        boxes = np.asarray(boxes, dtype=np.float32)
        if scale < 1.0:
            boxes[:, :4] = boxes[:, :4] / scale
        return boxes.astype(np.int32)

    def _expanded_box(
        self,
        box: tuple[int, int, int, int],
        width: int,
        height: int,
        *,
        x_pad: int,
        y_pad: int,
    ) -> tuple[int, int, int, int]:
        return (
            max(0, box[0] - x_pad),
            max(0, box[1] - y_pad),
            min(width, box[2] + x_pad),
            min(height, box[3] + y_pad),
        )

    def _intersection_area(
        self,
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> int:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        if right <= left or bottom <= top:
            return 0
        return (right - left) * (bottom - top)

    def _box_area(self, box: tuple[int, int, int, int]) -> int:
        return max(0, box[2] - box[0]) * max(0, box[3] - box[1])

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
        line_gap: int = 16,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        size = base_size
        while size >= min_size:
            font = self._load_font(size=size, bold=bold)
            lines = self._wrap_text(text, font, max_width, draw, stroke_width=stroke_width)
            height = self._block_height(
                lines,
                font,
                draw,
                stroke_width=stroke_width,
                line_gap=line_gap,
            )
            if height <= max_height:
                return font, lines
            size -= 4
        font = self._load_font(size=min_size, bold=bold)
        lines = self._wrap_text(text, font, max_width, draw, stroke_width=stroke_width)
        return font, lines

    def _split_slide_text(self, text: str) -> tuple[str, str]:
        parts = text.split("\n", 1)
        if len(parts) == 1:
            return "", parts[0].strip()
        first_line = parts[0].strip()
        body = parts[1].strip()
        if first_line.endswith(".") and first_line[:-1].isdigit() and body:
            return "", f"{first_line} {body}".strip()
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
        line_gap: int = 16,
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
            y += line_height + line_gap

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
        line_gap: int = 16,
    ) -> int:
        height = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=stroke_width)
            height += (bbox[3] - bbox[1]) + line_gap
        return max(height - line_gap, 0)

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
