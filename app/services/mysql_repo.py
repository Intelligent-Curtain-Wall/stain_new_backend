from __future__ import annotations

from datetime import datetime
from typing import Literal, Any
import uuid
import requests
import os
from urllib.parse import quote
import time
import json

import pymysql
from fastapi import HTTPException

from app.core.config import settings


InferenceMode = Literal["local", "cloud"]


class MySQLRepository:
    """Repository for managing OSS image storage and MySQL metadata."""

    def __init__(self) -> None:
        if not settings.mysql_host or not settings.mysql_user or not settings.mysql_database:
            raise RuntimeError("MySQL configuration is missing")
        if not settings.oss_base_url:
            raise RuntimeError("OSS configuration is missing")

    def _connect(self):
        return pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _execute(self, sql: str, params: tuple[Any, ...] = (), fetch: str | None = None):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                if fetch == "one":
                    result = cursor.fetchone()
                elif fetch == "all":
                    result = cursor.fetchall()
                else:
                    result = None
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sanitize_filename(self, filename: str) -> str:
        import re
        filename = os.path.basename(filename)
        filename = filename.replace("_", "-")
        return re.sub(r"[^A-Za-z0-9-.]", "-", filename)

    def create_signed_image_url(self, path: str, expires_in: int | None = None) -> str | None:
        if not path:
            return None
        stored_path = path.lstrip("/")
        return f"{settings.oss_base_url}/oss/download/stain-detection/{stored_path}"

    def _upload_to_oss(self, local_path: str, target_filename: str, retries: int = 3, delay: int = 2) -> str:
        if not os.path.exists(local_path):
            raise RuntimeError(f"Local file does not exist: {local_path}")

        sanitized_filename = self._sanitize_filename(target_filename)
        encoded_filename = quote(sanitized_filename)
        url = f"{settings.oss_base_url}{settings.oss_upload_endpoint}/{encoded_filename}"
        stored_path = f"output/{sanitized_filename}"

        for attempt in range(retries):
            try:
                with open(local_path, "rb") as file_handle:
                    files = {"file": ("file", file_handle, "image/jpeg")}
                    data = {"userName": settings.oss_username, "password": settings.oss_password}
                    response = requests.post(url, files=files, data=data, timeout=600)

                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        if response_data.get("code") == 200:
                            return stored_path
                    except Exception:
                        pass

                    if response.text.strip().startswith("http"):
                        return stored_path

                    raise RuntimeError(f"Unexpected response format: {response.text.strip()}")

                if attempt < retries - 1:
                    time.sleep(delay)
            except Exception as error:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to upload to OSS after {retries} attempts: {error}")

        raise RuntimeError("Failed to upload to OSS: no retries left")

    def upload_image(self, user_id: str, image_bytes: bytes, content_type: str) -> str:
        import tempfile

        suffix = ".jpg" if content_type.endswith("jpeg") else ".png"
        now = datetime.now()
        ym = f"{now.year:04d}{now.month:02d}"
        filename = f"u-{user_id}-o-{ym}-{uuid.uuid4().hex[:16]}{suffix}"

        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        try:
            with open(temp_path, "wb") as file_handle:
                file_handle.write(image_bytes)
            return self._upload_to_oss(temp_path, filename)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def upload_processed_image(self, user_id: str, task_id: str, image_bytes: bytes, content_type: str) -> str:
        import tempfile

        suffix = ".png" if content_type.endswith("png") else ".jpg"
        now = datetime.now()
        ym = f"{now.year:04d}{now.month:02d}"
        filename = f"u-{user_id}-p-{ym}-{task_id}-{uuid.uuid4().hex[:10]}{suffix}"

        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        try:
            with open(temp_path, "wb") as file_handle:
                file_handle.write(image_bytes)
            return self._upload_to_oss(temp_path, filename)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def create_detection(self, user_id: str, payload: dict, image_path: str, file_size: int, mime_type: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into inspection_tasks (
                        user_id, building_name, location_floor, location_section, description,
                        status, created_at, updated_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        payload["building_name"],
                        payload.get("location_floor"),
                        payload.get("location_section"),
                        payload.get("description"),
                        "pending",
                        now,
                        now,
                    ),
                )
                task_id = str(cursor.lastrowid)

                cursor.execute(
                    """
                    insert into task_images (
                        task_id, user_id, image_name, original_image_path, mime_type, file_size, created_at
                    ) values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_id,
                        user_id,
                        payload.get("image_name"),
                        image_path,
                        mime_type,
                        file_size,
                        now,
                    ),
                )

                cursor.execute(
                    """
                    insert into detection_results (
                        task_id, user_id, status, created_at, updated_at
                    ) values (%s, %s, %s, %s, %s)
                    """,
                    (task_id, user_id, "pending", now, now),
                )

            connection.commit()
            return task_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_detection_processing(self, task_id: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute(
            "update inspection_tasks set status = %s, updated_at = %s where id = %s",
            ("processing", now, task_id),
        )
        self._execute(
            "update detection_results set status = %s, updated_at = %s where task_id = %s",
            ("processing", now, task_id),
        )

    def update_detection_done(self, task_id: str, result: dict) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        owner = self._execute("select user_id from inspection_tasks where id = %s limit 1", (task_id,), fetch="one")
        if not owner:
            raise HTTPException(status_code=404, detail="Task not found")
        user_id = str(owner["user_id"])

        if result.get("processed_image_bytes") and result.get("processed_image_content_type"):
            processed_image_path = self.upload_processed_image(
                user_id=user_id,
                task_id=task_id,
                image_bytes=result["processed_image_bytes"],
                content_type=result["processed_image_content_type"],
            )
            self._execute(
                """
                update task_images
                set processed_image_path = %s
                where task_id = %s and user_id = %s
                """,
                (processed_image_path, task_id, user_id),
            )

        self._execute(
            """
            update inspection_tasks
            set status = %s, summary = %s, stain_detected = %s, stain_type = %s,
                affected_area_percentage = %s, updated_at = %s
            where id = %s
            """,
            (
                "done",
                result["summary"],
                int(bool(result["stain_detected"])),
                result["stain_type"],
                result["affected_area_percentage"],
                now,
                task_id,
            ),
        )

        metrics = {
            "runtimeMs": result["runtime_ms"],
            "overallCleanliness": result["overall_cleanliness"],
            "inferenceMode": result.get("inference_mode", "local"),
        }
        self._execute(
            """
            update detection_results
            set status = %s, summary = %s, metrics = %s, processed_at = %s, updated_at = %s
            where task_id = %s
            """,
            ("done", result["summary"], json.dumps(metrics), now, now, task_id),
        )

        self._execute("delete from result_regions where task_id = %s", (task_id,))
        if result["regions"]:
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        insert into result_regions (task_id, label, confidence, x1, y1, x2, y2)
                        values (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                task_id,
                                region["label"],
                                region["confidence"],
                                region["bbox"][0],
                                region["bbox"][1],
                                region["bbox"][2],
                                region["bbox"][3],
                            )
                            for region in result["regions"]
                        ],
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def update_detection_failed(self, task_id: str, error_message: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute(
            "update inspection_tasks set status = %s, error_message = %s, updated_at = %s where id = %s",
            ("failed", error_message, now, task_id),
        )
        self._execute(
            "update detection_results set status = %s, error_message = %s, updated_at = %s where task_id = %s",
            ("failed", error_message, now, task_id),
        )

    def _row_to_task_detail(self, task: dict, image_row: dict | None, metrics_row: dict | None, regions_rows: list[dict]) -> dict:
        image_name = image_row.get("image_name") if image_row else None
        image_path = image_row.get("original_image_path") if image_row else None
        processed_image_path = image_row.get("processed_image_path") if image_row else None
        image_signed_url = self.create_signed_image_url(image_path) if image_path else None
        processed_image_signed_url = self.create_signed_image_url(processed_image_path) if processed_image_path else None
        metrics = metrics_row.get("metrics") if metrics_row else None
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = None

        regions = [
            {
                "label": row["label"],
                "confidence": float(row["confidence"]),
                "bbox": [float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])],
            }
            for row in regions_rows
        ]

        return {
            "id": task["id"],
            "userId": task["user_id"],
            "buildingName": task["building_name"],
            "locationFloor": task.get("location_floor"),
            "locationSection": task.get("location_section"),
            "description": task.get("description"),
            "status": task["status"],
            "createdAt": task["created_at"],
            "updatedAt": task["updated_at"],
            "imageName": image_name,
            "imagePath": image_path,
            "imageSignedUrl": image_signed_url,
            "processedImagePath": processed_image_path,
            "processedImageSignedUrl": processed_image_signed_url,
            "summary": task.get("summary"),
            "stainDetected": bool(task.get("stain_detected")) if task.get("stain_detected") is not None else None,
            "stainType": task.get("stain_type"),
            "affectedAreaPercentage": float(task["affected_area_percentage"]) if task.get("affected_area_percentage") is not None else None,
            "regions": regions,
            "metrics": metrics,
            "errorMessage": task.get("error_message"),
        }

    def get_task_detail(self, task_id: str, user_id: str) -> dict:
        task = self._execute(
            "select * from inspection_tasks where id = %s and user_id = %s limit 1",
            (task_id, user_id),
            fetch="one",
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        image_row = self._execute(
            "select image_name, original_image_path, processed_image_path from task_images where task_id = %s and user_id = %s limit 1",
            (task_id, user_id),
            fetch="one",
        )
        metrics_row = self._execute(
            "select metrics from detection_results where task_id = %s and user_id = %s limit 1",
            (task_id, user_id),
            fetch="one",
        )
        regions_rows = self._execute(
            "select label, confidence, x1, y1, x2, y2 from result_regions where task_id = %s order by id asc",
            (task_id,),
            fetch="all",
        ) or []
        return self._row_to_task_detail(task, image_row, metrics_row, regions_rows)

    def get_task_inference_mode(self, task_id: str, user_id: str) -> InferenceMode:
        response = self._execute(
            "select metrics from detection_results where task_id = %s and user_id = %s limit 1",
            (task_id, user_id),
            fetch="one",
        )
        if not response:
            return "local"
        metrics = response.get("metrics") or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        mode = metrics.get("inferenceMode")
        return mode if mode in ("local", "cloud") else "local"

    def get_task_image_info(self, task_id: str, user_id: str) -> tuple[str, str]:
        response = self._execute(
            "select original_image_path, mime_type from task_images where task_id = %s and user_id = %s limit 1",
            (task_id, user_id),
            fetch="one",
        )
        if not response:
            raise HTTPException(status_code=404, detail="Task image not found")
        image_path = response.get("original_image_path")
        mime_type = response.get("mime_type") or "image/jpeg"
        if not image_path:
            raise HTTPException(status_code=404, detail="Task image path is empty")
        return str(image_path), str(mime_type)

    def list_tasks(
        self,
        user_id: str,
        current_page: int,
        size: int,
        status: str | None,
        building_name: str | None,
        start_time: str | None,
        end_time: str | None,
    ) -> dict:
        offset = (current_page - 1) * size
        where_clauses = ["user_id = %s"]
        params: list[Any] = [user_id]

        if status:
            where_clauses.append("status = %s")
            params.append(status)
        if building_name:
            where_clauses.append("building_name like %s")
            params.append(f"%{building_name}%")
        if start_time:
            where_clauses.append("created_at >= %s")
            params.append(start_time)
        if end_time:
            where_clauses.append("created_at <= %s")
            params.append(end_time)

        where_sql = " and ".join(where_clauses)
        total_row = self._execute(
            f"select count(*) as total from inspection_tasks where {where_sql}",
            tuple(params),
            fetch="one",
        ) or {"total": 0}

        rows = self._execute(
            f"""
            select id, user_id, building_name, location_floor, location_section, status,
                   created_at, updated_at, summary, stain_detected, stain_type,
                   affected_area_percentage, error_message
            from inspection_tasks
            where {where_sql}
            order by created_at desc, id desc
            limit %s offset %s
            """,
            tuple(params + [size, offset]),
            fetch="all",
        ) or []

        items: list[dict] = []
        for task in rows:
            image_row = self._execute(
                "select image_name from task_images where task_id = %s and user_id = %s order by id desc limit 1",
                (task["id"], user_id),
                fetch="one",
            )
            metrics_row = self._execute(
                "select metrics from detection_results where task_id = %s and user_id = %s limit 1",
                (task["id"], user_id),
                fetch="one",
            )
            metrics = metrics_row.get("metrics") if metrics_row else None
            if isinstance(metrics, str):
                try:
                    metrics = json.loads(metrics)
                except Exception:
                    metrics = None

            items.append(
                {
                    "id": task["id"],
                    "userId": task["user_id"],
                    "buildingName": task["building_name"],
                    "locationFloor": task.get("location_floor"),
                    "locationSection": task.get("location_section"),
                    "description": None,
                    "status": task["status"],
                    "createdAt": task["created_at"],
                    "updatedAt": task["updated_at"],
                    "imageName": image_row.get("image_name") if image_row else None,
                    "imagePath": None,
                    "imageSignedUrl": None,
                    "processedImagePath": None,
                    "processedImageSignedUrl": None,
                    "summary": task.get("summary"),
                    "stainDetected": bool(task.get("stain_detected")) if task.get("stain_detected") is not None else None,
                    "stainType": task.get("stain_type"),
                    "affectedAreaPercentage": float(task["affected_area_percentage"]) if task.get("affected_area_percentage") is not None else None,
                    "regions": [],
                    "metrics": metrics,
                    "errorMessage": task.get("error_message"),
                }
            )

        return {
            "items": items,
            "pagination": {
                "current_page": current_page,
                "size": size,
                "total": int(total_row["total"]),
            },
        }

    def reset_to_pending(self, task_id: str, user_id: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute(
            "update inspection_tasks set status = %s, error_message = null, updated_at = %s where id = %s and user_id = %s",
            ("pending", now, task_id, user_id),
        )
        self._execute(
            "update detection_results set status = %s, error_message = null, updated_at = %s where task_id = %s and user_id = %s",
            ("pending", now, task_id, user_id),
        )
