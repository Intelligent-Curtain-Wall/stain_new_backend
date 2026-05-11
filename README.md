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

##  systemd 部署

### systemd 配置

```bash
sudo nano /etc/systemd/system/stain-backend.service
```

写入以下内容：

```ini
[Unit]
Description=Stain Detection FastAPI Backend
After=network.target

[Service]
Type=simple
User=ecs-user
WorkingDirectory=/home/ecs-user/stain_new_backend
Environment="PATH=/home/ecs-user/anaconda3/envs/stain_backend/bin:/home/ecs-user/anaconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ecs-user/anaconda3/envs/stain_backend/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 操作步骤

```bash
# 1. 创建服务文件
sudo nano /etc/systemd/system/stain-backend.service

# 2. 粘贴上面的配置，保存退出

# 3. 重新加载 systemd
sudo systemctl daemon-reload

# 4. 启动服务
sudo systemctl start stain-backend.service

# 5. 设置开机自启
sudo systemctl enable stain-backend.service

# 6. 查看状态
sudo systemctl status stain-backend.service

# 7. 查看日志（如果有问题）
sudo journalctl -u stain-backend -f
```

### 验证服务

```bash
# 查看服务状态
sudo systemctl status stain-backend

# 测试 API
curl http://localhost:8081/api/health

# 查看实时日志
sudo journalctl -u stain-backend -f
```

### 常用管理命令

```bash
# 重启服务
sudo systemctl restart stain-backend.service

# 停止服务
sudo systemctl stop stain-backend.service

# 查看日志（最近50行）
sudo journalctl -u stain-backend -n 50

# 查看实时日志
sudo journalctl -u stain-backend -f

# 禁用开机自启（如果需要）
sudo systemctl disable stain-backend.service
```

## 生产部署建议

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
