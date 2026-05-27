# 放射学研究方案生成系统 - 前端

本系统是一个基于React的放射学研究方案生成前端应用，支持三步式表单输入，确保用户按顺序完成研究需求描述、基本信息填写和技能目标设定。

## 核心功能

### 三步式表单流程
1. **Step 1**: 研究需求输入 - 用户详细描述研究想法和需求
2. **Step 2**: 基本信息填写 - 年级、专业方向、病例规模等
3. **Step 3**: 技能基础与目标 - 统计学基础、AI基础、目标期刊层级

### 关键特性
- 严格的步骤验证：用户必须按顺序完成所有步骤
- Step 3字段手动输入：不会自动填充，确保用户主动选择
- 实时表单验证：确保所有必需字段都已填写
- 用户画像集成：自动加载和保存用户信息

## 核心代码结构

### 主要文件
- `src/pages/ResearchInput.js` - 研究输入表单主组件
- `src/contexts/AuthContext.js` - 用户认证上下文
- `src/App.js` - 应用主入口

### 关键代码逻辑

#### Step 3字段初始化
```javascript
// 只预填充Step 1和Step 2，Step 3字段显式设置为空
setFormData(prev => ({
  ...prev,
  statistical_background: '',
  ai_background: '',
  target_journal_level: '',
  available_resources: {},
  student_input: ''
}));
```

#### 步骤验证逻辑
```javascript
// Step 3验证：确保所有必需字段已填写
} else if (currentStep === 3) {
  if (!formData.statistical_background) {
    setError('请选择统计学基础水平');
    return;
  }
  if (!formData.ai_background) {
    setError('请选择AI基础水平');
    return;
  }
  if (!formData.target_journal_level) {
    setError('请选择目标期刊层级');
    return;
  }
}
```

#### 提交控制
```javascript
// 只有Step 3且字段完整时才允许提交
if (currentStep !== 3) {
  setError('请完成所有步骤后再提交');
  return;
}
```

## 技术栈

- React 18
- React Bootstrap
- Axios
- React Router

## 安装和运行

### 开发环境
```bash
npm install
npm start
```

### 生产构建
```bash
npm run build
serve -s build
```

## API接口

- 用户画像：`http://localhost:5002/api/profile/*`
- 方案生成：`http://localhost:5002/api/multi-agent/generate-plan`

## 测试验证

访问 `http://localhost:3007/research-input` 验证：
1. Step 3字段是否为空等待手动输入
2. 是否必须完成所有步骤才能提交
3. 表单验证是否正常工作

## 项目状态

✅ Step 3字段手动输入功能已实现
✅ 严格的步骤验证和提交控制
✅ 用户画像数据管理
✅ 生产环境构建部署