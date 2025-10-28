import feedparser
import json
import os
from datetime import datetime
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

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
    prompt = f"请将以下论文标题和摘要翻译成中文。\n\n标题: {title}\n摘要: {summary}\n\n请提供翻译后的标题、翻译后的摘要。返回格式为：\n翻译后的标题\n<翻译后的标题>\n\n翻译后的摘要\n<翻译后的摘要>。"
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "你是一个专业的学术论文翻译和摘要助手。严格遵守用户的要求，提供准确且流畅的中文翻译,内容精炼简洁，返回正确的格式。"},
            {"role": "user", "content": prompt}
        ],
        # temperature=0.3,
        # max_tokens=1000,
        # top_p=1,
    )
    # 检查响应内容
    if response.choices and response.choices[0].message:
        content = response.choices[0].message.content.strip()
        return content
    return "原始标题\n" + title + "\n\n" + "原始摘要\n" + summary  # 返回原始内容


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
    
    def item_exists(self, title):
        return title in self.title_set

def main():
    ARXIV_RSS_URL = "http://export.arxiv.org/rss/cs.CV"
    papers = fetch_arxiv_papers(ARXIV_RSS_URL)
    content = PaperContent(category=ARXIV_RSS_URL.split('/')[-1])
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
    except Exception as e:
        print(f"An error occurred: {e}")
        
    content.save_to_md()

if __name__ == "__main__":
    main()