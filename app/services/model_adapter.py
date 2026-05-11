from __future__ import annotations

import io
import os
import re
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image
from PIL import ImageColor
from PIL import ImageDraw
from PIL import ImageFont
import requests
from ultralytics import YOLO
from ultralytics.utils.plotting import colors

from app.core.config import settings

# 污渍分类名称
CLASS_NAMES = {0: "light", 1: "moderate", 2: "severe"}
# 污渍分类颜色 (十六进制)
CLASS_COLORS = {
    0: colors.hex2rgb("#ADD8E6"),  # 浅蓝
    1: colors.hex2rgb("#00FFFF"),  # 青色
    2: colors.hex2rgb("#0000CD"),  # 深蓝
}


InferenceMode = Literal["local", "cloud"]


@dataclass(frozen=True)
class ModelResultRegion:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ModelResult:
    stain_detected: bool
    stain_type: str | None
    affected_area_percentage: float | None
    summary: str
    runtime_ms: int
    overall_cleanliness: float
    regions: list[ModelResultRegion]
    processed_image_bytes: bytes | None
    processed_image_content_type: str | None


_model: YOLO | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _polygon_area(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(ys) < 3 or len(xs) != len(ys):
        return 0.0
    area = 0.0
    for idx in range(len(xs)):
        jdx = (idx + 1) % len(xs)
        area += xs[idx] * ys[jdx] - xs[jdx] * ys[idx]
    return abs(area) * 0.5


def _to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _normalize_xy(
    x_value: float,
    y_value: float,
    width: int,
    height: int,
    input_is_normalized: bool
) -> tuple[float, float]:
    if input_is_normalized:
        return _clamp01(x_value), _clamp01(y_value)
    safe_width = max(width, 1)
    safe_height = max(height, 1)
    return _clamp01(x_value / safe_width), _clamp01(y_value / safe_height)


def _render_cloud_prediction(
    image: Image.Image,
    raw_results: list[dict],
    input_is_normalized: bool
) -> bytes:
    rendered = image.convert("RGBA")
    draw = ImageDraw.Draw(rendered, "RGBA")
    width = max(image.width, 1)
    height = max(image.height, 1)

    font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 18)
        except OSError:
            font = ImageFont.load_default()

    def get_label_color(label_name: str) -> tuple[int, int, int]:
        """根据标签名称返回对应的RGB颜色"""
        class_id = None
        
        # 尝试从CLASS_NAMES中获取索引
        for cid, name in CLASS_NAMES.items():
            if label_name.lower() == name.lower():
                class_id = cid
                break
        
        # 如果不匹配，尝试从"class0"、"Class 0"这样的格式中提取数字
        if class_id is None:
            match = re.search(r'class\s*(\d+)', label_name.lower())
            if match:
                try:
                    class_id = int(match.group(1))
                except (ValueError, TypeError):
                    pass
        
        # 尝试直接转换为整数
        if class_id is None:
            try:
                class_id = int(label_name)
            except (ValueError, TypeError):
                pass
        
        # 获取对应的颜色，如果找到则返回
        if class_id is not None and class_id in CLASS_COLORS:
            rgb = CLASS_COLORS.get(class_id)
            if rgb is not None:
                return rgb
        
        # 默认颜色（浅蓝）
        return CLASS_COLORS.get(0, (173, 216, 230))

    for row in raw_results:
        label_raw = str(row.get("name") or "stain")
        confidence = float(row.get("confidence") or 0.0)
        
        # 处理标签：将"class0"、"Class 0"转换为CLASS_NAMES中的名称
        label = label_raw
        match = re.search(r'class\s*(\d+)', label_raw.lower())
        if match:
            try:
                class_id = int(match.group(1))
                label = CLASS_NAMES.get(class_id, label_raw)
            except (ValueError, TypeError):
                pass
        else:
            try:
                class_id = int(label_raw)
                label = CLASS_NAMES.get(class_id, label_raw)
            except (ValueError, TypeError):
                pass
        
        rgb = get_label_color(label_raw)
        # RGB元组转为包含透明度的RGBA
        outline = (int(rgb[0]), int(rgb[1]), int(rgb[2]), 255)
        fill = (int(rgb[0]), int(rgb[1]), int(rgb[2]), 72)

        segments = row.get("segments") or {}
        xs = segments.get("x") or []
        ys = segments.get("y") or []
        if isinstance(xs, list) and isinstance(ys, list) and len(xs) == len(ys) and len(xs) >= 3:
            points: list[tuple[float, float]] = []
            for x, y in zip(xs, ys, strict=False):
                try:
                    x_norm, y_norm = _normalize_xy(float(x), float(y), width, height, input_is_normalized)
                    px = x_norm * width
                    py = y_norm * height
                except (TypeError, ValueError):
                    continue
                points.append((px, py))
            if len(points) >= 3:
                draw.polygon(points, fill=fill, outline=outline)

        box = row.get("box") or {}
        try:
            x1_norm, y1_norm = _normalize_xy(float(box.get("x1", 0.0)), float(box.get("y1", 0.0)), width, height, input_is_normalized)
            x2_norm, y2_norm = _normalize_xy(float(box.get("x2", 0.0)), float(box.get("y2", 0.0)), width, height, input_is_normalized)
            x1 = x1_norm * width
            y1 = y1_norm * height
            x2 = x2_norm * width
            y2 = y2_norm * height
        except (TypeError, ValueError):
            continue

        draw.rectangle([(x1, y1), (x2, y2)], outline=outline, width=3)
        tag_text = f"{label} {confidence:.2f}"
        text_x = x1 + 4
        text_y = max(2, y1 - 28)
        text_bbox = draw.textbbox((text_x, text_y), tag_text, font=font)
        draw.rectangle(
            [
                (text_bbox[0] - 3, text_bbox[1] - 2),
                (text_bbox[2] + 3, text_bbox[3] + 2)
            ],
            fill=(0, 0, 0, 180)
        )
        draw.text((text_x, text_y), tag_text, fill=(255, 255, 255, 255), font=font)

    return _to_png_bytes(rendered.convert("RGB"))


