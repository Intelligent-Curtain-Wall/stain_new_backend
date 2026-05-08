# Backend (FastAPI)

该目录提供石材幕墙污渍检测后端骨架，负责：

- 接收前端上传图片并创建检测任务
- 调用模型适配器执行检测（同步/异步混合模式）
- 将任务、图片元数据、检测结果写入 MySQL

## Quick Start

```bash
cd backend
start.bat
```

## Docker 部署

### 1. 准备环境变量

复制 [.env.example](.env.example) 为 `.env`，然后把里面的 MySQL、OSS、JWT 和模型相关配置改成你自己的值。

### 2. 构建镜像

```bash
docker build -t stain-backend:latest .
```

### 3. 启动容器

```bash
docker run -d --name stain-backend \
	--env-file .env \
	-p 8081:8081 \
	--restart unless-stopped \
	stain-backend:latest
```

### 4. 验证服务

浏览器访问：

```text
http://localhost:8081/api/health
```

### 5. 生产部署建议

- 如果要连接外部 MySQL，确保容器能访问数据库地址和端口。
- 如果 `models/best.pt` 不是默认路径，可以在 `.env` 里设置 `YOLO_MODEL_PATH`。
- 如果前端和后端分开部署，请把 `CORS_ORIGINS` 改成前端实际域名。
- 建议在服务器上配一个反向代理，例如 Nginx 或 Caddy，再把 80/443 转发到容器的 8081 端口。

## API

- `GET /api/health`
- `POST /api/detections`
- `GET /api/detections`
- `GET /api/detections/{id}`
- `POST /api/detections/{id}/retry`

`POST /api/detections` 支持额外表单字段：

- `inference_mode`: `local`(默认) 或 `cloud`

## Notes

- YOLO 模型默认读取 `models/best.pt`。你可以直接将模型文件放到该路径。
- 若模型路径不同，设置环境变量 `YOLO_MODEL_PATH` 指向实际位置。
- 当前 `app/services/model_adapter.py` 已接入 `ultralytics` 推理。
- 云端模型可通过 `.env` 配置：`CLOUD_MODEL_URL`、`CLOUD_MODEL_API_KEY`。
- 请先执行 `sql/final_detection_schema.sql` 初始化 MySQL 表结构。
