# arXiv RSS 订阅链接（可以是多个分类）
ARXIV_RSS_URL = ["http://export.arxiv.org/rss/cs.AI"]

# 输出目录
OUTPUT_DIR = "arxiv_summaries" 

# SQLite 数据库文件路径（统一存储所有论文）
DB_FILE = "arxiv_summaries/papers.db"

# 是否保存到远程WebDAV服务器
IS_REMOTE_SAVE = True

# 是否使用AI翻译
IS_TRANSLATE = True

# 允许的最大请求失败次数
MAX_FAILURES = 3