def _load_model() -> YOLO:
    global _model
    if _model is not None:
        return _model

    model_path = os.path.abspath(settings.yolo_model_path)
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"YOLO model file not found: {model_path}. "
            "Please place best.pt under backend/models or set YOLO_MODEL_PATH."
        )

    _model = YOLO(model_path)
    
    # 设置模型的类名
    if hasattr(_model, "model") and _model.model is not None:
        _model.model.names = CLASS_NAMES
    if hasattr(_model, "predictor") and _model.predictor is not None and hasattr(_model.predictor, "model"):
        _model.predictor.model.names = CLASS_NAMES
    
    # 设置调色板颜色
    for class_id, rgb in CLASS_COLORS.items():
        colors.palette[class_id] = rgb
    
    return _model


def _detect_local(image_bytes: bytes, content_type: str) -> ModelResult:
    _ = content_type
    started_at = time.perf_counter()

    model = _load_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    prediction = model.predict(
        source=image,
        conf=settings.yolo_confidence_threshold,
        verbose=False
    )[0]

    names_map = prediction.names or {}
    width = max(float(image.width), 1.0)
    height = max(float(image.height), 1.0)

    regions: list[ModelResultRegion] = []
    affected_ratio_sum = 0.0
    best_confidence = -1.0
    best_label: str | None = None

    boxes = prediction.boxes
    if boxes is not None and len(boxes) > 0:
        xyxy_list = boxes.xyxy.cpu().tolist()
        conf_list = boxes.conf.cpu().tolist()
        cls_list = boxes.cls.cpu().tolist()

        for xyxy, confidence, cls_idx in zip(xyxy_list, conf_list, cls_list, strict=False):
            x1_px, y1_px, x2_px, y2_px = [float(value) for value in xyxy]
            x1 = _clamp01(x1_px / width)
            y1 = _clamp01(y1_px / height)
            x2 = _clamp01(x2_px / width)
            y2 = _clamp01(y2_px / height)

            area_ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            affected_ratio_sum += area_ratio

            class_index = int(cls_idx)
            label = str(names_map.get(class_index, f"class_{class_index}"))
            conf_value = float(confidence)

            if conf_value > best_confidence:
                best_confidence = conf_value
                best_label = label

            regions.append(
                ModelResultRegion(
                    label=label,
                    confidence=round(conf_value, 4),
                    bbox=(round(x1, 5), round(y1, 5), round(x2, 5), round(y2, 5))
                )
            )

    mask_ratio = 0.0
    masks = prediction.masks
    if masks is not None and getattr(masks, "data", None) is not None and len(masks.data) > 0:
        union_mask = masks.data.any(dim=0)
        mask_ratio = float(union_mask.float().mean().item())

    stain_detected = len(regions) > 0
    base_ratio = mask_ratio if mask_ratio > 0 else min(affected_ratio_sum, 1.0)
    affected_area = round(base_ratio * 100, 2)
    overall_cleanliness = round(max(0.0, 100 - affected_area), 2)
    runtime_ms = int((time.perf_counter() - started_at) * 1000)

    plotted = prediction.plot()
    processed_image_bytes: bytes | None = None
    if plotted is not None:
        rgb_plot = plotted[..., ::-1] if isinstance(plotted, np.ndarray) and plotted.ndim == 3 else plotted
        plotted_image = Image.fromarray(rgb_plot)
        buffer = io.BytesIO()
        plotted_image.save(buffer, format="PNG")
        processed_image_bytes = buffer.getvalue()

    if stain_detected:
        stain_type = best_label
        summary = f"检测到 {len(regions)} 处疑似污渍，主要类型为 {stain_type}，污渍占比约 {affected_area}% 。"
    else:
        stain_type = None
        summary = "未检测到明显污渍。"

    return ModelResult(
        stain_detected=stain_detected,
        stain_type=stain_type,
        affected_area_percentage=affected_area,
        summary=summary,
        runtime_ms=runtime_ms,
        overall_cleanliness=overall_cleanliness,
        regions=regions,
        processed_image_bytes=processed_image_bytes,
        processed_image_content_type="image/png" if processed_image_bytes else None
    )


