from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2
import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import Settings
from app.models import Language, SlidePlan, SlideRole, VideoPlan, VideoType
from app.opencv_compat import CV2_ERROR, build_cascade, build_people_detector


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
TIKTOK_OVERLAY_FONT_CANDIDATES = (
    "TikTokSans-Bold.ttf",
    "TikTokDisplay-Bold.ttf",
    "TikTokText-Bold.ttf",
    "ProximaNova-Bold.ttf",
    "Proxima Nova Bold.ttf",
    "AvenirNext-Bold.ttf",
    "Avenir Next Bold.ttf",
    "Gotham-Bold.ttf",
    "Gotham Bold.ttf",
    "Arial Rounded MT Bold.ttf",
    "ARLRDBD.TTF",
    "C:/Windows/Fonts/ARLRDBD.TTF",
    "arialbd.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
HOOK_TEXT_STROKE_FILL = (12, 12, 12)
HOOK_TEXT_STROKE_WIDTH = 4
TYPE_2_HOOK_STROKE_WIDTH = 5
TYPE_2_HOOK_INNER_STROKE_WIDTH = 1
TYPE_2_HOOK_FONT_SCALE = 0.99
TYPE_2_COSTLY_MISTAKES_HOOK_FONT_SCALE = 0.92
FIXED_SCREEN_TEXT_MARGIN = 78
FEBRUARY_FIXED_SCREEN_TEXT_MARGIN = 30
FEBRUARY_TITLE_MIN_BOX_WIDTH = 380
FEBRUARY_TEXT_GROUP_GAP = 38
HOOK_BASE_FONT_SIZE = 126
HOOK_MIN_FONT_SIZE = 54
HOOK_SIDE_MARGIN = 48
TYPE_1_HOOK_SIDE_MARGIN = 24
SAFE_TEXT_TOP_MARGIN = 160
SAFE_TEXT_BOTTOM_MARGIN = 230
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
TYPE_3_TITLE_FONT_SIZE = 66
TYPE_3_BODY_FONT_SIZE = 58
TYPE_3_TOOL_VERTICAL_NUDGE_RATIO = 0.015
TYPE_4_TARGET_SECONDS = 7.5
TYPE_4_TITLE_STROKE_WIDTH = 3
TYPE_4_TITLE_INNER_STROKE_WIDTH = 1
TYPE_4_TEXT_STROKE_WIDTH = 4
TYPE_4_TOOL_NAME_INNER_STROKE_WIDTH = 0
TYPE_4_STORY_CAPTION_PRIMARY_CENTER = 0.30
TYPE_4_LABEL_FONT_SIZE = 39
TYPE_4_LABEL_MIN_FONT_SIZE = 27
TYPE_4_EN_PAYMENTS_LABEL_EXTRA_WIDTH = 48
TEXT_CARD_FILL = (255, 255, 255, 246)
TEXT_CARD_TEXT = (0, 0, 0)
TEXT_FACE_AVOID_WEIGHT = 260.0
TEXT_EYE_AVOID_WEIGHT = 220.0
TEXT_HEAD_AVOID_WEIGHT = 120.0
TEXT_BODY_AVOID_WEIGHT = 2.5
TEXT_FALLBACK_HEAD_AVOID_WEIGHT = 150.0
TEXT_FALLBACK_BODY_AVOID_WEIGHT = 3.5
TEXT_CARD_EDGE_MARGIN = 84
TEXT_CARD_PADDING_X = 30
TEXT_CARD_PADDING_Y = 10
TEXT_CARD_TITLE_PADDING_Y = 13
TEXT_CARD_TITLE_FONT_SIZE = 40
TEXT_CARD_TITLE_MIN_FONT_SIZE = 31
TEXT_CARD_BODY_FONT_SIZE = 38
TEXT_CARD_BODY_MIN_FONT_SIZE = 29
TEXT_CARD_LINE_OVERLAP = 12
TEXT_CARD_GROUP_GAP = 20
TEXT_CARD_FAUX_BOLD_PIXELS = 1
TEXT_CARD_CORNER_RADIUS = 20
TEXT_AVOID_CLEARANCE_MARGIN = 58
TEXT_DETECTION_MAX_DIMENSION = 720
TEXT_OVERLAY_CACHE_MAX_ITEMS = 8
FIXED_CANVAS_CACHE_MAX_ITEMS = 2
FONT_CACHE_MAX_ITEMS = 256
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
    ("organic", "tiktok", "TikTok", 94, 1144, 232, 88, 360, 1128, 150, 554, 1179, 47),
    ("ads", "meta_ads", "Meta Ads", 120, 1329, 127, 82, 286, 1288, 150, 482, 1345, 45),
    ("editing", "capcut", "CapCut", 92, 1504, 216, 82, 368, 1476, 130, 542, 1530, 47),
)
TYPE_4_STORY_CAPTION_ROLES = {
    SlideRole.STORY_MCDONALD,
    SlideRole.STORY_BUILDING_STORE,
    SlideRole.STORY_FIRST_FAILURE,
    SlideRole.STORY_DEEP_FAILURE,
    SlideRole.STORY_DROPRADAR,
    SlideRole.STORY_SUCCESS_COMIC,
}
STORY_DROPRADAR_BRAND_TEXT = "Dropradar"


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
        self._face_detector = build_cascade("haarcascade_frontalface_default.xml")
        self._profile_face_detector = build_cascade(
            "haarcascade_profileface.xml",
            required=False,
        )
        self._eye_detector = build_cascade("haarcascade_eye.xml")
        self._people_detector = build_people_detector()
        self._text_overlay_cache: dict[tuple[object, ...], Image.Image] = {}
        self._type_4_overlay_cache: dict[Language, Image.Image] = {}
        self._fixed_canvas_cache: dict[tuple[object, ...], Image.Image] = {}
        self._font_cache: dict[tuple[str, int, bool], ImageFont.ImageFont] = {}

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
                "-preset", self.settings.ffmpeg_preset,
                "-crf", "23",
                "-movflags", "+faststart",
            ],
        ) as writer:
            source_images: dict[int, Image.Image] = {}
            fixed_frames: dict[int, np.ndarray] = {}
            for slide in plan.slides:
                if slide.fixed_asset:
                    fixed_frames[slide.index] = np.asarray(
                        self.render_slide_still(slide, plan.video_type)
                    )
                    continue
                source_image = self._load_source_image(slide.media.local_path)
                source_images[slide.index] = source_image
                self._prepare_slide_text_overlay(
                    slide,
                    source_image,
                    plan.video_type,
                )

            def render_frame(slide: SlidePlan, progress: float) -> np.ndarray:
                fixed = fixed_frames.get(slide.index)
                if fixed is not None:
                    return fixed
                return self._render_slide_frame(
                    slide,
                    source_images[slide.index],
                    progress,
                    plan.video_type,
                )

            for index, slide in enumerate(plan.slides):
                main_frames = total_frames
                if index < len(plan.slides) - 1:
                    main_frames = max(1, total_frames - transition_frames)

                for frame_index in range(main_frames):
                    progress = frame_index / max(main_frames - 1, 1)
                    frame = render_frame(slide, progress)
                    writer.append_data(frame)

                if index < len(plan.slides) - 1:
                    current_final = render_frame(slide, 1.0)
                    next_slide = plan.slides[index + 1]
                    next_initial = render_frame(next_slide, 0.0)
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
        if slide.fixed_asset:
            canvas = self._cached_fixed_slide_canvas(slide, video_type).convert("RGBA")
            if video_type == VideoType.TYPE_3:
                if slide.role != SlideRole.HOOK:
                    self._composite_type_3_tool_overlay(canvas, slide)
            else:
                self._draw_text(canvas, slide, video_type)
            return canvas.convert("RGB")
        source_image = self._load_source_image(slide.media.local_path)
        frame = self._render_slide_frame(slide, source_image, 1.0, video_type)
        return Image.fromarray(frame)

    def _cached_fixed_slide_canvas(
        self,
        slide: SlidePlan,
        video_type: VideoType,
    ) -> Image.Image:
        path = slide.media.local_path
        try:
            stat = path.stat()
            file_signature: tuple[object, ...] = (
                str(path.resolve()),
                stat.st_size,
                stat.st_mtime_ns,
            )
        except OSError:
            file_signature = (str(path),)
        fit_mode = "cover" if video_type == VideoType.TYPE_3 else "fixed"
        cache_key = (
            *file_signature,
            fit_mode,
            self.settings.width,
            self.settings.height,
        )
        cached = self._fixed_canvas_cache.get(cache_key)
        if cached is None:
            source_image = self._load_source_image(path)
            cached = (
                self._cover_image(source_image, 1.0)
                if fit_mode == "cover"
                else self._fit_fixed_image(source_image)
            ).convert("RGB")
            self._fixed_canvas_cache[cache_key] = cached
            if len(self._fixed_canvas_cache) > FIXED_CANVAS_CACHE_MAX_ITEMS:
                oldest_key = next(iter(self._fixed_canvas_cache))
                self._fixed_canvas_cache.pop(oldest_key, None)
        return cached.copy()

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
        self._cached_type_4_template_overlay(template_language).save(overlay_path)

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
            self.settings.ffmpeg_preset,
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

    def _cached_type_4_template_overlay(self, language: Language) -> Image.Image:
        cached = self._type_4_overlay_cache.get(language)
        if cached is None:
            cached = self.build_type_4_template_overlay(language)
            self._type_4_overlay_cache[language] = cached
        return cached.copy()

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
        self._draw_story_screen_brand(composed, slide)
        self._draw_text(composed, slide, video_type)
        return np.asarray(composed.convert("RGB"))

    def _draw_story_screen_brand(
        self,
        image: Image.Image,
        slide: SlidePlan,
    ) -> None:
        if slide.role != SlideRole.STORY_DROPRADAR:
            return
        screen_quad = self._story_laptop_screen_quad(image)
        if screen_quad is None:
            LOGGER.warning(
                "Could not locate laptop screen for integrated Dropradar browser tab"
            )
            return

        browser_width = 1000
        browser_height = 220
        browser_bar = Image.new(
            "RGBA",
            (browser_width, browser_height),
            (231, 234, 238, 255),
        )
        draw = ImageDraw.Draw(browser_bar)
        draw.rectangle((0, 92, browser_width, browser_height), fill=(250, 251, 252, 255))
        dot_colors = ((238, 95, 91), (244, 188, 63), (89, 190, 91))
        for index, color in enumerate(dot_colors):
            center_x = 34 + index * 34
            draw.ellipse((center_x - 9, 35, center_x + 9, 53), fill=(*color, 255))

        tab_box = (145, 15, 690, 96)
        draw.rounded_rectangle(
            tab_box,
            radius=24,
            fill=(255, 255, 255, 255),
            outline=(205, 210, 215, 255),
            width=3,
        )
        draw.ellipse((178, 39, 208, 69), fill=(38, 151, 82, 255))
        font = self._load_font(size=52, bold=True)
        draw.text(
            (226, 26),
            STORY_DROPRADAR_BRAND_TEXT,
            font=font,
            fill=(28, 104, 60, 255),
        )
        draw.rounded_rectangle(
            (120, 120, 920, 194),
            radius=35,
            fill=(238, 240, 243, 255),
            outline=(209, 213, 218, 255),
            width=3,
        )
        draw.ellipse((151, 143, 176, 168), outline=(112, 119, 126, 255), width=4)
        draw.line((171, 164, 184, 178), fill=(112, 119, 126, 255), width=4)

        top_left, top_right, bottom_right, bottom_left = screen_quad
        band_fraction = 0.25
        band_bottom_right = top_right + (bottom_right - top_right) * band_fraction
        band_bottom_left = top_left + (bottom_left - top_left) * band_fraction
        destination = np.asarray(
            [top_left, top_right, band_bottom_right, band_bottom_left],
            dtype=np.float32,
        )
        source = np.asarray(
            [
                (0, 0),
                (browser_width - 1, 0),
                (browser_width - 1, browser_height - 1),
                (0, browser_height - 1),
            ],
            dtype=np.float32,
        )
        transform = cv2.getPerspectiveTransform(source, destination)
        warped = cv2.warpPerspective(
            np.asarray(browser_bar),
            transform,
            image.size,
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        image.alpha_composite(Image.fromarray(warped, mode="RGBA"))

    @staticmethod
    def _story_laptop_screen_quad(
        image: Image.Image,
    ) -> np.ndarray | None:
        """Locate the bright dashboard bounded by the laptop's dark bezel."""
        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        roi_right = max(1, int(round(width * 0.70)))
        roi_top = max(0, int(round(height * 0.44)))
        roi_bottom = min(height, int(round(height * 0.88)))
        roi = rgb[roi_top:roi_bottom, :roi_right]
        if not roi.size:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        bright_neutral = ((hsv[:, :, 1] <= 115) & (hsv[:, :, 2] >= 132)).astype(
            np.uint8
        )
        close_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (5, 5),
        )
        cleaned = cv2.morphologyEx(bright_neutral, cv2.MORPH_CLOSE, close_kernel)
        contours, _ = cv2.findContours(
            cleaned,
            # The bright screen is often nested inside a dark bezel, which is
            # itself surrounded by a bright wall. RETR_LIST keeps that inner
            # screen contour instead of returning only the wall.
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        candidates: list[tuple[float, np.ndarray]] = []
        image_area = float(width * height)
        roi_rgb = roi.astype(np.int16)
        green_pixels = (
            (roi_rgb[:, :, 1] >= 70)
            & (roi_rgb[:, :, 1] - roi_rgb[:, :, 0] >= 12)
            & (roi_rgb[:, :, 1] - roi_rgb[:, :, 2] >= 6)
        )

        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not (image_area * 0.018 <= area <= image_area * 0.22):
                continue
            x, y, box_width, box_height = cv2.boundingRect(contour)
            if box_width < width * 0.16 or box_height < height * 0.12:
                continue
            if box_width > width * 0.64 or box_height > height * 0.43:
                continue
            absolute_y = roi_top + y
            if absolute_y < height * 0.48 or absolute_y > height * 0.76:
                continue
            contour_mask = np.zeros(cleaned.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [contour], -1, 1, thickness=-1)
            green_ratio = float(
                np.count_nonzero(green_pixels & (contour_mask > 0))
            ) / max(area, 1.0)
            if green_ratio < 0.003:
                continue

            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.035 * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                points = approx.reshape(4, 2).astype(np.float32)
            else:
                points = cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32)
            points[:, 1] += roi_top
            ordered = VideoRenderer._order_quad_points(points)
            top_width = np.linalg.norm(ordered[1] - ordered[0])
            bottom_width = np.linalg.norm(ordered[2] - ordered[3])
            left_height = np.linalg.norm(ordered[3] - ordered[0])
            right_height = np.linalg.norm(ordered[2] - ordered[1])
            mean_width = (top_width + bottom_width) / 2.0
            mean_height = (left_height + right_height) / 2.0
            aspect = mean_width / max(mean_height, 1.0)
            if not (0.55 <= aspect <= 1.80):
                continue
            edge_penalty = 0.82 if x <= 2 else 1.0
            score = area * (1.0 + min(green_ratio, 0.10) * 3.0) * edge_penalty
            candidates.append((score, ordered))

        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _order_quad_points(points: np.ndarray) -> np.ndarray:
        ordered = np.zeros((4, 2), dtype=np.float32)
        coordinate_sum = points.sum(axis=1)
        coordinate_difference = np.diff(points, axis=1).reshape(-1)
        ordered[0] = points[np.argmin(coordinate_sum)]
        ordered[2] = points[np.argmax(coordinate_sum)]
        ordered[1] = points[np.argmin(coordinate_difference)]
        ordered[3] = points[np.argmax(coordinate_difference)]
        return ordered

    def _prepare_slide_text_overlay(
        self,
        slide: SlidePlan,
        source_image: Image.Image,
        video_type: VideoType,
    ) -> None:
        if not slide.text or video_type == VideoType.TYPE_3:
            return
        cache_key = self._slide_overlay_cache_key(
            slide,
            video_type,
            (self.settings.width, self.settings.height),
        )
        if cache_key in self._text_overlay_cache:
            return

        source_regions = self._text_avoid_regions(source_image)
        avoid_regions = self._project_cover_avoid_regions(
            source_image,
            source_regions,
            progresses=(0.0, 0.5, 1.0),
        )
        layout_image = self._cover_image(source_image, 0.5).convert("RGBA")
        self._draw_text(
            layout_image,
            slide,
            video_type,
            avoid_regions=avoid_regions,
        )

    def _project_cover_avoid_regions(
        self,
        source: Image.Image,
        regions: list[tuple[tuple[int, int, int, int], float]],
        *,
        progresses: tuple[float, ...],
    ) -> list[tuple[tuple[int, int, int, int], float]]:
        if not regions:
            return []
        canvas_width = self.settings.width
        canvas_height = self.settings.height
        base_scale = max(
            canvas_width / max(source.width, 1),
            canvas_height / max(source.height, 1),
        )
        projected_regions: list[tuple[tuple[int, int, int, int], float]] = []
        for region, weight in regions:
            swept_boxes: list[tuple[int, int, int, int]] = []
            for progress in progresses:
                scale = base_scale * (1.0 + 0.06 * progress)
                resized_width = max(1, int(source.width * scale))
                resized_height = max(1, int(source.height * scale))
                offset_x = int(
                    max(0, resized_width - canvas_width)
                    * (0.3 + 0.4 * progress)
                )
                offset_y = int(max(0, resized_height - canvas_height) * 0.5)
                left = max(0, min(canvas_width, int(region[0] * scale) - offset_x))
                top = max(0, min(canvas_height, int(region[1] * scale) - offset_y))
                right = max(
                    0,
                    min(canvas_width, int(round(region[2] * scale)) - offset_x),
                )
                bottom = max(
                    0,
                    min(canvas_height, int(round(region[3] * scale)) - offset_y),
                )
                if right > left and bottom > top:
                    swept_boxes.append((left, top, right, bottom))
            if not swept_boxes:
                continue
            projected_regions.append(
                (
                    (
                        min(box[0] for box in swept_boxes),
                        min(box[1] for box in swept_boxes),
                        max(box[2] for box in swept_boxes),
                        max(box[3] for box in swept_boxes),
                    ),
                    weight,
                )
            )
        return projected_regions

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
            return np.asarray(canvas.convert("RGB"))
        else:
            self._composite_type_3_tool_overlay(canvas, slide)
        return np.asarray(canvas.convert("RGB"))

    def _composite_type_3_tool_overlay(
        self,
        image: Image.Image,
        slide: SlidePlan,
    ) -> None:
        cache_key = self._slide_overlay_cache_key(
            slide,
            VideoType.TYPE_3,
            image.size,
        )
        overlay = self._text_overlay_cache.get(cache_key)
        if overlay is None:
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            self._draw_type_3_tool_slide(overlay, slide)
            self._remember_text_overlay(cache_key, overlay)
        image.alpha_composite(overlay)

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
        max_text_width = width - edge_margin * 2
        stroke_width = max(2, _scale_x(TYPE_3_TEXT_STROKE_WIDTH, width))
        body_line_gap = _scale_y(8, height)
        title_font_size = _scale_x(TYPE_3_TITLE_FONT_SIZE, width)

        title_font = self._fit_single_line_text(
            title,
            draw,
            max_width=max_text_width,
            base_size=title_font_size,
            min_size=title_font_size,
            bold=True,
            stroke_width=stroke_width,
        )
        body_font = self._load_overlay_font(TYPE_3_BODY_FONT_SIZE, True)
        body_lines = self._type_3_body_lines(
            subtitle,
            cta,
            draw=draw,
            font=body_font,
            max_width=max_text_width,
        )
        title_lines = [title] if title else []
        title_height = self._block_height(
            title_lines,
            title_font,
            draw,
            stroke_width=stroke_width,
            line_gap=0,
        )
        vertical_nudge = int(height * TYPE_3_TOOL_VERTICAL_NUDGE_RATIO)
        title_y = int(height * 0.270) - title_height // 2 + vertical_nudge
        self._draw_lines(
            draw,
            title_lines,
            title_font,
            start_y=max(70, title_y),
            width=width,
            fill=(255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=HOOK_TEXT_STROKE_FILL,
            line_gap=0,
        )
        if body_lines:
            self._draw_lines(
                draw,
                body_lines,
                body_font,
                start_y=int(height * 0.32) + vertical_nudge,
                width=width,
                fill=(255, 255, 255),
                stroke_width=stroke_width,
                stroke_fill=HOOK_TEXT_STROKE_FILL,
                line_gap=body_line_gap,
            )

        tool_key = self._type_3_tool_key(slide.role, slide.text)
        icon_box_size = int(width * 0.44)
        icon_top = int(height * TYPE_3_ICON_TOP_RATIO.get(tool_key, 0.434)) + vertical_nudge
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
        font_loader: Callable[[int, bool], ImageFont.ImageFont] | None = None,
    ) -> ImageFont.ImageFont:
        load_font = font_loader or (
            lambda font_size, is_bold: self._load_font(size=font_size, bold=is_bold)
        )
        size = base_size
        while size >= min_size:
            font = load_font(size, bold)
            height = self._block_height(lines, font, draw, stroke_width=stroke_width)
            widths = [
                self._text_size(draw, line, font, stroke_width=stroke_width)[0]
                for line in lines
            ]
            if height <= max_height and (not widths or max(widths) <= max_width):
                return font
            size -= 2
        emergency_min_size = max(12, int(min_size * 0.55))
        while size >= emergency_min_size:
            font = load_font(size, bold)
            height = self._block_height(lines, font, draw, stroke_width=stroke_width)
            widths = [
                self._text_size(draw, line, font, stroke_width=stroke_width)[0]
                for line in lines
            ]
            if height <= max_height and (not widths or max(widths) <= max_width):
                return font
            size -= 2
        return load_font(emergency_min_size, bold)

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
        y0: int | None = None,
    ) -> None:
        tool_key = self._type_3_tool_key(role, text)
        label, fill, text_fill = TYPE_3_TOOL_BADGES.get(
            tool_key,
            ("Tool", (255, 255, 255), (0, 0, 0)),
        )
        badge_size = int(width * 0.38)
        x0 = (width - badge_size) // 2
        if y0 is None:
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
            self._draw_type_3_badge(draw, role, text, width, image.height, y0=y0)
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
        # The animated tool template uses a clearly bold hook while retaining
        # the existing white fill and black outline over moving video.
        font = self._load_font(size=_scale_y(60, height), bold=True)
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
        first_x = (width - first_width) // 2
        draw.text(
            (first_x, y),
            first_line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TITLE_STROKE_WIDTH,
            stroke_fill=(0, 0, 0),
        )
        draw.text(
            (first_x, y),
            first_line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TITLE_INNER_STROKE_WIDTH,
            stroke_fill=(255, 255, 255),
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
        draw.text(
            (second_x, second_y),
            second_line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=TYPE_4_TITLE_INNER_STROKE_WIDTH,
            stroke_fill=(255, 255, 255),
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
        label_left = label_x
        label_right = label_x + label_w
        if label_key == "payments" and label == "Payments:":
            extra_each_side = TYPE_4_EN_PAYMENTS_LABEL_EXTRA_WIDTH // 2
            label_left -= extra_each_side
            label_right += extra_each_side
        label_box = (
            _scale_x(label_left, width),
            _scale_y(label_y, height),
            _scale_x(label_right, width),
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

        name_stroke_width = max(
            2,
            _scale_x(TYPE_4_TEXT_STROKE_WIDTH, width),
        )
        name_font = self._fit_single_line_text(
            name,
            draw,
            max_width=width - _scale_x(name_x + 40, width),
            base_size=_scale_y(name_size, height),
            min_size=_scale_y(32, height),
            bold=False,
            stroke_width=name_stroke_width,
        )
        draw.text(
            (_scale_x(name_x, width), _scale_y(name_y, height)),
            name,
            font=name_font,
            fill=(255, 255, 255),
            stroke_width=name_stroke_width,
            stroke_fill=(0, 0, 0),
        )
        # Keep the tool names regular like the reference. A configurable inner
        # stroke remains available, but zero deliberately avoids faux bold.
        if TYPE_4_TOOL_NAME_INNER_STROKE_WIDTH > 0:
            base_x = _scale_x(name_x, width)
            base_y = _scale_y(name_y, height)
            draw.text(
                (base_x, base_y),
                name,
                font=name_font,
                fill=(255, 255, 255),
                stroke_width=max(
                    1,
                    _scale_x(TYPE_4_TOOL_NAME_INNER_STROKE_WIDTH, width),
                ),
                stroke_fill=(255, 255, 255),
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
        *,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
    ) -> None:
        if not slide.text:
            return

        cache_key = self._slide_overlay_cache_key(slide, video_type, image.size)
        cached = self._text_overlay_cache.get(cache_key)
        if cached is not None:
            image.alpha_composite(cached)
            return

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))

        if slide.role == SlideRole.HOOK:
            if video_type == VideoType.TYPE_3:
                return
            self._draw_hook_text(
                overlay,
                slide.text,
                video_type=video_type,
                slide=slide,
                layout_image=image,
                avoid_regions=avoid_regions,
            )
        elif self._uses_hook_paragraph_style(slide, video_type):
            self._draw_hook_paragraph_text(
                overlay,
                slide.text,
                slide=slide,
                layout_image=image,
                avoid_regions=avoid_regions,
            )
        else:
            self._draw_caption_card_text(
                overlay,
                slide.text,
                slide=slide,
                layout_image=image,
                avoid_regions=avoid_regions,
            )
        self._remember_text_overlay(cache_key, overlay)
        image.alpha_composite(overlay)

    def _slide_overlay_cache_key(
        self,
        slide: SlidePlan,
        video_type: VideoType,
        image_size: tuple[int, int],
    ) -> tuple[object, ...]:
        try:
            stat = slide.media.local_path.stat()
            file_signature: tuple[object, ...] = (
                str(slide.media.local_path.resolve()),
                stat.st_size,
                stat.st_mtime_ns,
            )
        except OSError:
            file_signature = (str(slide.media.local_path),)
        return (
            *file_signature,
            slide.media.source_id,
            slide.role.value,
            slide.text,
            slide.fixed_asset,
            video_type.value,
            image_size,
        )

    def _remember_text_overlay(
        self,
        cache_key: tuple[object, ...],
        overlay: Image.Image,
    ) -> None:
        self._text_overlay_cache[cache_key] = overlay
        if len(self._text_overlay_cache) > TEXT_OVERLAY_CACHE_MAX_ITEMS:
            oldest_key = next(iter(self._text_overlay_cache))
            self._text_overlay_cache.pop(oldest_key, None)

    def _uses_hook_paragraph_style(
        self,
        slide: SlidePlan,
        video_type: VideoType,
    ) -> bool:
        if video_type not in {VideoType.TYPE_1, VideoType.TYPE_2}:
            return False
        if slide.role not in {SlideRole.TIP1, SlideRole.TIP2, SlideRole.TIP3, SlideRole.TIP4}:
            return False
        text = slide.text.strip()
        return (
            "\n" not in text
            and bool(re.match(r"^\d+\.\s+\S+", text))
        )

    def _slide_expects_person(self, slide: SlidePlan | None) -> bool:
        if slide is None or slide.fixed_asset:
            return False
        if slide.role in TYPE_4_STORY_CAPTION_ROLES:
            return True
        metrics = slide.media.metrics
        if metrics is None:
            return False
        detected_person = bool(
            metrics.faces
            or metrics.face_area_ratio >= 0.004
            or metrics.portrait_focus_score >= 0.18
            or metrics.body_area_ratio >= 0.025
            or metrics.body_focus_score >= 0.16
        )
        likely_missed_portrait = bool(
            metrics.faces == 0
            and metrics.quality_score >= 0.58
            and metrics.daylight >= 0.50
            and metrics.aspect_ratio <= 0.92
            and not metrics.is_landscape
        )
        return detected_person or likely_missed_portrait

    def _fallback_slide_avoid_regions(
        self,
        slide: SlidePlan | None,
        width: int,
        height: int,
    ) -> list[tuple[tuple[int, int, int, int], float]]:
        if slide is not None and slide.role in TYPE_4_STORY_CAPTION_ROLES:
            return [
                (
                    (
                        int(width * 0.08),
                        int(height * 0.46),
                        int(width * 0.92),
                        int(height * 0.94),
                    ),
                    TEXT_FALLBACK_BODY_AVOID_WEIGHT,
                ),
                (
                    (
                        int(width * 0.10),
                        int(height * 0.34),
                        int(width * 0.90),
                        int(height * 0.70),
                    ),
                    TEXT_FALLBACK_HEAD_AVOID_WEIGHT,
                ),
            ]
        return self._fallback_portrait_avoid_regions(width, height)

    def _draw_hook_text(
        self,
        image: Image.Image,
        text: str,
        *,
        video_type: VideoType | None = None,
        slide: SlidePlan | None = None,
        layout_image: Image.Image | None = None,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        layout_source = layout_image or image

        hook_stroke_width = (
            TYPE_2_HOOK_STROKE_WIDTH
            if video_type == VideoType.TYPE_2
            else HOOK_TEXT_STROKE_WIDTH
        )
        stroke_width = max(2, _scale_x(hook_stroke_width, width))
        side_margin = _scale_x(
            TYPE_1_HOOK_SIDE_MARGIN if video_type == VideoType.TYPE_1 else HOOK_SIDE_MARGIN,
            width,
        )
        max_width = width - (side_margin * 2)
        max_height = int(height * 0.40)
        base_size = self._scaled_text_size(HOOK_BASE_FONT_SIZE, minimum=38)
        min_size = self._scaled_text_size(HOOK_MIN_FONT_SIZE, minimum=20)
        font_loader = (
            self._load_type_2_hook_font
            if video_type == VideoType.TYPE_2
            else self._load_overlay_font
        )
        manual_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(manual_lines) > 2 or (
            len(manual_lines) > 1 and video_type != VideoType.TYPE_1
        ):
            lines = manual_lines
            font = self._fit_prebroken_lines(
                lines,
                draw,
                max_width=max_width,
                max_height=max_height,
                base_size=base_size,
                min_size=min_size,
                bold=True,
                stroke_width=stroke_width,
                font_loader=font_loader,
            )
        else:
            fitted_text = " ".join(manual_lines) if manual_lines else text
            font, lines = self._fit_hook_two_lines(
                fitted_text,
                draw,
                max_width=max_width,
                max_height=max_height,
                base_size=base_size,
                min_size=min_size,
                stroke_width=stroke_width,
                font_loader=font_loader,
            )
        if video_type == VideoType.TYPE_2:
            fitted_size = getattr(font, "size", 0)
            normalized_hook = " ".join(text.lower().split())
            font_scale = (
                TYPE_2_COSTLY_MISTAKES_HOOK_FONT_SCALE
                if normalized_hook.startswith(
                    "errores que cuestan dinero al empezar en dropshipping"
                )
                else TYPE_2_HOOK_FONT_SCALE
            )
            reduced_size = max(1, int(round(fitted_size * font_scale)))
            if fitted_size and reduced_size < fitted_size:
                font = font_loader(reduced_size, True)
        text_height = self._block_height(lines, font, draw, stroke_width=stroke_width)
        block_width = min(
            width - _scale_x(80, width),
            self._block_width(lines, font, draw, stroke_width=stroke_width)
            + _scale_x(40, width),
        )
        start_y = self._safe_text_start_y(
            layout_source,
            block_width=block_width,
            block_height=text_height,
            preferred_centers=(0.50, 0.46, 0.54, 0.42, 0.58, 0.38, 0.62),
            expect_person=self._slide_expects_person(slide),
            avoid_regions=avoid_regions,
            fallback_regions=self._fallback_slide_avoid_regions(
                slide,
                width,
                height,
            ),
        )
        self._draw_lines(
            draw,
            lines,
            font,
            start_y=start_y,
            width=width,
            fill=(255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=HOOK_TEXT_STROKE_FILL,
            inner_stroke_width=(
                max(1, _scale_x(TYPE_2_HOOK_INNER_STROKE_WIDTH, width))
                if video_type == VideoType.TYPE_2
                else 0
            ),
        )

    def _draw_hook_paragraph_text(
        self,
        image: Image.Image,
        text: str,
        *,
        slide: SlidePlan | None = None,
        layout_image: Image.Image | None = None,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        layout_source = layout_image or image
        text = self._normalise_hook_paragraph_text(text)
        stroke_width = max(2, _scale_x(HOOK_TEXT_STROKE_WIDTH, width))
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
            font_loader=self._load_overlay_font,
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
            layout_source,
            block_width=block_width,
            block_height=text_height,
            preferred_centers=(
                self._caption_preferred_centers(slide)
                if slide is not None and slide.fixed_asset and slide.role == SlideRole.TIP3
                else (0.50, 0.46, 0.54, 0.42, 0.58, 0.38, 0.62)
            ),
            expect_person=self._slide_expects_person(slide),
            avoid_regions=avoid_regions,
            fallback_regions=self._fallback_slide_avoid_regions(
                slide,
                width,
                height,
            ),
            max_start_y=self._fixed_screen_max_start_y(
                slide,
                text_height,
                canvas_height=height,
            ),
        )
        start_y = self._clamp_fixed_screen_caption_y(
            slide,
            start_y,
            text_height,
            canvas_height=height,
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
            stroke_fill=HOOK_TEXT_STROKE_FILL,
        )

    def _normalise_hook_paragraph_text(self, text: str) -> str:
        text = " ".join(text.strip().split())
        marker = re.match(r"^(\d+\.\s+)", text)
        if marker is None:
            return text
        repeated_at = text.find(marker.group(1), marker.end())
        if repeated_at > 0:
            return text[:repeated_at].strip()
        return text

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
        font_loader: Callable[[int, bool], ImageFont.ImageFont] | None = None,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        load_font = font_loader or (
            lambda font_size, is_bold: self._load_font(size=font_size, bold=is_bold)
        )
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
                font_loader=font_loader,
            )

        for size in range(base_size, min_size - 1, -2):
            font = load_font(size, True)
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

        emergency_min_size = max(18, int(min_size * 0.65))
        for size in range(min_size - 2, emergency_min_size - 1, -2):
            font = load_font(size, True)
            best_lines = None
            best_score = None
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

        for size in range(min_size, emergency_min_size - 1, -2):
            font = load_font(size, True)
            lines = self._wrap_text(
                text,
                font,
                max_width,
                draw,
                stroke_width=stroke_width,
            )
            height = self._block_height(lines, font, draw, stroke_width=stroke_width)
            if height <= max_height:
                return font, lines

        font = load_font(emergency_min_size, True)
        return font, self._wrap_text(
            text,
            font,
            max_width,
            draw,
            stroke_width=stroke_width,
        )

    def _draw_caption_card_text(
        self,
        image: Image.Image,
        text: str,
        *,
        slide: SlidePlan | None = None,
        layout_image: Image.Image | None = None,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
    ) -> None:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        layout_source = layout_image or image
        first_line, body = self._split_slide_text(text)
        edge_margin = _scale_x(TEXT_CARD_EDGE_MARGIN, width)
        padding_x = _scale_x(TEXT_CARD_PADDING_X, width)
        padding_y = _scale_y(TEXT_CARD_PADDING_Y, height)
        title_padding_y = _scale_y(TEXT_CARD_TITLE_PADDING_Y, height)
        connected_line_gap = -_scale_y(TEXT_CARD_LINE_OVERLAP, height)
        block_gap = self._caption_group_gap(slide, height)
        max_text_width = max(1, width - (edge_margin * 2) - (padding_x * 2))

        title_font, title_lines = self._fit_caption_title_text(
            first_line,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.18),
            base_size=self._scaled_text_size(
                TEXT_CARD_TITLE_FONT_SIZE,
                minimum=18,
            ),
            min_size=self._scaled_text_size(
                TEXT_CARD_TITLE_MIN_FONT_SIZE,
                minimum=15,
            ),
            bold=False,
            stroke_width=0,
        )
        body_font, body_lines = self._fit_text(
            body,
            draw,
            max_width=max_text_width,
            max_height=int(height * 0.40),
            base_size=self._scaled_text_size(
                TEXT_CARD_BODY_FONT_SIZE,
                minimum=17,
            ),
            min_size=self._scaled_text_size(
                TEXT_CARD_BODY_MIN_FONT_SIZE,
                minimum=14,
            ),
            bold=False,
            stroke_width=0,
            balanced=True,
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
        title_min_box_width = self._caption_title_min_box_width(slide, width)
        block_width = min(
            width - (edge_margin * 2),
            max(
                self._pill_lines_width(
                    lines,
                    font,
                    draw,
                    padding_x=padding_x,
                    min_box_width=(
                        title_min_box_width if index == 0 and not connected else 0
                    ),
                )
                for index, (lines, font, _line_gap, connected, _group_padding_y)
                in enumerate(groups)
            ),
        )
        start_y = self._safe_text_start_y(
            layout_source,
            block_width=block_width,
            block_height=total_height,
            preferred_centers=self._caption_preferred_centers(slide),
            expect_person=self._slide_expects_person(slide),
            avoid_regions=avoid_regions,
            fallback_regions=self._fallback_slide_avoid_regions(
                slide,
                width,
                height,
            ),
            max_start_y=self._fixed_screen_max_start_y(
                slide,
                total_height,
                canvas_height=height,
            ),
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
                    min_box_width=title_min_box_width if index == 0 else 0,
                )
            if index < len(groups) - 1:
                y += block_gap

    def _caption_preferred_centers(
        self,
        slide: SlidePlan | None,
    ) -> tuple[float, ...]:
        if slide is not None and slide.role in TYPE_4_STORY_CAPTION_ROLES:
            return (
                TYPE_4_STORY_CAPTION_PRIMARY_CENTER,
                0.32,
                0.28,
                0.34,
                0.26,
                0.36,
                0.24,
            )
        if (
            slide is not None and slide.fixed_asset and slide.role == SlideRole.TIP3
        ):
            return (0.42, 0.40, 0.44, 0.38, 0.36)
        if (
            slide is not None and slide.fixed_asset and slide.role == SlideRole.FEBRUARY
        ):
            return (0.38, 0.40, 0.36, 0.42, 0.34, 0.32)
        return (0.50, 0.46, 0.54, 0.42, 0.58, 0.38, 0.62)

    def _clamp_fixed_screen_caption_y(
        self,
        slide: SlidePlan | None,
        start_y: int,
        block_height: int,
        *,
        canvas_height: int,
    ) -> int:
        max_start_y = self._fixed_screen_max_start_y(
            slide,
            block_height,
            canvas_height=canvas_height,
        )
        if max_start_y is None:
            return start_y
        min_y, _max_y = self._safe_text_vertical_bounds(canvas_height, block_height)
        return max(min_y, min(start_y, max_start_y))

    def _fixed_screen_max_start_y(
        self,
        slide: SlidePlan | None,
        block_height: int,
        *,
        canvas_height: int,
    ) -> int | None:
        if slide is None or not slide.fixed_asset:
            return None
        if slide.role == SlideRole.TIP3:
            margin = _scale_y(FIXED_SCREEN_TEXT_MARGIN, canvas_height)
        elif slide.role == SlideRole.FEBRUARY:
            margin = _scale_y(FEBRUARY_FIXED_SCREEN_TEXT_MARGIN, canvas_height)
        else:
            return None
        screen_top = int(canvas_height * 0.525)
        min_y, _max_y = self._safe_text_vertical_bounds(canvas_height, block_height)
        return max(min_y, screen_top - margin - block_height)

    def _scaled_text_size(self, base_size: int, *, minimum: int) -> int:
        return max(minimum, _scale_x(base_size, self.settings.width))

    def _pill_lines_width(
        self,
        lines: list[str],
        font: ImageFont.ImageFont,
        draw: ImageDraw.ImageDraw,
        *,
        padding_x: int,
        min_box_width: int = 0,
    ) -> int:
        if not lines:
            return 0
        return max(
            max(
                min_box_width,
                self._text_size(draw, line, font, stroke_width=0)[0] + padding_x * 2,
            )
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
        min_box_width: int = 0,
    ) -> int:
        y = start_y
        radius = max(6, _scale_x(TEXT_CARD_CORNER_RADIUS, canvas_width))
        for line in lines:
            bbox = draw.textbbox((0, 0), line or "A", font=font, stroke_width=0)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            box_width = max(min_box_width, line_width + padding_x * 2)
            box_height = line_height + padding_y * 2
            x = (canvas_width - box_width) // 2
            box = (x, y, x + box_width, y + box_height)
            draw.rounded_rectangle(box, radius=radius, fill=TEXT_CARD_FILL)
            text_x = x + (box_width - line_width) // 2 - bbox[0]
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

    def _caption_title_min_box_width(
        self,
        slide: SlidePlan | None,
        canvas_width: int,
    ) -> int:
        if (
            slide is not None
            and slide.fixed_asset
            and slide.role == SlideRole.FEBRUARY
        ):
            return min(
                canvas_width - _scale_x(TEXT_CARD_EDGE_MARGIN * 2, canvas_width),
                _scale_x(FEBRUARY_TITLE_MIN_BOX_WIDTH, canvas_width),
            )
        return 0

    def _caption_group_gap(
        self,
        slide: SlidePlan | None,
        canvas_height: int,
    ) -> int:
        if (
            slide is not None
            and slide.fixed_asset
            and slide.role == SlideRole.FEBRUARY
        ):
            return _scale_y(FEBRUARY_TEXT_GROUP_GAP, canvas_height)
        return _scale_y(TEXT_CARD_GROUP_GAP, canvas_height)

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
        radius = max(6, _scale_x(TEXT_CARD_CORNER_RADIUS, canvas_width))
        for box, _text_pos, _line in boxes:
            mask_draw.rounded_rectangle(box, radius=radius, fill=255)

        smooth_radius = max(1, _scale_x(2, canvas_width))
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
        expect_person: bool = False,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
        fallback_regions: list[tuple[tuple[int, int, int, int], float]] | None = None,
        max_start_y: int | None = None,
    ) -> int:
        width, height = image.size
        min_y, max_y = self._safe_text_vertical_bounds(height, block_height)
        if max_start_y is not None:
            max_y = max(min_y, min(max_y, max_start_y))
        regions = (
            self._text_avoid_regions(image)
            if avoid_regions is None
            else list(avoid_regions)
        )
        if not regions and expect_person:
            regions = list(
                fallback_regions
                if fallback_regions is not None
                else self._fallback_portrait_avoid_regions(width, height)
            )
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
        face_safe_candidates = [
            y
            for y in candidates
            if self._text_candidate_clears_priority_regions(
                y,
                block_width=block_width,
                block_height=block_height,
                canvas_width=width,
                canvas_height=height,
                avoid_regions=regions,
            )
        ]
        scored_candidates = face_safe_candidates or candidates
        best_y = min(
            scored_candidates,
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

    def _text_candidate_clears_priority_regions(
        self,
        y: int,
        *,
        block_width: int,
        block_height: int,
        canvas_width: int,
        canvas_height: int,
        avoid_regions: list[tuple[tuple[int, int, int, int], float]],
    ) -> bool:
        x = max(0, (canvas_width - block_width) // 2)
        box = (
            x,
            y,
            min(canvas_width, x + block_width),
            min(canvas_height, y + block_height),
        )
        for region, weight in avoid_regions:
            if weight < TEXT_HEAD_AVOID_WEIGHT:
                continue
            if self._intersection_area(box, region) > 0:
                return False
            if self._avoid_region_clearance_score(
                box,
                region,
                region_weight=weight,
                canvas_height=canvas_height,
            ) > 0:
                return False
        return True

    @staticmethod
    def _safe_text_vertical_bounds(
        canvas_height: int,
        block_height: int,
    ) -> tuple[int, int]:
        top_margin = max(16, _scale_y(SAFE_TEXT_TOP_MARGIN, canvas_height))
        bottom_margin = max(16, _scale_y(SAFE_TEXT_BOTTOM_MARGIN, canvas_height))
        min_y = top_margin
        max_y = max(min_y, canvas_height - block_height - bottom_margin)
        return min_y, max_y

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
        margin = _scale_y(TEXT_AVOID_CLEARANCE_MARGIN, canvas_height)
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
        score = abs(center - preferred_center) * 3.2
        score += abs(center - 0.5) * 0.85
        if preferred_center >= 0.50 and center < 0.42:
            score += (0.42 - center) * 2.8
        score += self._background_clutter_score(luminance, box) * 1.05
        for region, weight in avoid_regions:
            overlap = self._intersection_area(box, region)
            region_area = max(1, self._box_area(region))
            if overlap > 0:
                overlap_ratio = max(overlap / box_area, overlap / region_area)
                score += weight * overlap_ratio
                if weight >= TEXT_HEAD_AVOID_WEIGHT:
                    score += weight * 2.0 * overlap_ratio
                continue
            score += self._avoid_region_clearance_score(
                box,
                region,
                region_weight=weight,
                canvas_height=canvas_height,
            )
        return score

    def _avoid_region_clearance_score(
        self,
        box: tuple[int, int, int, int],
        region: tuple[int, int, int, int],
        *,
        region_weight: float,
        canvas_height: int,
    ) -> float:
        horizontal_overlap = min(box[2], region[2]) - max(box[0], region[0])
        if horizontal_overlap <= 0:
            return 0.0

        if box[3] <= region[1]:
            gap = region[1] - box[3]
        elif region[3] <= box[1]:
            gap = box[1] - region[3]
        else:
            gap = 0
        clearance = _scale_y(TEXT_AVOID_CLEARANCE_MARGIN, canvas_height)
        if gap >= clearance:
            return 0.0

        horizontal_ratio = horizontal_overlap / max(
            1,
            min(box[2] - box[0], region[2] - region[0]),
        )
        closeness = (clearance - gap) / max(1, clearance)
        return (region_weight / 12.0) * horizontal_ratio * closeness

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
            full_rgb = np.asarray(image.convert("RGB"))
            detection_scale = min(
                1.0,
                TEXT_DETECTION_MAX_DIMENSION / max(width, height, 1),
            )
            if detection_scale < 1.0:
                rgb = cv2.resize(
                    full_rgb,
                    (
                        max(1, int(round(width * detection_scale))),
                        max(1, int(round(height * detection_scale))),
                    ),
                    interpolation=cv2.INTER_AREA,
                )
            else:
                rgb = full_rgb
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            gray = cv2.equalizeHist(gray)
        except CV2_ERROR:
            if self._face_avoid_detectors_unavailable():
                return self._fallback_portrait_avoid_regions(width, height)
            return []

        regions: list[tuple[tuple[int, int, int, int], float]] = []
        face_boxes = self._deduplicate_detection_boxes(
            self._detect_render_faces(gray),
            self._detect_render_profile_faces(gray),
        )
        restored_faces = self._restore_detection_boxes(
            face_boxes,
            detection_scale,
        )
        for x, y, w, h in restored_faces:
            face = self._expanded_box(
                (int(x), int(y), int(x + w), int(y + h)),
                width,
                height,
                x_pad=int(w * 0.58),
                y_pad=int(h * 0.88),
            )
            regions.append((face, TEXT_FACE_AVOID_WEIGHT))

        eye_boxes = self._detect_render_eyes(gray)
        restored_eyes = self._restore_detection_boxes(
            eye_boxes,
            detection_scale,
        )
        for x, y, w, h in restored_eyes:
            eye_face = self._expanded_box(
                (
                    int(x - w * 1.4),
                    int(y - h * 1.2),
                    int(x + w * 2.4),
                    int(y + h * 3.6),
                ),
                width,
                height,
                x_pad=int(w * 0.62),
                y_pad=int(h * 0.62),
            )
            regions.append((eye_face, TEXT_EYE_AVOID_WEIGHT))

        people_boxes = self._detect_render_people(rgb)
        restored_people = self._restore_detection_boxes(
            people_boxes,
            detection_scale,
        )
        for x, y, w, h in restored_people:
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
                x_pad=int(w * 0.22),
                y_pad=int(h * 0.16),
            )
            regions.append((body, TEXT_BODY_AVOID_WEIGHT))
            regions.append((head, TEXT_HEAD_AVOID_WEIGHT))
        if not regions and self._face_avoid_detectors_unavailable():
            return self._fallback_portrait_avoid_regions(width, height)
        return regions

    @staticmethod
    def _restore_detection_boxes(
        boxes: np.ndarray,
        detection_scale: float,
    ) -> np.ndarray:
        if len(boxes) == 0:
            return np.empty((0, 4), dtype=np.int32)
        restored = np.asarray(boxes, dtype=np.float32).copy()
        if detection_scale < 1.0:
            restored[:, :4] /= detection_scale
        return np.rint(restored).astype(np.int32)

    @staticmethod
    def _deduplicate_detection_boxes(*groups: np.ndarray) -> np.ndarray:
        boxes = [
            tuple(int(value) for value in box[:4])
            for group in groups
            for box in np.asarray(group).reshape((-1, 4))
            if int(box[2]) > 0 and int(box[3]) > 0
        ]
        boxes.sort(key=lambda box: box[2] * box[3], reverse=True)
        kept: list[tuple[int, int, int, int]] = []
        for candidate in boxes:
            candidate_xyxy = (
                candidate[0],
                candidate[1],
                candidate[0] + candidate[2],
                candidate[1] + candidate[3],
            )
            candidate_area = candidate[2] * candidate[3]
            duplicate = False
            for existing in kept:
                existing_xyxy = (
                    existing[0],
                    existing[1],
                    existing[0] + existing[2],
                    existing[1] + existing[3],
                )
                left = max(candidate_xyxy[0], existing_xyxy[0])
                top = max(candidate_xyxy[1], existing_xyxy[1])
                right = min(candidate_xyxy[2], existing_xyxy[2])
                bottom = min(candidate_xyxy[3], existing_xyxy[3])
                intersection = max(0, right - left) * max(0, bottom - top)
                if intersection <= 0:
                    continue
                existing_area = existing[2] * existing[3]
                union = candidate_area + existing_area - intersection
                iou = intersection / max(1, union)
                containment = intersection / max(
                    1,
                    min(candidate_area, existing_area),
                )
                if iou >= 0.30 or containment >= 0.58:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        if not kept:
            return np.empty((0, 4), dtype=np.int32)
        return np.asarray(kept, dtype=np.int32)

    def _fallback_portrait_avoid_regions(
        self,
        width: int,
        height: int,
    ) -> list[tuple[tuple[int, int, int, int], float]]:
        if width <= 0 or height <= 0:
            return []
        if width / max(height, 1) > 1.05:
            return []

        head = (
            int(width * 0.14),
            int(height * 0.08),
            int(width * 0.86),
            int(height * 0.56),
        )
        body = (
            int(width * 0.10),
            int(height * 0.28),
            int(width * 0.90),
            int(height * 0.88),
        )
        return [
            (body, TEXT_FALLBACK_BODY_AVOID_WEIGHT),
            (head, TEXT_FALLBACK_HEAD_AVOID_WEIGHT),
        ]

    def _face_avoid_detectors_unavailable(self) -> bool:
        return (
            self._detector_empty(self._face_detector)
            and self._detector_empty(self._profile_face_detector)
            and self._detector_empty(self._eye_detector)
        )

    @staticmethod
    def _detector_empty(detector: object) -> bool:
        empty = getattr(detector, "empty", None)
        if callable(empty):
            return bool(empty())
        return False

    def _detect_render_faces(self, gray: np.ndarray) -> np.ndarray:
        if self._face_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        height, width = gray.shape[:2]
        min_size = max(12, _scale_x(42, width))
        detected = self._face_detector.detectMultiScale(
            gray,
            scaleFactor=1.16,
            minNeighbors=4,
            minSize=(min_size, min_size),
        )
        if len(detected) == 0:
            return np.empty((0, 4), dtype=np.int32)
        return np.asarray(detected, dtype=np.int32)

    def _detect_render_profile_faces(self, gray: np.ndarray) -> np.ndarray:
        if self._profile_face_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        height, width = gray.shape[:2]
        min_size = max(12, _scale_x(42, width))

        def detect(source: np.ndarray) -> np.ndarray:
            boxes = self._profile_face_detector.detectMultiScale(
                source,
                scaleFactor=1.16,
                minNeighbors=4,
                minSize=(min_size, min_size),
            )
            if len(boxes) == 0:
                return np.empty((0, 4), dtype=np.int32)
            return np.asarray(boxes, dtype=np.int32)

        direct = detect(gray)
        mirrored = detect(cv2.flip(gray, 1))
        if len(mirrored):
            mirrored = mirrored.copy()
            mirrored[:, 0] = width - mirrored[:, 0] - mirrored[:, 2]
        if len(direct) and len(mirrored):
            return np.vstack((direct, mirrored))
        return direct if len(direct) else mirrored

    def _detect_render_eyes(self, gray: np.ndarray) -> np.ndarray:
        if self._eye_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        height, width = gray.shape[:2]
        min_size = max(8, _scale_x(22, width))
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
        balanced: bool = False,
        font_loader: Callable[[int, bool], ImageFont.ImageFont] | None = None,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        load_font = font_loader or (
            lambda font_size, is_bold: self._load_font(size=font_size, bold=is_bold)
        )
        size = base_size
        while size >= min_size:
            font = load_font(size, bold)
            lines = (
                self._wrap_text_balanced(
                    text,
                    font,
                    max_width,
                    draw,
                    stroke_width=stroke_width,
                )
                if balanced
                else self._wrap_text(
                    text,
                    font,
                    max_width,
                    draw,
                    stroke_width=stroke_width,
                )
            )
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
        font = load_font(min_size, bold)
        lines = (
            self._wrap_text_balanced(
                text,
                font,
                max_width,
                draw,
                stroke_width=stroke_width,
            )
            if balanced
            else self._wrap_text(
                text,
                font,
                max_width,
                draw,
                stroke_width=stroke_width,
            )
        )
        return font, lines

    def _fit_caption_title_text(
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
        if not text.strip():
            return self._fit_text(
                text,
                draw,
                max_width=max_width,
                max_height=max_height,
                base_size=base_size,
                min_size=min_size,
                bold=bold,
                stroke_width=stroke_width,
            )
        for size in range(base_size, min_size - 1, -2):
            font = self._load_font(size=size, bold=bold)
            line_width, line_height = self._text_size(
                draw,
                text,
                font,
                stroke_width=stroke_width,
            )
            if line_width <= max_width and line_height <= max_height:
                return font, [text]
        return self._fit_text(
            text,
            draw,
            max_width=max_width,
            max_height=max_height,
            base_size=base_size,
            min_size=min_size,
            bold=bold,
            stroke_width=stroke_width,
        )

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
        stroke_fill: tuple[int, int, int] = (0, 0, 0),
        inner_stroke_width: int = 0,
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
                stroke_fill=stroke_fill,
            )
            if inner_stroke_width > 0:
                draw.text(
                    (x, y),
                    line,
                    font=font,
                    fill=fill,
                    stroke_width=inner_stroke_width,
                    stroke_fill=fill,
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
            wrapped_lines.extend(
                self._wrap_words_greedy(
                    words,
                    font,
                    max_width,
                    draw,
                    stroke_width=stroke_width,
                )
            )
        return wrapped_lines

    def _wrap_text_balanced(
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
            wrapped_lines.extend(
                self._wrap_words_balanced(
                    words,
                    font,
                    max_width,
                    draw,
                    stroke_width=stroke_width,
                )
            )
        return wrapped_lines

    def _wrap_words_greedy(
        self,
        words: list[str],
        font: ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
        *,
        stroke_width: int,
    ) -> list[str]:
        line = words[0]
        wrapped_lines: list[str] = []
        for word in words[1:]:
            trial = f"{line} {word}"
            if self._text_size(draw, trial, font, stroke_width=stroke_width)[0] <= max_width:
                line = trial
            else:
                wrapped_lines.append(line)
                line = word
        wrapped_lines.append(line)
        return wrapped_lines

    def _wrap_words_balanced(
        self,
        words: list[str],
        font: ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
        *,
        stroke_width: int,
    ) -> list[str]:
        greedy = self._wrap_words_greedy(
            words,
            font,
            max_width,
            draw,
            stroke_width=stroke_width,
        )
        target_lines = len(greedy)
        if target_lines <= 1:
            return greedy

        n_words = len(words)
        full_width = self._text_size(
            draw,
            " ".join(words),
            font,
            stroke_width=stroke_width,
        )[0]
        target_width = min(
            max_width * 0.94,
            max(max_width * 0.58, full_width / target_lines),
        )

        phrase_widths: dict[tuple[int, int], int] = {}
        for start in range(n_words):
            phrase_words: list[str] = []
            for end in range(start + 1, n_words + 1):
                phrase_words.append(words[end - 1])
                phrase = " ".join(phrase_words)
                width = self._text_size(
                    draw,
                    phrase,
                    font,
                    stroke_width=stroke_width,
                )[0]
                if width > max_width and end > start + 1:
                    break
                phrase_widths[(start, end)] = width
                if width > max_width:
                    break

        states: dict[int, tuple[float, list[tuple[int, int]]]] = {0: (0.0, [])}
        for line_index in range(target_lines):
            next_states: dict[int, tuple[float, list[tuple[int, int]]]] = {}
            remaining_lines = target_lines - line_index - 1
            for start, (score, spans) in states.items():
                min_end = start + 1
                max_end = n_words - remaining_lines
                for end in range(min_end, max_end + 1):
                    width = phrase_widths.get((start, end))
                    if width is None:
                        continue
                    if remaining_lines == 0 and end != n_words:
                        continue
                    short_line_penalty = 1.0
                    if width < target_width * 0.58:
                        short_line_penalty = 1.65
                    line_score = ((width - target_width) ** 2) * short_line_penalty
                    candidate = (score + line_score, [*spans, (start, end)])
                    previous = next_states.get(end)
                    if previous is None or candidate[0] < previous[0]:
                        next_states[end] = candidate
            states = next_states
            if not states:
                return greedy

        best = states.get(n_words)
        if best is None:
            return greedy
        return [" ".join(words[start:end]) for start, end in best[1]]

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
        cache_key = ("base", size, bold)
        cached = self._font_cache.get(cache_key)
        if cached is not None:
            return cached
        font = self._load_font_uncached(size=size, bold=bold)
        self._remember_font(cache_key, font)
        return font

    def _load_font_uncached(self, *, size: int, bold: bool) -> ImageFont.ImageFont:
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

    def _load_overlay_font(self, size: int, bold: bool) -> ImageFont.ImageFont:
        cache_key = ("overlay", size, bold)
        cached = self._font_cache.get(cache_key)
        if cached is not None:
            return cached
        font = self._load_overlay_font_uncached(size, bold)
        self._remember_font(cache_key, font)
        return font

    def _load_type_2_hook_font(
        self,
        size: int,
        _bold: bool,
    ) -> ImageFont.ImageFont:
        # Type 2 keeps the same fitting box and maximum size, but uses the
        # regular face so the glyphs have less visual fill than other hooks.
        # The fitter can choose a slightly larger regular font when needed,
        # preserving the occupied width and line distribution.
        return self._load_font(size=size, bold=False)

    def _load_overlay_font_uncached(
        self,
        size: int,
        bold: bool,
    ) -> ImageFont.ImageFont:
        if self._font_dir.exists():
            preferred_tokens = (
                "tiktok",
                "proxima",
                "avenir",
                "gotham",
                "arialrounded",
                "arial rounded",
                "rounded",
            )
            font_files = sorted(self._font_dir.glob("*.ttf"))
            for font_file in font_files:
                name = font_file.name.lower().replace("_", " ").replace("-", " ")
                if any(token in name for token in preferred_tokens):
                    try:
                        return ImageFont.truetype(str(font_file), size=size)
                    except OSError:
                        continue

        for candidate in TIKTOK_OVERLAY_FONT_CANDIDATES:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue

        return self._load_font(size=size, bold=bold)

    def _remember_font(
        self,
        cache_key: tuple[str, int, bool],
        font: ImageFont.ImageFont,
    ) -> None:
        self._font_cache[cache_key] = font
        if len(self._font_cache) > FONT_CACHE_MAX_ITEMS:
            oldest_key = next(iter(self._font_cache))
            self._font_cache.pop(oldest_key, None)

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
                "-preset", self.settings.ffmpeg_preset,
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
