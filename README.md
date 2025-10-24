# arXiv 每日论文摘要

自动获取 arXiv 每日最新论文并翻译为中文的工具。

## 功能特点

- 📚 自动从 arXiv RSS 订阅获取最新论文
- 🌏 使用 OpenAI API 将论文标题和摘要翻译为中文
- 💾 自动保存为 JSON 和 Markdown 格式
- 🔄 支持增量更新，避免重复处理
- ⚡ 智能去重机制

## 项目结构

```
arXiv-daily-paper/
├── main.py              # 主程序
├── api_key.env          # 环境变量配置文件（需自行创建）
├── arxiv_summaries/     # 输出目录
│   ├── cs.CV_YYYY-MM-DD.json  # JSON 格式数据
│   └── cs.CV_YYYY-MM-DD.md    # Markdown 格式报告
└── README.md            # 项目说明
```

## 安装依赖

```bash
pip install feedparser python-dotenv openai
```

或使用 requirements.txt（推荐）：

```bash
pip install -r requirements.txt
```

## 配置

### 1. 创建环境变量文件

在项目根目录创建 `api_key.env` 文件（或 `.env`），添加以下内容：

```env
OPENAI_API_KEY=你的OpenAI密钥
OPENAI_BASE_URL=https://api.openai.com/v1
```

> **注意**: 如果使用第三方 API 代理（如 ChatAnywhere），请修改 `OPENAI_BASE_URL` 为对应的地址。

### 2. 修改订阅类别（可选）

在 `main.py` 中修改 `ARXIV_RSS_URL` 变量来订阅不同的 arXiv 分类：

```python
ARXIV_RSS_URL = "http://export.arxiv.org/rss/cs.CV"  # 计算机视觉
# ARXIV_RSS_URL = "http://export.arxiv.org/rss/cs.AI"  # 人工智能
# ARXIV_RSS_URL = "http://export.arxiv.org/rss/cs.LG"  # 机器学习
```

常用 arXiv 分类：
- `cs.CV` - 计算机视觉与模式识别
- `cs.AI` - 人工智能
- `cs.LG` - 机器学习
- `cs.CL` - 计算与语言
- `cs.NE` - 神经与进化计算

完整分类列表请参考：https://arxiv.org/

## 使用方法

运行主程序：

```bash
python main.py
```

程序将：
1. 从 arXiv RSS 获取最新论文列表
2. 逐篇翻译论文标题和摘要
3. 实时保存到 JSON 文件（防止中断丢失数据）
4. 最后生成完整的 Markdown 报告

## 输出格式

### JSON 格式
```json
[
  {
    "title": "原始英文标题",
    "translated_title": "翻译后的中文标题",
    "translated_summary": "翻译后的中文摘要",
    "url": "论文链接"
  }
]
```

### Markdown 格式
```markdown
# 原始英文标题

**标题:** 翻译后的中文标题

**摘要:**

翻译后的中文摘要

**链接:** 论文链接

---
```

## 注意事项

1. **API 限制**: 程序在每次请求后会等待 2 秒，避免触发 API 频率限制
2. **去重机制**: 同一天内重复运行程序，已处理的论文会自动跳过
3. **数据持久化**: 每处理一篇论文都会立即保存到 JSON 文件，避免中断导致数据丢失
4. **成本控制**: 翻译会消耗 API 调用额度，请注意控制使用频率
5. **环境变量**: 确保 `api_key.env` 文件不要提交到版本控制系统


## 定时任务（可选）

### macOS/Linux (cron)

编辑 crontab：
```bash
crontab -e
```

添加定时任务（每天早上 12 点执行）：
```bash
0 12 * * * cd /path/to/arXiv-daily-paper && /usr/bin/python3 main.py
```

### Windows (任务计划程序)

1. 打开"任务计划程序"
2. 创建基本任务
3. 设置触发器为每天特定时间
4. 操作选择"启动程序"，填入 Python 路径和脚本路径

## 常见问题

### Q: 程序正常执行，保存文件为空
A: 代码采用arXiv RSS订阅，更新时间会晚于网页端，建议每日12:00之后执行。

### Q: API 请求失败怎么办？
A: 检查 `api_key.env` 配置是否正确，以及网络连接是否正常。

### Q: 翻译格式解析失败？
A: 可能是 GPT 返回格式不符合预期，程序会跳过该论文并打印错误信息。

### Q: 如何修改翻译的模型？
A: 在 `main.py` 的 `translate_and_summarize` 函数中修改 `model` 参数。

### Q: 如何同时订阅多个分类？
A: 修改 `main()` 函数，添加多个 RSS URL 的循环处理。

## 许可证

MIT License
