import feedparser
import json
import os
import re
import sqlite3
import asyncio
from datetime import datetime
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from webdav3.client import Client
from config import (
    ARXIV_RSS_URL,
    OUTPUT_DIR,
    IS_REMOTE_SAVE,
    IS_TRANSLATE,
    MAX_FAILURES,
    DB_FILE,
    MAX_CONCURRENT_REQUESTS,
)

load_dotenv("api_key.env")  # 指定加载 api_key.env 文件

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


class TranslationManager:
    """管理翻译任务的类，封装客户端、并发控制和失败重试逻辑"""
    
    def __init__(self, max_concurrent=5, max_failures=3):
        """
        初始化翻译管理器
        
        Args:
            max_concurrent: 最大并发数
            max_failures: 单个客户端最大失败次数
        """
        # 初始化主客户端
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self.model = os.getenv("MODEL", "")
        
        # 初始化备用客户端
        self.client_bak = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY_BAK", ""),
            base_url=os.getenv("OPENAI_BASE_URL_BAK", ""),
        )
        self.model_bak = os.getenv("MODEL_BAK", "")
        
        # 并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # 失败计数
        self.failure_count = {"primary": 0, "backup": 0}
        self.max_failures = max_failures
        
        # 系统提示词
        self.system_prompt = (
            "You are a highly constrained, professional academic translator. "
            "Your SOLE task is to translate the provided English paper title and abstract into fluent, high-quality, academic Chinese. "
            "You MUST strictly follow the REQUIRED OUTPUT FORMAT provided by the user, and you MUST NOT include any explanation, comments, extra text, self-checks, or English paragraphs outside of the format. "
            "Your output begins with <翻译后的标题> and ends after <翻译后的摘要>."
        )
    
    async def translate(self, title, summary):
        """
        异步翻译论文标题和摘要
        
        Args:
            title: 论文标题
            summary: 论文摘要
            
        Returns:
            翻译后的文本（包含标题和摘要）
        """
        async with self.semaphore:
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
            
            # 根据失败次数选择客户端优先级
            if self.failure_count["primary"] >= self.max_failures and os.getenv("OPENAI_API_KEY_BAK"):
                clients = [("backup", self.client_bak, self.model_bak), ("primary", self.client, self.model)]
            else:
                clients = [("primary", self.client, self.model), ("backup", self.client_bak, self.model_bak)]
            
            response = None
            for name, c, m in clients:
                # 跳过未配置的客户端或模型
                if c is None or not m:
                    continue
                    
                try:
                    response = await c.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": prompt_user}
                        ],
                    )
                    # 成功则重置失败计数并跳出
                    self.failure_count[name] = 0
                    break
                    
                except Exception as e:
                    print(f"Error during {name} OpenAI API call (model={m}): {e}")
                    self.failure_count[name] += 1
                    await asyncio.sleep(2)
            
            # 检查响应内容
            if response is not None and response.choices and response.choices[0].message:
                content = response.choices[0].message.content.strip()
                return content
            
            # 所有客户端都失败，返回原始内容
            return title + "\n\n" + summary

