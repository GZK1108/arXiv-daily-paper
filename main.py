import feedparser
import json
import os
import re
from datetime import datetime
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from webdav3.client import Client
from config import (
    ARXIV_RSS_URL,
    OUTPUT_DIR,
    IS_REMOTE_SAVE,
    IS_TRANSLATE,
    MAX_FAILURES,
)

load_dotenv("api_key.env")  # 指定加载 api_key.env 文件
client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    # base_url="https://api.chatanywhere.org/v1"
)
model = os.getenv("MODEL", "")

client_bak = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_BAK", ""),
    base_url=os.getenv("OPENAI_BASE_URL_BAK", ""),
)
model_bak = os.getenv("MODEL_BAK", "")

# 增加一个全局计数器，如果client请求失败超过一定次数，默认调用备用client
failure_count = {"primary": 0, "backup": 0}


Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def fetch_arxiv_papers(rss_url):
    feed = feedparser.parse(rss_url)
    return feed.entries

def translate_and_summarize(title, summary):
    prompt_user = f"""
    Translate the following academic paper Title and Abstract into Chinese.

    ---
    INPUT
    Title: {title}
    Abstract: {summary}
    ---

    **CORE REQUIREMENTS**
    1. **Academic Quality:** Translate faithfully into fluent, professional Chinese suitable for an academic paper.
    2. **Proper Nouns:** Keep necessary proper nouns, formulas, or short English terms (e.g., specific algorithms or acronyms) if a clear Chinese equivalent is lacking, but **the majority of the text MUST be in Chinese**.
    3. **Format ONLY:** You MUST strictly adhere to the required output format below. **DO NOT** explain, comment, summarize, or add any text before, between, or after the translation block.

    ---

    **REQUIRED OUTPUT FORMAT (STRICTLY ADHERE)**

    <翻译后的标题>

    <翻译后的摘要>

    ---

    Return ONLY the content within the REQUIRED OUTPUT FORMAT section, starting with "<翻译后的标题>" and ending with the last line of the abstract translation.
    """
    global failure_count
    clients = []
    # 优先选择：若主客户端连续失败达到阈值且配置了备用密钥，则先尝试备用客户端
    if failure_count["primary"] >= MAX_FAILURES and os.getenv("OPENAI_API_KEY_BAK"):
        clients = [("backup", client_bak, model_bak), ("primary", client, model)]
    else:
        clients = [("primary", client, model), ("backup", client_bak, model_bak)]

    response = None
    for name, c, m in clients:
        # 跳过未配置的客户端或模型
        if c is None or not m:
            continue
        try:
            response = c.chat.completions.create(
                model=m,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a highly constrained, professional academic translator. "
                            "Your SOLE task is to translate the provided English paper title and abstract into fluent, high-quality, academic Chinese. "
                            "You MUST strictly follow the REQUIRED OUTPUT FORMAT provided by the user, and you MUST NOT include any explanation, comments, extra text, self-checks, or English paragraphs outside of the format. "
                            "Your output begins with <翻译后的标题> and ends after <翻译后的摘要>."
                        )
                    },
                    {"role": "user", "content": prompt_user}
                ],
                # temperature=0.0,
                # top_p=1.0,
                # max_tokens=1200,
            )
            # 成功则重置失败计数并跳出
            failure_count[name] = 0
            break
        except Exception as e:
            print(f"Error during {name} OpenAI API call (model={m}):", e)
            failure_count[name] += 1
            time.sleep(2)
    
    # 检查响应内容
    if response is not None and response.choices and response.choices[0].message:
        content = response.choices[0].message.content.strip()
        return content

    return title + "\n\n" + summary  # 返回原始内容

# 返回结果处理
def process_translation_response(response_text):
    # 移除<翻译后标题></n翻译后的标题>和<翻译后摘要></n翻译后的摘要>标签，并去除首尾空白，然后返回处理后的字符串
    cleaned = re.sub(r'<翻译后的标题>|</翻译后的标题>|<翻译后的摘要>|</翻译后的摘要>|摘要：', '', response_text).strip()
    # 剔除多余空行
    cleaned = re.sub(r'(?:\r\n|\r|\n){3,}', '\n\n', cleaned)
    parts = cleaned.split('\n\n')
    if len(parts) >= 2:
        translated_title = parts[0].strip()
        # 将剩余部分作为摘要
        translated_summary = '\n\n'.join(part.strip() for part in parts[1:])
        return translated_title, translated_summary
    else:
        return None, None

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
    for arxiv_rss_url in ARXIV_RSS_URL:
        print(f"Fetching papers from {arxiv_rss_url}...")
        papers = fetch_arxiv_papers(arxiv_rss_url)
        content = PaperContent(category=arxiv_rss_url.split('/')[-1])
        try:
            for paper in papers:
                paper_id = paper.id.split('/')[-1]
                title = paper.title
                summary = paper.summary.split('\n')[-1]
                url = paper.link
                if content.item_exists(title):
                    print(f"Paper {paper_id} already processed, skipping.")
                    continue
                print(f"Processing {paper_id}: {title}")
                if IS_TRANSLATE:
                    if failure_count["primary"] + failure_count["backup"] >= MAX_FAILURES * 2:
                        print("Both OpenAI clients have failed too many times. Exiting.")
                        break
                    translated_content = translate_and_summarize(title, summary)
                    translated_title, translated_summary = process_translation_response(translated_content)
                    if not translated_title and not translated_summary:
                        print(f"Failed to process translation for paper {paper_id}, skipping.")
                        translated_title = title
                        translated_summary = summary
                else:
                    translated_title = title
                    translated_summary = summary

                content.add_content(title, translated_title, translated_summary, url)
                time.sleep(3)  # 避免请求过于频繁

        except Exception as e:
            print(f"An error occurred: {e}")
        
        file_path = content.save_to_md()
        if IS_REMOTE_SAVE:
            webdav_client = WebDAVClient()
            local_md_path = file_path
            remote_md_path = f"/论文总结/{file_path.split('/')[-1]}"
            webdav_client.upload_file(local_md_path, remote_md_path)
            print(f"Uploaded {local_md_path} to WebDAV server at {remote_md_path}")

if __name__ == "__main__":
    main()