def _detect_cloud(image_bytes: bytes, content_type: str) -> ModelResult:
    started_at = time.perf_counter()

    if not settings.cloud_model_url:
        raise RuntimeError("CLOUD_MODEL_URL is not configured")
    if not settings.cloud_model_api_key:
        raise RuntimeError("CLOUD_MODEL_API_KEY is not configured")

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    mime = content_type or "image/jpeg"
    suffix = ".png" if "png" in mime else ".jpg"

    response = requests.post(
        settings.cloud_model_url,
        headers={"Authorization": f"Bearer {settings.cloud_model_api_key}"},
        data={
            "conf": settings.yolo_confidence_threshold,
            "iou": settings.cloud_model_iou_threshold,
            "imgsz": settings.cloud_model_imgsz
        },
        files={
            "file": (f"upload{suffix}", image_bytes, mime)
        },
        timeout=settings.cloud_model_timeout_seconds
    )
    response.raise_for_status()
    payload = response.json()

    image_results = payload.get("images") or []
    first_image = image_results[0] if image_results else {}
    raw_results = first_image.get("results") or []

    shape = first_image.get("shape") or []
    shape_h = 0.0
    shape_w = 0.0
    if isinstance(shape, list) and len(shape) >= 2:
        try:
            shape_h = float(shape[0])
            shape_w = float(shape[1])
        except (TypeError, ValueError):
            shape_h = 0.0
            shape_w = 0.0

    input_is_normalized = True
    for row in raw_results:
        box = row.get("box") or {}
        try:
            values = [float(box.get("x1", 0.0)), float(box.get("y1", 0.0)), float(box.get("x2", 0.0)), float(box.get("y2", 0.0))]
        except (TypeError, ValueError):
            continue
        if any(value > 1.0 for value in values):
            input_is_normalized = False
            break

    regions: list[ModelResultRegion] = []
    affected_ratio_sum = 0.0
    polygon_ratio_sum = 0.0
    best_confidence = -1.0
    best_label: str | None = None

    for row in raw_results:
        label_raw = str(row.get("name") or "stain")
        confidence = float(row.get("confidence") or 0.0)
        
        # 处理标签：将"class0"、"Class 0"转换为CLASS_NAMES中的名称
        label = label_raw
        match = re.search(r'class\s*(\d+)', label_raw.lower())
        if match:
            try:
                class_id = int(match.group(1))
                label = CLASS_NAMES.get(class_id, label_raw)
            except (ValueError, TypeError):
                pass
        else:
            try:
                class_id = int(label_raw)
                label = CLASS_NAMES.get(class_id, label_raw)
            except (ValueError, TypeError):
                pass
        
        box = row.get("box") or {}

        x1_raw = float(box.get("x1") or 0.0)
        y1_raw = float(box.get("y1") or 0.0)
        x2_raw = float(box.get("x2") or 0.0)
        y2_raw = float(box.get("y2") or 0.0)
        if not input_is_normalized and shape_w > 0 and shape_h > 0:
            x1 = _clamp01(x1_raw / shape_w)
            y1 = _clamp01(y1_raw / shape_h)
            x2 = _clamp01(x2_raw / shape_w)
            y2 = _clamp01(y2_raw / shape_h)
        else:
            x1 = _clamp01(x1_raw)
            y1 = _clamp01(y1_raw)
            x2 = _clamp01(x2_raw)
            y2 = _clamp01(y2_raw)

        area_ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        affected_ratio_sum += area_ratio

        segments = row.get("segments") or {}
        xs = segments.get("x") or []
        ys = segments.get("y") or []
        if isinstance(xs, list) and isinstance(ys, list) and len(xs) == len(ys):
            xs_norm = []
            ys_norm = []
            for x, y in zip(xs, ys, strict=False):
                try:
                    x_raw = float(x)
                    y_raw = float(y)
                    if not input_is_normalized and shape_w > 0 and shape_h > 0:
                        xs_norm.append(_clamp01(x_raw / shape_w))
                        ys_norm.append(_clamp01(y_raw / shape_h))
                    else:
                        xs_norm.append(_clamp01(x_raw))
                        ys_norm.append(_clamp01(y_raw))
                except (TypeError, ValueError):
                    continue
            polygon_ratio_sum += _polygon_area(xs_norm, ys_norm)

        if confidence > best_confidence:
            best_confidence = confidence
            best_label = label

        regions.append(
            ModelResultRegion(
                label=label,
                confidence=round(confidence, 4),
                bbox=(round(x1, 5), round(y1, 5), round(x2, 5), round(y2, 5))
            )
        )

    stain_detected = len(regions) > 0
    base_ratio = min(max(polygon_ratio_sum, affected_ratio_sum), 1.0)
    affected_area = round(base_ratio * 100, 2)
    overall_cleanliness = round(max(0.0, 100 - affected_area), 2)
    runtime_ms = int((time.perf_counter() - started_at) * 1000)
    processed_image_bytes = _render_cloud_prediction(image, raw_results, input_is_normalized)

    if stain_detected:
        stain_type = best_label
        summary = f"检测到 {len(regions)} 处疑似污渍，主要类型为 {stain_type}，污渍占比约 {affected_area}% 。"
    else:
        stain_type = None
        summary = "未检测到明显污渍。"

    return ModelResult(
        stain_detected=stain_detected,
        stain_type=stain_type,
        affected_area_percentage=affected_area,
        summary=summary,
        runtime_ms=runtime_ms,
        overall_cleanliness=overall_cleanliness,
        regions=regions,
        processed_image_bytes=processed_image_bytes,
        processed_image_content_type="image/png"
    )


def detect_image_sync(image_bytes: bytes, content_type: str, mode: InferenceMode = "local") -> ModelResult:
    if mode == "cloud":
        return _detect_cloud(image_bytes, content_type)
    return _detect_local(image_bytes, content_type)