def fetch_arxiv_papers(rss_url):
    feed = feedparser.parse(rss_url)
    return feed.entries


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
        self.db_path = DB_FILE
        
        # 初始化数据库连接
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # 创建表（如果不存在）
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS papers (
                title TEXT PRIMARY KEY,
                translated_title TEXT,
                translated_summary TEXT,
                url TEXT,
                date TEXT NOT NULL,
                category TEXT NOT NULL
            )
        ''')
        self.conn.commit()
        
        # 加载当前日期和分类的论文到内存（用于生成当日 MD）
        self.papers_today = []
        self.cursor.execute('''
            SELECT title, translated_title, translated_summary, url
            FROM papers
            WHERE date = ? AND category = ?
        ''', (self.date_str, self.category))
        
        for row in self.cursor.fetchall():
            self.papers_today.append({
                "title": row[0],
                "translated_title": row[1],
                "translated_summary": row[2],
                "url": row[3]
            })

    def add_content(self, title, translated_title, translated_summary, url):
        """添加论文到数据库，使用 INSERT OR REPLACE 确保去重"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO papers (title, translated_title, translated_summary, url, date, category)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, translated_title, translated_summary, url, self.date_str, self.category))
            self.conn.commit()
            
            # 同时添加到当日列表
            self.papers_today.append({
                "title": title,
                "translated_title": translated_title,
                "translated_summary": translated_summary,
                "url": url
            })
        except sqlite3.IntegrityError as e:
            print(f"Paper already exists in database: {title}")
    
    def save_to_md(self):
        """根据当日数据生成 Markdown 文件"""
        filename = f"{OUTPUT_DIR}/{self.category}_{self.date_str}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"共有 {len(self.papers_today)} 篇论文。\n\n")
            for paper in self.papers_today:
                f.write(f"# {paper['title']}\n\n")
                f.write(f"**标题:** {paper['translated_title']}\n\n")
                f.write(f"**摘要:**\n\n{paper['translated_summary']}\n\n")
                f.write(f"**链接:** {paper['url']}\n\n")
                f.write("---\n\n")
        return filename
    
    def item_exists(self, title):
        """检查论文是否已存在于数据库（不限日期和分类）"""
        self.cursor.execute('SELECT 1 FROM papers WHERE title = ?', (title,))
        return self.cursor.fetchone() is not None
    
    def close(self):
        """关闭数据库连接"""
        self.conn.close()

async def process_papers_async(papers, content, translator):
    """
    异步处理论文列表
    
    Args:
        papers: 论文列表
        content: PaperContent 实例
        translator: TranslationManager 实例
    """
    papers_to_process = []
    
    # 筛选需要处理的论文
    for paper in papers:
        paper_id = paper.id.split('/')[-1]
        title = paper.title
        summary = paper.summary.split('\n')[1:]
        url = paper.link
        
        if content.item_exists(title):
            print(f"Paper {paper_id} already processed, skipping.")
            continue
        
        papers_to_process.append((paper_id, title, summary, url))
    
    # 如果需要翻译，创建异步任务并使用 as_completed 实时处理
    if IS_TRANSLATE and papers_to_process:
        print(f"Processing {len(papers_to_process)} papers with async translation...")
        
        # 创建包装函数，将任务和元数据绑定
        async def translate_with_metadata(paper_id, title, summary, url):
            result = await translator.translate(title, summary)
            return (paper_id, title, summary, url, result)
        
        # 创建所有任务
        tasks = [
            translate_with_metadata(paper_id, title, '\n'.join(summary), url)
            for paper_id, title, summary, url in papers_to_process
        ]
        
        # 使用 as_completed 实时处理完成的任务
        for coro in asyncio.as_completed(tasks):
            try:
                paper_id, title, summary, url, result = await coro
                
                translated_title, translated_summary = process_translation_response(result)
                
                if not translated_title and not translated_summary:
                    print(f"Failed to process translation for {paper_id}, using original.")
                    translated_title = title
                    translated_summary = summary
                    
            except Exception as e:
                print(f"Translation failed: {e}")
                # 如果失败，跳过这篇（因为无法获取元数据）
                continue
            
            # 立即存入数据库
            content.add_content(title, translated_title, translated_summary, url)
    
    # 不需要翻译时直接处理
    elif papers_to_process:
        for paper_id, title, summary, url in papers_to_process:
            content.add_content(title, title, '\n'.join(summary), url)
            print(f"Processed {paper_id}: {title}")

async def main_async():
    """异步主函数"""
    # 初始化翻译管理器
    translator = TranslationManager(
        max_concurrent=MAX_CONCURRENT_REQUESTS,
        max_failures=MAX_FAILURES
    )
    
    for arxiv_rss_url in ARXIV_RSS_URL:
        print(f"Fetching papers from {arxiv_rss_url}...")
        papers = fetch_arxiv_papers(arxiv_rss_url)
        content = PaperContent(category=arxiv_rss_url.split('/')[-1])
        
        try:
            await process_papers_async(papers, content, translator)
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 确保数据库连接关闭
            content.close()
        
        file_path = content.save_to_md()
        if IS_REMOTE_SAVE:
            webdav_client = WebDAVClient()
            local_md_path = file_path
            remote_md_path = f"/论文总结/{file_path.split('/')[-1]}"
            webdav_client.upload_file(local_md_path, remote_md_path)
            print(f"Uploaded {local_md_path} to WebDAV server at {remote_md_path}")

def main():
    """同步入口函数"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()