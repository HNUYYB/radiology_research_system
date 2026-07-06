# 放射学研究方案智能生成系统

面向放射学领域研究生的智能研究方案生成平台，基于多智能体协同（Multi-Agent Collaboration）技术，将学生的研究想法自动转化为规范、可开题的完整研究方案。

---

## 功能概览

- **多智能体流水线**：7 个专属 Agent 协同工作（输入解析 → 学生画像 → 问题定义 → 文献检索 → 方案生成 → 方案评审 → 方案修订），全程自动化
- **文献检索**：自动检索 PubMed 和 arXiv 相关文献，识别研究空白
- **实时日志流**：通过 WebSocket 实时推送各智能体的运行日志，方便调试和观察进度
- **方案管理**：查看、导出研究方案（支持 Word、LaTeX、PDF、BibTeX 格式）
- **专家盲评**：支持专家对方案进行多维度评分和评论
- **放射学输入校验**：自动校验输入是否包含放射学领域关键词，确保方案聚焦

---

## 技术架构

```
前端 (React 18 + Bootstrap 5)    端口 3024
        │
        │  HTTP REST API + WebSocket
        │
后端 (Flask + Flask-SocketIO)    端口 5002
        │
        ├── SQLite 数据库
        ├── LongCat API (LLM 推理核心)
        ├── PubMed E-Utilities (文献检索)
        └── arXiv API (预印本检索)
```

---

## 环境要求

| 组件 | 版本要求 |
|------|----------|
| Node.js | ≥ 16 |
| Python | ≥ 3.9 |
| npm | ≥ 8 |

---

## 快速启动

### 1. 配置环境变量

根目录已包含 `.env` 文件，其中配置了 API 密钥和默认参数。如需修改，参考 `.env.example`。

关键配置项：

```
ANTHROPIC_API_KEY=your_longcat_api_key
ANTHROPIC_BASE_URL=https://api.longcat.chat/anthropic
ANTHROPIC_MODEL=LongCat-2.0
PUBMED_API_KEY=your_pubmed_api_key
DATABASE_URL=sqlite:///research_system.db
SECRET_KEY=your_secret_key
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端将在 `http://localhost:5002` 启动。

### 3. 启动前端

打开一个新的终端：

```bash
cd frontend
npm install
npm start
```

前端将在 `http://localhost:3024` 启动。

### 4. 访问系统

浏览器打开 **http://localhost:3024** 即可使用。

---

## 使用流程

1. **注册 / 登录**：创建账号或使用已有账号登录
2. **完善画像**：填写年级、专业方向、统计学/AI 基础、研究条件等信息
3. **输入研究想法**：通过三步向导描述你的研究需求
4. **等待生成**：多智能体流水线自动运行（约 5-10 分钟），可实时查看日志
5. **查看方案**：在仪表盘查看生成的完整研究方案（包含 13 个标准字段）
6. **导出方案**：支持导出为 Word、LaTeX、PDF 或 BibTeX 格式

---

## 项目结构

```
radiology_research_system/
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── pages/           # 页面组件
│   │   │   ├── Login.js
│   │   │   ├── Register.js
│   │   │   ├── Dashboard.js
│   │   │   ├── ProfileSetup.js
│   │   │   ├── ResearchInput.js
│   │   │   ├── PlanViewer.js
│   │   │   ├── ExpertReview.js
│   │   │   └── Admin.js
│   │   ├── components/      # 通用组件
│   │   └── contexts/        # React Context（认证状态）
│   └── package.json
├── backend/                  # Flask 后端
│   ├── routes/              # API 路由
│   │   ├── auth.py          # 认证
│   │   ├── profile.py       # 学生画像
│   │   ├── research.py      # 研究方案
│   │   ├── review.py        # 专家评审
│   │   ├── system.py        # 系统管理
│   │   └── llm_settings.py  # LLM 配置
│   ├── agents.py            # 多智能体定义
│   ├── agent_tools.py       # 智能体工具函数
│   ├── models.py            # 数据库模型
│   ├── app.py               # 应用入口
│   ├── config.py            # 配置文件
│   ├── api_clients.py       # PubMed / arXiv 客户端
│   ├── debug_logger.py      # 调试日志系统
│   └── requirements.txt
├── .env                     # 环境变量
└── 项目概述.md               # 详细技术文档
```

---

## 数据库

系统使用 SQLite 数据库（`backend/research_system.db`），包含以下核心表：

| 表名 | 说明 |
|------|------|
| `User` | 用户认证信息（学生/专家/管理员） |
| `StudentProfile` | 学生画像（学术信息、研究条件、技能水平） |
| `ResearchPlan` | 研究方案（13 个标准字段 + 评审反馈） |
| `BlindReview` | 专家盲评记录（多维度评分） |
| `SystemLog` | 系统日志 |

---

## API 简要说明

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/profile/student` | POST/PUT | 创建/更新学生画像 |
| `/api/multi-agent/generate-plan` | POST | 启动异步方案生成 |
| `/api/multi-agent/task/<id>` | GET | 查询任务进度 |
| `/api/research/plans` | GET | 获取方案列表 |
| `/api/research/plan/<id>` | GET | 获取方案详情 |
| `/api/research/export-word/<id>` | GET | 导出 Word 文档 |
| `/api/research/export-pdf/<id>` | GET | 导出 PDF 文档 |
| `/api/research/export-latex/<id>` | GET | 导出 LaTeX 文档 |
| `/api/review/submit` | POST | 提交评审 |
| `/api/pubmed/recommendations` | POST | 个性化文献推荐 |

---

## 注意事项

- 方案生成耗时约 5-10 分钟，请耐心等待（页面会实时显示进度）
- 首次使用需先完成学生画像填写
- 输入研究描述时建议包含放射学相关关键词（如影像模态、解剖部位、AI 技术等），系统会自动校验
