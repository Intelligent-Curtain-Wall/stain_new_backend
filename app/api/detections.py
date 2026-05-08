from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from app.core.auth import get_current_user_id
from app.core.config import settings
from app.core.response import fail, ok
from app.services.model_adapter import InferenceMode, detect_image_sync
from app.services.mysql_repo import MySQLRepository
from app.workers.tasks import process_detection_task, process_detection_task_from_storage

router = APIRouter(prefix="/detections", tags=["detections"])


def _get_repo_or_fail() -> tuple[MySQLRepository | None, dict | None]:
    try:
        return MySQLRepository(), None
    except Exception as error:  # noqa: BLE001
        return None, fail(f"Database configuration error: {error}", 500)


@router.post("")
async def create_detection(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    image: UploadFile = File(...),
    building_name: str = Form(...),
    location_floor: int | None = Form(None),
    location_section: str | None = Form(None),
    description: str | None = Form(None),
    inference_mode: InferenceMode = Form("local")
) -> dict:
    if image.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        return {
            "code": 400,
            "data": None,
            "message": "Only jpg/png image files are supported"
        }

    image_bytes = await image.read()
    if not image_bytes:
        return {
            "code": 400,
            "data": None,
            "message": "Uploaded image is empty"
        }

    repo, error_response = _get_repo_or_fail()
    if error_response:
        return error_response
    assert repo is not None
    try:
        image_path = repo.upload_image(user_id, image_bytes, image.content_type)
        task_id = repo.create_detection(
            user_id=user_id,
            payload={
                "building_name": building_name,
                "location_floor": location_floor,
                "location_section": location_section,
                "description": description,
                "image_name": image.filename
            },
            image_path=image_path,
            file_size=len(image_bytes),
            mime_type=image.content_type
        )

        if len(image_bytes) <= settings.sync_size_threshold_bytes:
            repo.update_detection_processing(task_id)
            model_result = detect_image_sync(image_bytes, image.content_type, inference_mode)
            repo.update_detection_done(task_id, {
                "stain_detected": model_result.stain_detected,
                "stain_type": model_result.stain_type,
                "affected_area_percentage": model_result.affected_area_percentage,
                "summary": model_result.summary,
                "runtime_ms": model_result.runtime_ms,
                "overall_cleanliness": model_result.overall_cleanliness,
                "inference_mode": inference_mode,
                "processed_image_bytes": model_result.processed_image_bytes,
                "processed_image_content_type": model_result.processed_image_content_type,
                "regions": [
                    {
                        "label": item.label,
                        "confidence": item.confidence,
                        "bbox": item.bbox
                    }
                    for item in model_result.regions
                ]
            })
        else:
            background_tasks.add_task(process_detection_task, task_id, image_bytes, image.content_type, inference_mode)

        return ok(repo.get_task_detail(task_id, user_id), "Task created")
    except Exception as error:  # noqa: BLE001
        return fail(f"Create detection failed: {error}", 500)


@router.get("")
def list_detections(
    user_id: str = Depends(get_current_user_id),
    current_page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: str | None = Query(None),
    building_name: str | None = Query(None),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None)
) -> dict:
    repo, error_response = _get_repo_or_fail()
    if error_response:
        return error_response
    assert repo is not None
    try:
        data = repo.list_tasks(user_id, current_page, size, status, building_name, start_time, end_time)
        return ok(data)
    except Exception as error:  # noqa: BLE001
        return fail(f"Query detections failed: {error}", 500)


@router.get("/{task_id}")
def get_detection(task_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    repo, error_response = _get_repo_or_fail()
    if error_response:
        return error_response
    assert repo is not None
    try:
        data = repo.get_task_detail(task_id, user_id)
        return ok(data)
    except Exception as error:  # noqa: BLE001
        return fail(f"Get detection failed: {error}", 500)


@router.post("/{task_id}/retry")
def retry_detection(
    task_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id)
) -> dict:
    repo, error_response = _get_repo_or_fail()
    if error_response:
        return error_response
    assert repo is not None
    try:
        repo.reset_to_pending(task_id, user_id)
        image_path, mime_type = repo.get_task_image_info(task_id, user_id)
        inference_mode = repo.get_task_inference_mode(task_id, user_id)
        background_tasks.add_task(process_detection_task_from_storage, task_id, image_path, mime_type, inference_mode)
        return ok({"id": task_id, "status": "pending"}, "Task requeued")
    except Exception as error:  # noqa: BLE001
        return fail(f"Retry detection failed: {error}", 500)


@router.get("/{task_id}/signed-url")
def get_detection_image_signed_url(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    repo, error_response = _get_repo_or_fail()
    if error_response:
        return error_response
    assert repo is not None
    try:
        image_path, _ = repo.get_task_image_info(task_id, user_id)
        signed_url = repo.create_signed_image_url(image_path)
        return ok({
            "id": task_id,
            "imagePath": image_path,
            "imageSignedUrl": signed_url,
        })
    except Exception as error:  # noqa: BLE001
        return fail(f"Get signed url failed: {error}", 500)
