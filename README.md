# Backend (FastAPI)

该目录提供石材幕墙污渍检测后端骨架，负责：

- 接收前端上传图片并创建检测任务
- 调用模型适配器执行检测（同步/异步混合模式）
- 将任务、图片元数据、检测结果写入 MySQL

---

## 目录结构

```
stain_new_backend/
├── app/                    # 应用代码
│   ├── api/                # API 路由
│   ├── core/               # 配置、认证等核心模块
│   ├── schemas/            # 数据模型
│   ├── services/           # 业务逻辑（模型推理、数据库操作）
│   ├── workers/            # 后台任务
│   └── main.py             # 应用入口
├── models/                 # YOLO 模型文件（需自行放入 best.pt）
├── sql/                    # 数据库建表脚本
├── .env                    # 环境变量配置
├── .env.example            # 环境变量模板
├── .dockerignore           # Docker 构建排除规则
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 编排文件
├── DEPLOY.md               # Docker 部署详细指南
├── requirements.txt        # Python 依赖
└── start.bat               # 本地开发启动脚本
```

---

## Docker 部署（推荐）

### 前置条件

- Docker Engine >= 24.0
- Docker Compose >= 2.20
- 服务器内存 >= 4GB（推荐 8GB）

### 快速部署

```bash
# 1. 放入 YOLO 模型文件
cp /path/to/best.pt models/

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 MySQL、OSS、JWT 等实际配置

# 3. 初始化数据库
mysql -h your-mysql-host -u stain -p stain < sql/final_detection_schema.sql

# 4. 构建并启动
docker compose up -d --build

# 5. 验证服务
curl http://localhost:8081/api/health
```

### 常用命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f

# 重启
docker compose restart

# 停止
docker compose stop

# 更新代码后重新构建
docker compose up -d --build
```

> 详细部署说明请参考 [DEPLOY.md](./DEPLOY.md)。

---

## 本地开发

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器（热重载）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload

# 或直接运行脚本
start.bat
```

---

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MYSQL_HOST` | MySQL 地址 | `8.159.143.133` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户名 | `stain` |
| `MYSQL_PASSWORD` | MySQL 密码 | `stain` |
| `MYSQL_DATABASE` | MySQL 数据库名 | `stain` |
| `OSS_BASE_URL` | OSS 对象存储地址 | `http://8.159.143.133:9000` |
| `OSS_USERNAME` | OSS 用户名 | `stain-detection` |
| `OSS_PASSWORD` | OSS 密码 | - |
| `JWT_SECRET` | JWT 签名密钥 | - |
| `CORS_ORIGINS` | 允许跨域的前端地址 | `http://localhost:80` |
| `SYNC_SIZE_THRESHOLD_BYTES` | 同步/异步处理阈值（字节） | `2097152` (2MB) |
| `YOLO_MODEL_PATH` | YOLO 模型路径 | `models/best.pt` |
| `YOLO_CONFIDENCE_THRESHOLD` | 检测置信度阈值 | `0.25` |
| `CLOUD_MODEL_URL` | 云端模型 API 地址 | - |
| `CLOUD_MODEL_API_KEY` | 云端模型 API 密钥 | - |
| `CLOUD_MODEL_TIMEOUT_SECONDS` | 云端模型超时时间 | `60` |

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/detections` | 创建检测任务 |
| `GET` | `/api/detections` | 获取检测任务列表 |
| `GET` | `/api/detections/{id}` | 获取检测任务详情 |
| `POST` | `/api/detections/{id}/retry` | 重试失败的检测任务 |

`POST /api/detections` 支持额外表单字段：

- `inference_mode`: `local`（默认，本地 YOLO 推理）或 `cloud`（云端模型推理）

---

## 注意事项

- YOLO 模型文件 `models/best.pt` 需自行准备，未包含在代码仓库中
- 首次部署前请先执行 `sql/final_detection_schema.sql` 初始化 MySQL 表结构
- 如果前端和后端分开部署，请将 `CORS_ORIGINS` 改为前端实际域名
- 生产环境建议在 Nginx 中配置 `proxy_read_timeout 300s;` 避免大图处理超时（详见 [DEPLOY.md](./DEPLOY.md)）