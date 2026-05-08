from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Stone Curtain Wall Stain Detection API")
    app_env: str = os.getenv("APP_ENV", "development")
    cors_origins: tuple[str, ...] = tuple(
        value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:80").split(",") if value.strip()
    )

    # OSS Configuration
    oss_base_url: str = os.getenv("OSS_BASE_URL", "http://8.159.143.133:9000")
    oss_upload_endpoint: str = os.getenv("OSS_UPLOAD_ENDPOINT", "/oss/upload/output")
    oss_username: str = os.getenv("OSS_USERNAME", "stain-detection")
    oss_password: str = os.getenv("OSS_PASSWORD", "tongji-icw-3567")

    # MySQL Database Configuration
    mysql_host: str = os.getenv("MYSQL_HOST", "8.159.143.133")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "stain")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "stain")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "stain")

    # JWT Configuration
    jwt_secret: str = os.getenv("JWT_SECRET", "")

    sync_size_threshold_bytes: int = int(os.getenv("SYNC_SIZE_THRESHOLD_BYTES", "2097152"))
    yolo_model_path: str = os.getenv("YOLO_MODEL_PATH", "models/best.pt")
    yolo_confidence_threshold: float = float(os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.25"))
    cloud_model_url: str = os.getenv("CLOUD_MODEL_URL", "")
    cloud_model_api_key: str = os.getenv("CLOUD_MODEL_API_KEY", "")
    cloud_model_iou_threshold: float = float(os.getenv("CLOUD_MODEL_IOU_THRESHOLD", "0.7"))
    cloud_model_imgsz: int = int(os.getenv("CLOUD_MODEL_IMGSZ", "640"))
    cloud_model_timeout_seconds: int = int(os.getenv("CLOUD_MODEL_TIMEOUT_SECONDS", "60"))


settings = Settings()
