import feedparser
import json
import os
from datetime import datetime
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from webdav3.client import Client


load_dotenv("api_key.env")  # 指定加载 api_key.env 文件
client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    # base_url="https://api.chatanywhere.org/v1"
)

OUTPUT_DIR = "arxiv_summaries"

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def fetch_arxiv_papers(rss_url):
    feed = feedparser.parse(rss_url)
    return feed.entries

def translate_and_summarize(title, summary):
    prompt = f"""
    你是一名专业的学术论文翻译助手，具备精确的中英学术语言转换能力。
    你的任务是 **仅将下方的论文标题与摘要翻译成中文**，不得返回任何原文或额外解释。

    ---
    【输入内容】
    标题: {title}
    摘要: {summary}
    ---

    【翻译要求】
    1. 严格逐句忠实翻译，保持学术语气与逻辑一致。
    2. 不得添加、改写或总结原文内容。
    3. 不得输出任何原文、说明文字或空结果。
    4. 保证中文语法通顺、专业术语使用准确。

    【输出格式】
    请严格按照以下格式输出（不得省略任何标识符）：

    翻译后的标题
    <翻译后的标题>

    翻译后的摘要
    <翻译后的摘要>

    ---
    注意：
    - 仅输出上方指定格式的内容，不要输出英文原文。
    - 不要添加多余的空行、符号或说明性文字。
    - 若输入为空，也需返回空标签。
    """
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个专业的学术论文翻译助手。"
                    "你的回答必须准确、格式化、且符合科研论文中文写作规范。"
                    "任何时候都不得返回英文原文、解释、或无内容输出。"
                )
            },
            {"role": "user", "content": prompt}
        ],
        # temperature=0.2,
        # max_tokens=1000,
        # top_p=0.9,
    )


    # 检查响应内容
    if response.choices and response.choices[0].message:
        content = response.choices[0].message.content.strip()
        return content
    return "原始标题\n" + title + "\n\n" + "原始摘要\n" + summary  # 返回原始内容

# 新增webdav连接，保存到远程服务器
class WebDAVClient:
    def __init__(self):
        self._connect()
        
    def upload_file(self, local_path, remote_path):
        self.client.upload_sync(remote_path=remote_path, local_path=local_path)
    
    def _connect(self):
        options = {
            'webdav_hostname': os.getenv("WEBDAV_HOSTNAME"),
            'webdav_login':    os.getenv("WEBDAV_LOGIN"),
            'webdav_password': os.getenv("WEBDAV_PASSWORD")
        }
        self.client = Client(options)
        # 测试连接
        try:
            self.client.list('./')
            print("Connected to WebDAV server successfully.")
        except Exception as e:
            print("Failed to connect to WebDAV server:", e)


class PaperContent:
    def __init__(self, category="cs"):
        self.category = category
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        # 新建一个数据库文件，实时保存内容
        self.db_file = f"{OUTPUT_DIR}/{self.category}_{self.date_str}.json"
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=4)
            self.json_data = []
        else:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        # 新建一个hash set，方便查重
        self.title_set = set(item['title'] for item in self.json_data)

    def add_content(self, title, translated_title, translated_summary, url):    
        self.json_data.append({
            "title": title,
            "translated_title": translated_title,
            "translated_summary": translated_summary,
            "url": url
        })
        # 实时保存到数据库文件
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.json_data, f, ensure_ascii=False, indent=4)
        self.title_set.add(title)
    
    def save_to_md(self):
        filename = f"{OUTPUT_DIR}/{self.category}_{self.date_str}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            for paper in self.json_data:
                f.write(f"# {paper['title']}\n\n")
                f.write(f"**标题:** {paper['translated_title']}\n\n")
                f.write(f"**摘要:**\n\n{paper['translated_summary']}\n\n")
                f.write(f"**链接:** {paper['url']}\n\n")
                f.write("---\n\n")
        return filename
    
    def item_exists(self, title):
        return title in self.title_set

def main():
    is_remote_save = True  # 是否保存到远程WebDAV服务器
    ARXIV_RSS_URL = "http://export.arxiv.org/rss/cs.CV"
    papers = fetch_arxiv_papers(ARXIV_RSS_URL)
    content = PaperContent(category=ARXIV_RSS_URL.split('/')[-1])
    count = 0
    try:
        for paper in papers:
            paper_id = paper.id.split('/')[-1]
            title = paper.title
            summary = paper.summary
            url = paper.link
            print(f"Processing paper: {paper_id}")
            if content.item_exists(title):
                print(f"Paper {paper_id} already processed, skipping.")
                continue
            translated_content = translate_and_summarize(title, summary)
            # 假设返回内容格式为：翻译后的标题\n\n翻译后的摘要\n\n中文摘要
            parts = translated_content.split('\n\n')
            if len(parts) >= 2:
                try:
                    translated_title = parts[0].split('\n')[1].strip()
                except:
                    translated_title = parts[0].strip()
                translated_summary = parts[1].strip()
                content.add_content(title, translated_title, translated_summary, url)
            else:
                print(f"Unexpected response format for paper {paper_id}")
            time.sleep(2)  # 避免请求过于频繁
            count += 1
            if count >= 3:  # 限制每次处理的论文数量，
                break

    except Exception as e:
        print(f"An error occurred: {e}")
        
    file_path = content.save_to_md()
    if is_remote_save:
        webdav_client = WebDAVClient()
        local_md_path = file_path
        remote_md_path = f"/论文总结/{file_path.split('/')[-1]}"
        webdav_client.upload_file(local_md_path, remote_md_path)
        print(f"Uploaded {local_md_path} to WebDAV server at {remote_md_path}")

if __name__ == "__main__":
    main()