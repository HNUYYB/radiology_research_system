#!/bin/bash
# ============================================================
# 放射学研究方案生成系统 — 一键部署脚本
# 在服务器上运行此脚本
# ============================================================

echo "=========================================="
echo "  放射学研究方案生成系统 — 开始部署"
echo "=========================================="

# ── 1. 创建项目目录 ──
PROJECT_DIR="/home/user01/radiology_research_system"
echo "[1/7] 创建项目目录: $PROJECT_DIR"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# ── 2. 创建 Python 虚拟环境 ──
echo "[2/7] 创建 Python 虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# ── 3. 安装依赖 ──
echo "[3/7] 安装 Python 依赖..."
pip install --upgrade pip
pip install flask==2.3.3 \
            flask-cors==4.0.0 \
            flask-sqlalchemy==3.0.5 \
            anthropic==0.8.0 \
            requests==2.31.0 \
            python-dotenv==1.0.0 \
            pandas==2.1.1 \
            openpyxl==3.1.2 \
            reportlab==4.0.4 \
            python-docx==1.1.0 \
            flask-socketio==5.6.1 \
            python-socketio==5.12.0 \
            python-engineio==4.13.1 \
            biopython==1.83 \
            gunicorn==21.2.0 \
            eventlet==0.35.1

# ── 4. 创建 .env 配置文件 ──
echo "[4/7] 创建环境配置文件..."
cat > backend/.env << 'ENVEOF'
# ============================================================
# 放射学研究方案生成系统 — 环境变量配置
# ============================================================

# ── 安全密钥 ──
SECRET_KEY=my-flask-secret-key-2024-production
JWT_SECRET_KEY=my-jwt-secret-key-2024-production
JWT_ACCESS_TOKEN_EXPIRES=86400

# ── LLM 模型提供商选择 ──
LLM_PROVIDER=gpt54

# ── LongCat / Anthropic API (默认) ──
ANTHROPIC_API_KEY=ak_2kn44a41p3s58Bp8fi0D18KD9kn4d
ANTHROPIC_BASE_URL=https://api.longcat.chat/anthropic
ANTHROPIC_MODEL=LongCat-2.0-Preview

# ── GPT-5.4 Mini API (通过 api.ssopen.top 代理) ──
OPENAI_API_KEY=sk-NwhxnJ3wqdu4cnYOk41PeHG1ocYpDolzRGmuUg2EsmoiH6Iq
OPENAI_BASE_URL=https://api.ssopen.top/v1
OPENAI_MODEL=gpt-5.4-mini

# ── DeepSeek API (可选) ──
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ── PubMed API ──
PUBMED_API_KEY=1307550aa4966b0cbbc68a6b2d4cb1ff8009
PUBMED_EMAIL=79047879@qq.com

# ── 应用配置 ──
FLASK_DEBUG=False
PORT=8013
LOG_LEVEL=INFO
ENVEOF

# ── 5. 初始化数据库 ──
echo "[5/7] 初始化数据库..."
cd backend
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('数据库初始化完成！')
"
cd ..

# ── 6. 创建 Gunicorn 启动脚本 ──
echo "[6/7] 创建 Gunicorn 启动脚本..."
cat > start.sh << 'STARTEOF'
#!/bin/bash
cd /home/user01/radiology_research_system/backend
source /home/user01/radiology_research_system/venv/bin/activate
echo "启动放射学研究方案系统... 端口: 8013"
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:8013 --timeout 600 --access-logfile ../access.log --error-logfile ../error.log app:app
STARTEOF
chmod +x start.sh

# ── 7. 启动服务 ──
echo "[7/7] 启动服务..."
./start.sh &

echo "=========================================="
echo "  部署完成！"
echo "  访问地址: http://3.tcp.vip.cpolor.cn:8013"
echo "=========================================="
