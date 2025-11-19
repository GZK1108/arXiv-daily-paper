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
├── config.py           # 行为配置（RSS、输出目录、是否翻译/远程保存）
├── main.py              # 主程序
├── api_key.env          # 环境变量配置文件（需自行创建）
├── arxiv_summaries/     # 输出目录
│   ├── cs.CV_YYYY-MM-DD.json  # JSON 格式数据
│   └── cs.CV_YYYY-MM-DD.md    # Markdown 格式报告
└── README.md            # 项目说明
```

## 安装依赖

```bash
pip install feedparser python-dotenv openai webdavclient3
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
MODEL = gpt-5-nano
OPENAI_API_KEY_BAK = 备用OpenAI秘钥，可以为空
OPENAI_BASE_URL_BAK = 备用链接，可以为空
MODEL_BAK = 备用模型，可以为空
WEBDAV_HOSTNAME=https://example/webdav
WEBDAV_LOGIN=your_name
WEBDAV_PASSWORD=your_password
```

> **注意**: 如果使用第三方 API 代理（如 ChatAnywhere），请修改 `OPENAI_BASE_URL` 为对应的地址。Webdav具体配置请参考你的Webdav提供方教程

### 2. 使用 config.py 管理行为（推荐）

编辑 `config.py` 来控制订阅源、输出目录和功能开关：

```python
# arXiv RSS 订阅链接（分类订阅）
ARXIV_RSS_URL = ["http://export.arxiv.org/rss/cs.CV", "http://export.arxiv.org/rss/cs.AI"]

# 输出目录
OUTPUT_DIR = "arxiv_summaries"

# 是否保存到远程 WebDAV 服务器
IS_REMOTE_SAVE = False

# 是否使用 AI 翻译
IS_TRANSLATE = False
```

常用 arXiv 分类：
- `cs.CV` - 计算机视觉与模式识别
- `cs.AI` - 人工智能
- `cs.LG` - 机器学习
- `cs.CL` - 计算与语言
- `cs.NE` - 神经与进化计算

完整分类列表请参考：https://arxiv.org/

也可以直接多类别订阅（不使用循环）：https://info.arxiv.org/help/rss.html

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
5. 如果在 `config.py` 中设置 `IS_REMOTE_SAVE = True`，程序会连接到 WebDAV 服务器，并将第 4 步生成的 Markdown 文件上传到远程目录 `/论文总结/`（可在 `main.py` 中调整上传路径）。

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
6. **WebDAV**: 若启用远程保存，请确保 `WEBDAV_HOSTNAME/WEBDAV_LOGIN/WEBDAV_PASSWORD` 已正确配置且服务器可达；默认上传到 `/论文总结/` 目录，可在 `main.py` 中修改。

7. **开关说明**: `IS_TRANSLATE=False` 时将直接使用英文标题和摘要；`IS_REMOTE_SAVE=False` 时只在本地输出，不会尝试连接 WebDAV。

8. **模型与格式**: 当前使用的模型为 `gpt-5-nano`，输出格式要求为：

```
<翻译后的标题>

<翻译后的摘要>
```

如果你更换模型或格式，请同步调整 `main.py` 中 `translate_and_summarize` 与 `process_translation_response` 的解析逻辑。


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
A: 常见报错为缺少 API Key：

```
openai.OpenAIError: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable
```

请检查 `api_key.env` 是否存在且包含正确的 `OPENAI_API_KEY`，并确认 `main.py` 顶部使用了 `load_dotenv("api_key.env")`。

### Q: 翻译格式解析失败？
A: 通常是返回没有包含预期的标签或换行。请确认模型返回以 `<翻译后的标题>` 开始，并且有一个空行分隔，再跟 `<翻译后的摘要>`。如需兼容更多格式，可调整 `process_translation_response()` 的正则与切分规则。

### Q: 如何修改翻译的模型？
A: 在 `main.py` 的 `translate_and_summarize` 函数中修改 `model` 参数即可，例如改为 `gpt-4o-mini`（请保证你的 BASE_URL 与 API Key 支持该模型）。

### Q: 如何同时订阅多个分类？
A: 修改 `main()` 函数，添加多个 RSS URL 的循环处理。

## 许可证

MIT License
