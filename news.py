"""读取固定游戏媒体 RSS；只保留有日期、原文链接的短摘要。"""

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlsplit

import aiohttp

SOURCES = (("indienova", "https://indienova.com/feed/", "indienova.com"),)
MAX_BYTES = 1_500_000
BEIJING = timezone(timedelta(hours=8))


def plain(value, limit):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()[:limit]


def parse_feed(body, *, source, domain, now, max_age_hours):
    if len(body) > MAX_BYTES or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("RSS 过大或含不支持的 XML 声明")
    root = ET.fromstring(body)
    articles = []
    seen = set()
    for item in root.findall("./channel/item")[:100]:
        title = plain(item.findtext("title"), 160)
        url = (item.findtext("link") or "").strip()
        parts = urlsplit(url)
        if not title or parts.scheme != "https" or parts.hostname != domain or parts.username or parts.password:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        if not now - timedelta(hours=max_age_hours) <= published <= now + timedelta(minutes=5):
            continue
        # 去掉 tracking 参数和 fragment，以原文地址去重。
        url = parts._replace(query="", fragment="").geturl()
        if url in seen:
            continue
        seen.add(url)
        articles.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "published": published.astimezone(BEIJING).isoformat(timespec="minutes"),
                "summary": plain(item.findtext("description"), 220),
            }
        )
    return sorted(articles, key=lambda item: item["published"], reverse=True)


async def download(url):
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "LubiGameNews/0.1 RSS reader"}) as session:
        async with session.get(url, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status != 200:
                raise ValueError("新闻源返回非 200 状态")
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("RSS 超出大小限制")
            return bytes(body)


class NewsService:
    def __init__(self, fetch=download):
        self.fetch = fetch
        self.lock = asyncio.Lock()
        self.cached_body = None
        self.fetched_at = 0.0
        self.fetched_text = ""

    async def get(self, *, count, max_age_hours, cache_minutes):
        async with self.lock:
            cached = self.cached_body is not None and time.monotonic() - self.fetched_at < cache_minutes * 60
            body = self.cached_body
            if not cached:
                # 不在失败时延长缓存期限，也不冒充新鲜新闻。
                body = await self.fetch(SOURCES[0][1])
            items = parse_feed(
                body,
                source=SOURCES[0][0],
                domain=SOURCES[0][2],
                now=datetime.now(timezone.utc),
                max_age_hours=max_age_hours,
            )
            if not cached:
                self.cached_body = body
                self.fetched_at = time.monotonic()
                self.fetched_text = datetime.now(BEIJING).isoformat(timespec="seconds")
            return items[:count], cached, self.fetched_text
