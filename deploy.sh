#!/bin/bash
# ============================================================
# 放射学研究方案生成系统 — 一键部署脚本（A6000 服务器）
# 使用方法：在服务器上运行 bash deploy.sh
# ============================================================

echo "=========================================="
echo "  放射学研究方案生成系统 — 开始部署"
echo "=========================================="

# ── 配置变量 ──
PROJECT_DIR="/home/user01/radiology_research_system"
VENV_NAME="yybvenv"
PORT=8013

# ── 1. 创建项目目录 ──
echo "[1/8] 创建项目目录: $PROJECT_DIR"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# ── 2. 创建 Python 虚拟环境 yybvenv ──
echo "[2/8] 创建 Python 虚拟环境: $VENV_NAME"
python3 -m venv $VENV_NAME
source $VENV_NAME/bin/activate

# ── 3. 升级 pip ──
echo "[3/8] 升级 pip..."
pip install --upgrade pip -q

# ── 4. 安装依赖 ──
echo "[4/8] 安装 Python 依赖（可能需要几分钟）..."
pip install -r backend/requirements.txt -q

# ── 5. 创建 .env 配置文件 ──
echo "[5/8] 创建环境配置文件..."
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

# ── GPT-5.4 Mini API (通过 api.ssopen.top 代理) ──
OPENAI_API_KEY=sk-NwhxnJ3wqdu4cnYOk41PeHG1ocYpDolzRGmuUg2EsmoiH6Iq
OPENAI_BASE_URL=https://api.ssopen.top/v1
OPENAI_MODEL=gpt-5.4-mini

# ── LongCat / Anthropic API (备用) ──
ANTHROPIC_API_KEY=ak_2kn44a41p3s58Bp8fi0D18KD9kn4d
ANTHROPIC_BASE_URL=https://api.longcat.chat/anthropic
ANTHROPIC_MODEL=LongCat-2.0

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
FRONTEND_URL=http://localhost:3024
ENVEOF

# ── 6. 初始化数据库 ──
echo "[6/8] 初始化数据库..."
cd backend
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('数据库初始化完成！')
"
cd ..

# ── 7. 创建 Gunicorn 启动脚本 ──
echo "[7/8] 创建 Gunicorn 启动脚本..."
cat > start_$PORT.sh << STARTEOF
#!/bin/bash
cd $PROJECT_DIR/backend
source $PROJECT_DIR/$VENV_NAME/bin/activate
echo "启动放射学研究方案系统... 端口: $PORT"
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT --timeout 600 --access-logfile ../access.log --error-logfile ../error.log app:app
STARTEOF
chmod +x start_$PORT.sh

# ── 8. 启动服务 ──
echo "[8/8] 启动服务..."
./start_$PORT.sh &

echo "=========================================="
echo "  部署完成！"
echo "  访问地址: http://3.tcp.vip.cpolor.cn:$PORT"
echo "  项目目录: $PROJECT_DIR"
echo "  虚拟环境: $VENV_NAME"
echo "  启动脚本: start_$PORT.sh"
echo ""
echo "  常用命令："
echo "    查看日志: tail -f $PROJECT_DIR/backend.log"
echo "    停止服务: pkill -f 'gunicorn.*$PORT'"
echo "    重启服务: bash start_$PORT.sh &"
echo "=========================================="
