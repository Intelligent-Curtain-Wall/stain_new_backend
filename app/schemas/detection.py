from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DetectionStatus = Literal["pending", "processing", "done", "failed"]


class DetectionRegion(BaseModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: tuple[float, float, float, float]


class DetectionMetrics(BaseModel):
    runtimeMs: int | None = None
    overallCleanliness: float | None = None
    inferenceMode: Literal["local", "cloud"] | None = None


class DetectionTaskItem(BaseModel):
    id: str
    userId: str
    buildingName: str
    locationFloor: int | None = None
    locationSection: str | None = None
    description: str | None = None
    status: DetectionStatus
    createdAt: datetime
    updatedAt: datetime
    imageName: str | None = None
    imagePath: str | None = None
    imageSignedUrl: str | None = None
    processedImagePath: str | None = None
    processedImageSignedUrl: str | None = None
    summary: str | None = None
    stainDetected: bool | None = None
    stainType: str | None = None
    affectedAreaPercentage: float | None = None
    regions: list[DetectionRegion] = []
    metrics: DetectionMetrics | None = None
    errorMessage: str | None = None


class DetectionListData(BaseModel):
    list: list[DetectionTaskItem]
    total: int
