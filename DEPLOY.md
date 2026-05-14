# Docker 部署指南

## 环境要求

- Docker Engine >= 24.0
- Docker Compose >= 2.20
- 服务器内存 >= 4GB（推荐 8GB，YOLO 模型推理需要）

---

## 目录结构

```
stain_new_backend/
├── app/                    # 应用代码
├── models/                 # YOLO 模型文件（需自行放入 best.pt）
│   └── best.pt
├── .env                    # 环境变量配置（需自行修改）
├── .env.example            # 环境变量模板
├── .dockerignore           # Docker 构建排除规则
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 编排文件
├── requirements.txt        # Python 依赖
└── sql/                    # 数据库建表脚本
```

---

## 第一步：准备模型文件

YOLO 模型文件 `best.pt` 未包含在代码仓库中，需要手动放入：

```bash
# 在 stain_new_backend/ 目录下创建 models 文件夹（已存在则跳过）
mkdir -p models

# 将 best.pt 放入 models/ 目录
# 例如通过 scp 从本地复制到服务器：
scp best.pt user@your-server:/path/to/stain_new_backend/models/
```

最终目录结构应为：

```
stain_new_backend/models/best.pt
```

---

## 第二步：配置环境变量

复制环境变量模板并修改：

```bash
cd stain_new_backend
cp .env.example .env
```

编辑 `.env` 文件，根据实际环境修改以下配置：

### 必填项

```ini
# MySQL 数据库配置（必填）
MYSQL_HOST=你的MySQL服务器地址
MYSQL_PORT=3306
MYSQL_USER=stain
MYSQL_PASSWORD=你的数据库密码
MYSQL_DATABASE=stain

# OSS 对象存储配置（必填）
OSS_BASE_URL=http://你的OSS服务地址:9000
OSS_UPLOAD_ENDPOINT=/oss/upload/output
OSS_USERNAME=stain-detection
OSS_PASSWORD=你的OSS密码

# JWT 密钥（必填，用于 token 验证）
JWT_SECRET=你的JWT密钥

# CORS 允许的前端地址（必填）
CORS_ORIGINS=http://你的前端地址
```

### 选填项（有默认值）

```ini
# 应用名称
APP_NAME=Stone Curtain Wall Stain Detection API

# 运行环境：development / production
APP_ENV=production

# 同步/异步处理阈值（字节），默认 2MB
# 小于此值的图片同步处理（等待结果），大于此值的异步处理（后台处理）
SYNC_SIZE_THRESHOLD_BYTES=2097152

# YOLO 模型路径（容器内路径）
YOLO_MODEL_PATH=models/best.pt

# YOLO 检测置信度阈值
YOLO_CONFIDENCE_THRESHOLD=0.25

# 云端模型 API（如使用远程模型推理）
CLOUD_MODEL_URL=
CLOUD_MODEL_API_KEY=
CLOUD_MODEL_IOU_THRESHOLD=0.7
CLOUD_MODEL_IMGSZ=640
CLOUD_MODEL_TIMEOUT_SECONDS=60
```

---

## 第三步：初始化数据库

在 MySQL 中执行建表脚本：

```bash
# 方式一：直接导入
mysql -h 你的MySQL地址 -u stain -p stain < sql/final_detection_schema.sql

# 方式二：在 MySQL 客户端中执行
mysql> source /path/to/stain_new_backend/sql/final_detection_schema.sql;
```

---

## 第四步：构建并启动

### 首次启动

```bash
cd stain_new_backend

# 构建镜像并后台启动
docker compose up -d --build

# 查看启动日志
docker compose logs -f
```

### 查看运行状态

```bash
# 查看容器状态
docker compose ps

# 查看实时日志
docker compose logs -f

# 查看最近 50 行日志
docker compose logs --tail=50
```

### 验证服务

```bash
# 测试健康检查接口
curl http://localhost:8081/api/health

# 预期返回：
# {"code": 0, "message": "ok", "data": {"status": "healthy"}}
```

---

## 日常管理命令

### 启动 / 停止 / 重启

```bash
# 启动服务
docker compose start

# 停止服务
docker compose stop

# 重启服务
docker compose restart

# 停止并删除容器（保留镜像和数据）
docker compose down
```

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动（仅更改了代码时）
docker compose up -d --build

# 如果只改了 .env 配置，不需要重建，直接重启即可
docker compose restart
```

### 查看容器内部

```bash
# 进入容器内部（调试用）
docker compose exec backend bash

# 查看容器资源占用
docker stats stain-backend
```

### 清理

```bash
# 停止并删除容器、网络（保留镜像）
docker compose down

# 完全清理（包括镜像）
docker compose down --rmi all

# 清理未使用的 Docker 资源
docker system prune
```

---

## Nginx 反向代理配置

如果后端前面有 Nginx 做反向代理，需要增加超时时间，避免处理大图时 504：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /detection-api/ {
        proxy_pass http://127.0.0.1:8081/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置（关键：防止 504）
        proxy_connect_timeout 30s;
        proxy_read_timeout 300s;     # 等待后端响应的超时时间
        proxy_send_timeout 300s;
    }
}
```

配置完成后重载 Nginx：

```bash
nginx -t          # 测试配置是否正确
nginx -s reload   # 重载配置
```

---

## 常见问题

### 1. 容器启动后马上退出

```bash
# 查看日志找出原因
docker compose logs
```

常见原因：
- `.env` 文件未正确配置（MySQL 连接失败、OSS 配置错误）
- `models/best.pt` 不存在或路径错误
- 端口 8081 被占用

### 2. 数据库连接失败

```bash
# 检查 MySQL 是否允许远程连接
# 检查 .env 中的 MYSQL_HOST、MYSQL_PORT 是否正确
# 检查防火墙是否放行 3306 端口
```

### 3. 上传图片返回 504

Nginx 默认 `proxy_read_timeout` 为 60 秒，YOLO 模型处理大图可能超时。

解决方法：
- 在 Nginx 配置中增加 `proxy_read_timeout 300s;`（见上方 Nginx 配置）
- 或降低 `SYNC_SIZE_THRESHOLD_BYTES` 让大图走异步处理

### 4. 模型推理报错

```bash
# 检查 models/best.pt 文件是否完整
# 检查容器内模型路径：
docker compose exec backend ls -la /app/models/
```

### 5. 端口冲突

如果 8081 端口已被占用，修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "8082:8081"   # 将宿主机的 8082 映射到容器的 8081
```

---

## 完整部署流程（速查）

```bash
# 1. 进入项目目录
cd /path/to/stain_new_backend

# 2. 放入模型文件
cp /path/to/best.pt models/

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际配置

# 4. 初始化数据库
mysql -h your-mysql-host -u stain -p stain < sql/final_detection_schema.sql

# 5. 构建并启动
docker compose up -d --build

# 6. 验证
curl http://localhost:8081/api/health

# 7. 查看日志
docker compose logs -f
```