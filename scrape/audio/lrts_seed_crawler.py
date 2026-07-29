from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi.requests import Session
from scrapling import Selector

BASE_URL = "https://www.lrts.me"
USER_AGENT = "Mozilla/5.0 seed-metadata-research"
logger = logging.getLogger("lrts_seed_crawler")
DEFAULT_START_URLS = [
    "/book/category",
    "/book/category/1/recommend",
    "/book/category/3/recommend",
    "/book/category/6/recommend",
    "/rank/hot/week",
    "/explore/album",
]


@dataclass(frozen=True)
class SourceRef:
    source_type: str
    source_id: str
    url: str


class LrtsCrawler:
    def __init__(
        self,
        project_root: Path,
        *,
        delay_seconds: float,
        timeout_seconds: int,
        refresh_cache: bool,
        summary_max_chars: int,
    ) -> None:
        self.project_root = project_root
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.refresh_cache = refresh_cache
        self.summary_max_chars = summary_max_chars
        self.raw_root = project_root / "seeds" / "raw" / "lrts"
        self.page_cache_dir = self.raw_root / "pages"
        self.json_dir = self.raw_root / "json"
        self.foundation_dir = project_root / "seeds" / "1_foundation"
        self.content_dir = project_root / "seeds" / "2_content"
        self.trade_dir = project_root / "seeds" / "4_trade"
        self.operation_dir = project_root / "seeds" / "6_operation"
        self.http = Session(impersonate="chrome")
        self.last_request_at = 0.0
        self.discovered_categories: dict[str, dict[str, Any]] = {}

    def run(
        self,
        *,
        start_urls: list[str],
        max_list_pages: int,
        max_items: int,
        max_track_pages: int,
        max_topic_pages: int,
        max_operation_refs: int,
        crawl_narrator_pages: bool,
    ) -> dict[str, int]:
        self._ensure_dirs()
        started_at = time.monotonic()
        logger.info(
            "start crawl: output_root=%s max_list_pages=%s max_items=%s "
            "max_track_pages=%s max_topic_pages=%s max_operation_refs=%s "
            "crawl_narrator_pages=%s",
            self.project_root,
            max_list_pages,
            max_items,
            max_track_pages,
            max_topic_pages,
            max_operation_refs,
            crawl_narrator_pages,
        )

        logger.info("fetch home metadata")
        home_html = self.fetch_text("/")
        home_metadata = self.parse_home_page(home_html)
        logger.info(
            "home metadata parsed: organizations=%s recommend_slots=%s "
            "recommend_items=%s topics=%s",
            len(home_metadata["organizations"]),
            len(home_metadata["recommend_slots"]),
            len(home_metadata["recommend_items"]),
            len(home_metadata["topics"]),
        )

        logger.info("collect ranking definitions and items")
        ranking_list = self.collect_ranking_list()
        ranking_items = self.collect_ranking_items(ranking_list)
        logger.info(
            "rankings collected: ranking_list=%s ranking_items=%s",
            len(ranking_list),
            len(ranking_items),
        )

        logger.info("collect topic refs and details")
        topic_refs = self.collect_topic_refs(
            home_metadata["topics"],
            max_topic_pages=max_topic_pages,
        )
        topics = self.collect_topics(topic_refs)
        logger.info("topics collected: topics=%s", len(topics))

        logger.info("discover source refs from list pages")
        source_refs = self.collect_source_refs(start_urls, max_list_pages)
        operation_refs = self.collect_operation_source_refs(
            ranking_items,
            home_metadata["recommend_items"],
            topics,
        )
        selected_operation_refs = (
            operation_refs[:max_operation_refs]
            if max_operation_refs >= 0
            else operation_refs
        )
        selected_refs = self.merge_source_refs(
            source_refs[:max_items],
            selected_operation_refs,
        )
        logger.info(
            "source refs discovered: total=%s selected=%s operation_refs=%s "
            "operation_refs_selected=%s categories=%s",
            len(source_refs),
            len(selected_refs),
            len(operation_refs),
            len(selected_operation_refs),
            len(self.discovered_categories),
        )

        albums: list[dict[str, Any]] = []
        tracks: list[dict[str, Any]] = []
        authors: dict[str, dict[str, Any]] = {}
        narrators: dict[str, dict[str, Any]] = {}
        categories: dict[str, dict[str, Any]] = dict(self.discovered_categories)
        sources: list[dict[str, Any]] = []

        for index, ref in enumerate(selected_refs, start=1):
            if index == 1 or index % 10 == 0 or index == len(selected_refs):
                logger.info(
                    "crawl album detail progress: %s/%s current=%s:%s",
                    index,
                    len(selected_refs),
                    ref.source_type,
                    ref.source_id,
                )
            try:
                detail_html = self.fetch_text(ref.url)
            except RuntimeError as exc:
                logger.warning(str(exc))
                continue
            album = self.parse_detail_page(ref, detail_html)
            if not album:
                logger.warning("skip unparsable detail page: %s", ref.url)
                continue

            albums.append(album)
            sources.append(
                {
                    "source_type": ref.source_type,
                    "source_id": ref.source_id,
                    "url": ref.url,
                }
            )

            category_name = album.get("category_name")
            if category_name:
                categories.setdefault(
                    str(category_name),
                    {
                        "source_category_id": "",
                        "source_category_name": category_name,
                        "parent_source_category_id": "",
                        "parent_category_name": "",
                        "category_level": 2,
                        "category_type": "program"
                        if ref.source_type == "album"
                        else "audiobook",
                    },
                )

            for author_name in album.get("authors", []):
                if author_name:
                    authors.setdefault(
                        author_name,
                        {
                            "source_author_name": author_name,
                            "author_type": "original",
                        },
                    )

            for narrator in album.get("narrators", []):
                narrator_key = str(
                    narrator.get("source_narrator_id") or narrator.get("narrator_name")
                )
                if narrator_key:
                    narrators.setdefault(narrator_key, narrator)

            tracks.extend(self.collect_tracks(ref, detail_html, max_track_pages))

        if crawl_narrator_pages:
            logger.info("enrich narrator profiles: narrators=%s", len(narrators))
            self.enrich_narrators(narrators)

        logger.info("write raw json and csv outputs")
        self.write_jsonl(self.json_dir / "crawl_sources.jsonl", sources)
        self.write_jsonl(self.json_dir / "albums.jsonl", albums)
        self.write_jsonl(self.json_dir / "tracks.jsonl", tracks)
        self.write_jsonl(self.json_dir / "authors.jsonl", list(authors.values()))
        self.write_jsonl(self.json_dir / "narrators.jsonl", list(narrators.values()))
        self.write_jsonl(self.json_dir / "categories.jsonl", list(categories.values()))
        self.write_jsonl(
            self.json_dir / "organizations.jsonl", home_metadata["organizations"]
        )
        self.write_jsonl(self.json_dir / "ranking_list.jsonl", ranking_list)
        self.write_jsonl(self.json_dir / "ranking_items.jsonl", ranking_items)
        self.write_jsonl(
            self.json_dir / "recommend_slots.jsonl", home_metadata["recommend_slots"]
        )
        self.write_jsonl(
            self.json_dir / "recommend_items.jsonl", home_metadata["recommend_items"]
        )
        self.write_jsonl(self.json_dir / "topics.jsonl", topics)

        self.write_csv_outputs(
            albums,
            tracks,
            authors,
            narrators,
            categories,
            home_metadata["organizations"],
            ranking_list,
            ranking_items,
            home_metadata["recommend_slots"],
            home_metadata["recommend_items"],
            topics,
        )

        summary = {
            "source_refs": len(source_refs),
            "operation_refs": len(operation_refs),
            "albums": len(albums),
            "tracks": len(tracks),
            "authors": len(authors),
            "narrators": len(narrators),
            "categories": len(categories),
            "organizations": len(home_metadata["organizations"]),
            "ranking_list": len(ranking_list),
            "ranking_items": len(ranking_items),
            "recommend_slots": len(home_metadata["recommend_slots"]),
            "recommend_items": len(home_metadata["recommend_items"]),
            "topics": len(topics),
        }
        logger.info(
            "crawl finished in %.1fs: %s",
            time.monotonic() - started_at,
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
        )
        return summary

    def parse_home_page(self, page_html: str) -> dict[str, list[dict[str, Any]]]:
        recommend_slots = self.parse_recommend_slots(page_html)
        return {
            "organizations": self.parse_organizations(page_html),
            "recommend_slots": recommend_slots,
            "recommend_items": self.parse_recommend_items(page_html, recommend_slots),
            "topics": self.parse_home_topics(page_html),
        }

    def parse_organizations(self, page_html: str) -> list[dict[str, Any]]:
        organizations: list[dict[str, Any]] = []
        seen: set[str] = set()
        pattern = (
            r'<div class=["\'][^"\']*h-agency-l[^"\']*["\'][^>]*>'
            r'[\s\S]*?<a href=["\']/org/(\d+)["\']>([^<]+)</a>'
            r'[\s\S]*?<p>([\s\S]*?)\s*\[<a class=["\']link["\'] href=["\']/org/\1["\']>'
        )
        for source_id, name, intro in re.findall(pattern, page_html):
            if source_id in seen:
                continue
            seen.add(source_id)
            organizations.append(
                {
                    "source_organization_id": source_id,
                    "organization_name": self.clean_text(name),
                    "organization_type": "publisher",
                    "intro": self.truncate_text(
                        self.clean_text(intro), self.summary_max_chars
                    ),
                    "source_url": self.normalize_url(f"/org/{source_id}"),
                    "source": "lrts",
                }
            )
        return organizations

    def parse_recommend_slots(self, page_html: str) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        seen: set[str] = set()
        for title, href in re.findall(
            r'<div class=["\']h-title["\'][\s\S]*?<span class=["\']h-title-text["\']>([^<]+)</span>'
            r'[\s\S]*?<a class=["\']h-title-more["\'] href=["\']([^"\']+)["\']>',
            page_html,
        ):
            slot_name = self.clean_text(title).rstrip("/")
            slot = self.recommend_slot_from_title(slot_name, href)
            if slot["slot_code"] in seen:
                continue
            seen.add(slot["slot_code"])
            slots.append(slot)

        static_slots = [
            {
                "slot_code": "LR_SLOT_HOME_TOPIC",
                "slot_name": "精彩专题",
                "page_code": "home",
                "slot_type": "topic_list",
                "max_item_count": 3,
                "source_url": self.normalize_url("/"),
                "source": "lrts",
            },
            {
                "slot_code": "LR_SLOT_HOME_ORG_BOOK",
                "slot_name": "机构热书",
                "page_code": "home",
                "slot_type": "album_list",
                "max_item_count": 8,
                "source_url": self.normalize_url("/"),
                "source": "lrts",
            },
        ]
        for slot in static_slots:
            if slot["slot_code"] not in seen:
                slots.append(slot)
                seen.add(slot["slot_code"])
        return slots

    def recommend_slot_from_title(self, slot_name: str, href: str) -> dict[str, Any]:
        slot_type = "album_list"
        max_item_count = 8
        if "主播" in slot_name:
            slot_type = "narrator_list"
            max_item_count = 6
        elif "专题" in slot_name:
            slot_type = "topic_list"
            max_item_count = 3

        slot_key = (
            self.slug_text(slot_name)
            or hashlib.sha1(slot_name.encode("utf-8")).hexdigest()[:8]
        )
        return {
            "slot_code": f"LR_SLOT_HOME_{slot_key.upper()}",
            "slot_name": slot_name,
            "page_code": "home",
            "slot_type": slot_type,
            "max_item_count": max_item_count,
            "source_url": self.normalize_url(href),
            "source": "lrts",
        }

    def parse_home_topics(self, page_html: str) -> list[dict[str, Any]]:
        topics: list[dict[str, Any]] = []
        page = self.selector(page_html)
        for topic_link in page.css('a[href^="/topic/"]'):
            href = topic_link.attrib.get("href", "")
            source_id = self.first_match(href, r"^/topic/(\d+)")
            image_url = topic_link.css("img::attr(src)").get() or ""
            if not source_id or not image_url:
                continue
            topics.append(
                {
                    "source_topic_id": source_id,
                    "topic_title": "",
                    "cover_url": html.unescape(image_url),
                    "summary": "",
                    "source_url": self.normalize_url(f"/topic/{source_id}"),
                    "source": "lrts",
                }
            )
        return topics

    def collect_topic_refs(
        self, seed_refs: list[dict[str, Any]], max_topic_pages: int
    ) -> list[dict[str, Any]]:
        topics: dict[str, dict[str, Any]] = {
            str(item["source_topic_id"]): item for item in seed_refs
        }
        queue = [self.normalize_url("/topic")]
        visited: set[str] = set()

        while queue and len(visited) < max_topic_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            logger.info(
                "fetch topic list page: %s/%s topics=%s url=%s",
                len(visited),
                max_topic_pages,
                len(topics),
                url,
            )
            try:
                page_html = self.fetch_text(url)
            except RuntimeError as exc:
                logger.warning(str(exc))
                continue
            for topic in self.parse_home_topics(page_html):
                topics.setdefault(str(topic["source_topic_id"]), topic)
            for next_url in self.parse_next_topic_urls(page_html):
                normalized = self.normalize_url(next_url)
                if normalized not in visited and normalized not in queue:
                    queue.append(normalized)

        return list(topics.values())

    def parse_next_topic_urls(self, page_html: str) -> list[str]:
        urls = []
        for href in self.selector(page_html).css(".pagination a::attr(href)").getall():
            if re.match(r"^/topic(?:/\d+/\d+)?$", href):
                urls.append(href)
        return urls

    def parse_recommend_items(
        self, page_html: str, recommend_slots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        slot_by_name = {slot["slot_name"]: slot["slot_code"] for slot in recommend_slots}
        rows = []
        rows.extend(
            self.parse_home_album_items(
                page_html,
                r'<div class=["\']h-new-book["\'][^>]*>([\s\S]*?)<div class=["\']h-hot-album["\']',
                str(slot_by_name.get("每日推荐", "LR_SLOT_HOME_每日推荐")),
                "book",
            )
        )
        rows.extend(
            self.parse_home_album_items(
                page_html,
                r'<div class=["\']h-hot-album["\'][^>]*>([\s\S]*?)</div>\s*</div>\s*<div class=["\']clear["\']',
                str(slot_by_name.get("热门节目", "LR_SLOT_HOME_热门节目")),
                "album",
            )
        )
        rows.extend(
            self.parse_home_narrator_items(
                page_html,
                str(slot_by_name.get("主播推荐", "LR_SLOT_HOME_主播推荐")),
            )
        )
        rows.extend(
            self.parse_home_topic_items(
                page_html,
                str(slot_by_name.get("精彩专题", "LR_SLOT_HOME_TOPIC")),
            )
        )
        return self.dedupe_operation_items(rows)

    def parse_home_album_items(
        self, page_html: str, block_pattern: str, slot_code: str, source_type: str
    ) -> list[dict[str, Any]]:
        block = self.first_match(page_html, block_pattern)
        if not block:
            return []

        page = self.selector(block)
        items = page.css("li.book-item") or page.css("li.album-item")
        rows = []
        for sort_no, item in enumerate(items, start=1):
            href = (
                item.css(".book-item-name a::attr(href)").get()
                or item.css(".album-item-name a::attr(href)").get()
                or item.css('a[href^="/book/"]::attr(href)').get()
                or item.css('a[href^="/album/"]::attr(href)').get()
                or ""
            )
            source_id = self.first_match(href, r"^/(?:book|album)/(\d+)")
            if not source_id:
                continue
            title = (
                item.css(".book-item-name a::text").get()
                or item.css(".album-item-name a::text").get()
                or ""
            )
            rows.append(
                {
                    "slot_code": slot_code,
                    "target_type": "album",
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": self.clean_text(title),
                    "image_url": html.unescape(
                        item.css(".book-item-photo img::attr(src)").get()
                        or item.css(".album-item-photo img::attr(src)").get()
                        or ""
                    ),
                    "category_name": self.clean_text(
                        item.css(".category-b::text").get() or ""
                    ),
                    "author_name": self.clean_text(
                        item.css("a.author::text").get() or ""
                    ),
                    "narrator_name": self.clean_text(
                        item.css("a.g-user-shutdown::text").get()
                        or item.css('a[href^="/search/album/"]::text').get()
                        or ""
                    ),
                    "jump_url": self.normalize_url(href),
                    "sort_no": sort_no,
                    "source": "lrts",
                }
            )
        return rows

    def parse_home_narrator_items(
        self, page_html: str, slot_code: str
    ) -> list[dict[str, Any]]:
        page = self.selector(page_html)
        rows = []
        for sort_no, item in enumerate(page.css(".lazy-anchor > ul > li"), start=1):
            href = item.css('a.g-user-shutdown[href^="/user/"]::attr(href)').get() or ""
            source_id = self.first_match(href, r"^/user/(\d+)")
            if not source_id:
                continue
            image_url = item.css('a.g-user-shutdown[href^="/user/"] img::attr(src)').get()
            title = (
                item.css('a.g-user-shutdown[href^="/user/"] img::attr(alt)').get()
                or item.css(".lazy-anchor-name::text").get()
                or ""
            )
            rows.append(
                {
                    "slot_code": slot_code,
                    "target_type": "narrator",
                    "source_type": "user",
                    "source_id": source_id,
                    "title": self.clean_text(title),
                    "image_url": html.unescape(image_url or ""),
                    "category_name": "",
                    "author_name": "",
                    "narrator_name": self.clean_text(title),
                    "jump_url": self.normalize_url(href),
                    "sort_no": sort_no,
                    "source": "lrts",
                }
            )
        return rows

    def parse_home_topic_items(
        self, page_html: str, slot_code: str
    ) -> list[dict[str, Any]]:
        rows = []
        page = self.selector(page_html)
        for sort_no, topic_link in enumerate(page.css('a[href^="/topic/"]'), start=1):
            href = topic_link.attrib.get("href", "")
            source_id = self.first_match(href, r"^/topic/(\d+)")
            image_url = topic_link.css("img::attr(src)").get() or ""
            if not source_id or not image_url:
                continue
            rows.append(
                {
                    "slot_code": slot_code,
                    "target_type": "topic",
                    "source_type": "topic",
                    "source_id": source_id,
                    "title": "",
                    "image_url": html.unescape(image_url),
                    "category_name": "",
                    "author_name": "",
                    "narrator_name": "",
                    "jump_url": self.normalize_url(href),
                    "sort_no": sort_no,
                    "source": "lrts",
                }
            )
        return rows

    def collect_topics(self, topic_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        topics: list[dict[str, Any]] = []
        for index, topic_ref in enumerate(topic_refs, start=1):
            source_url = str(topic_ref["source_url"])
            logger.info("fetch topic detail: %s/%s %s", index, len(topic_refs), source_url)
            try:
                page_html = self.fetch_text(source_url)
            except RuntimeError as exc:
                logger.warning(str(exc))
                topics.append(topic_ref)
                continue
            topic = dict(topic_ref)
            topic.update(self.parse_topic_page(page_html))
            topics.append(topic)
        return topics

    def parse_topic_page(self, page_html: str) -> dict[str, Any]:
        page = self.selector(page_html)
        title = page.css(".topic-title::text").get() or ""
        cover_url = page.css(".topic-banner img::attr(src)").get() or ""
        summary = self.first_match(
            page_html,
            r'<div class=["\']topic-banner-r["\'][\s\S]*?<p class=["\']f14["\']>([\s\S]*?)</p>',
        )
        book_count = self.first_match(page_html, r"<span[^>]*>书籍：</span>\s*(\d+)")
        play_count = self.first_match(
            page_html, r"<span[^>]*>收听次数：</span>\s*([^<]+)"
        )
        updated_at_text = self.first_match(
            page_html, r"<span[^>]*>更新时间：</span>\s*([^<]+)"
        )
        topic_items = []
        for item_link in page.css('.book-item-name[href^="/book/"]'):
            href = item_link.attrib.get("href", "")
            book_id = self.first_match(href, r"^/book/(\d+)")
            item_title = item_link.css("::text").get() or ""
            if not book_id:
                continue
            topic_items.append(
                {
                    "source_type": "book",
                    "source_id": book_id,
                    "title": self.clean_text(item_title),
                }
            )
        return {
            "topic_title": self.clean_text(title),
            "cover_url": html.unescape(cover_url or ""),
            "summary": self.truncate_text(
                self.clean_text(summary), self.summary_max_chars
            ),
            "book_count": self.parse_int(book_count) or "",
            "play_count_text": self.clean_text(play_count),
            "updated_at_text": self.clean_text(updated_at_text),
            "items": topic_items,
        }

    def collect_ranking_list(self) -> list[dict[str, Any]]:
        page_html = self.fetch_text("/rank/hot/week")
        rank_nav: dict[str, str] = {}
        for slug, name in re.findall(
            r'href=["\']/rank/([^/]+)/week["\'][^>]*>([^<]+)</a>', page_html
        ):
            rank_nav.setdefault(slug, self.clean_text(name))
        period_nav: dict[str, str] = {}
        for period, name in re.findall(
            r'href=["\']/rank/hot/([^/"\']+)["\'][^>]*>([^<]+)</a>', page_html
        ):
            period_nav.setdefault(period, self.clean_text(name))
        rank_name_map = {
            "hot": "热播榜",
            "comment": "热评榜",
            "search": "热搜榜",
            "down": "免费榜",
            "male": "畅销榜",
            "female": "完结榜",
        }
        rank_type_map = {
            "hot": "hot_album",
            "comment": "commented_album",
            "search": "searched_album",
            "down": "free_album",
            "male": "paid_album",
            "female": "completed_album",
        }
        period_name_map = {
            "week": "周榜",
            "month": "月榜",
            "all": "总榜",
        }
        period_type_map = {
            "week": "weekly",
            "month": "monthly",
            "all": "total",
        }
        ranking_list = []
        for slug, rank_name in rank_nav.items():
            ranking_type = rank_type_map.get(slug)
            if not ranking_type:
                continue
            for period, period_name in period_nav.items():
                period_type = period_type_map.get(period)
                if not period_type:
                    continue
                ranking_list.append(
                    {
                        "source_ranking_slug": slug,
                        "source_period_slug": period,
                        "ranking_code": f"LR_RANK_{slug.upper()}_{period.upper()}",
                        "ranking_name": f"{rank_name_map.get(slug, rank_name)}{period_name_map.get(period, period_name)}",
                        "ranking_type": ranking_type,
                        "period_type": period_type,
                        "source_url": self.normalize_url(f"/rank/{slug}/{period}"),
                        "yn": 1,
                        "source": "lrts",
                    }
                )
        return ranking_list

    def collect_ranking_items(
        self, ranking_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        ranking_items = []
        for index, ranking in enumerate(ranking_list, start=1):
            source_url = str(ranking["source_url"])
            logger.info(
                "fetch ranking page: %s/%s %s",
                index,
                len(ranking_list),
                source_url,
            )
            try:
                page_html = self.fetch_text(source_url)
            except RuntimeError as exc:
                logger.warning(str(exc))
                continue
            ranking_items.extend(self.parse_ranking_items_page(ranking, page_html))
        return ranking_items

    def parse_ranking_items_page(
        self, ranking: dict[str, Any], page_html: str
    ) -> list[dict[str, Any]]:
        rows = []
        page = self.selector(page_html)
        for rank_no, item in enumerate(
            page.css(".ranking-books-list li.book-item"), start=1
        ):
            href = item.css(".book-item-name::attr(href)").get() or ""
            source_type = "album" if href.startswith("/album/") else "book"
            source_id = self.first_match(href, r"^/(?:book|album)/(\d+)")
            if not source_id:
                continue
            rows.append(
                {
                    "ranking_code": ranking["ranking_code"],
                    "source_ranking_slug": ranking["source_ranking_slug"],
                    "source_period_slug": ranking["source_period_slug"],
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_type": "album",
                    "rank_no": rank_no,
                    "title": self.clean_text(
                        item.css(".book-item-name::text").get() or ""
                    ),
                    "image_url": html.unescape(
                        item.css(".book-item-photo img::attr(src)").get() or ""
                    ),
                    "author_name": self.clean_text(
                        item.css(".book-item-info a.author::text").get() or ""
                    ),
                    "narrator_name": self.clean_text(
                        item.css(".book-item-info a.g-user-shutdown::text").get()
                        or ""
                    ),
                    "summary": self.truncate_text(
                        self.clean_text(item.css(".book-item-desc::text").get() or ""),
                        self.summary_max_chars,
                    ),
                    "source_url": str(ranking["source_url"]),
                    "jump_url": self.normalize_url(href),
                    "source": "lrts",
                }
            )
        return rows

    def dedupe_operation_items(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in rows:
            key = (
                str(row["slot_code"]),
                str(row["target_type"]),
                str(row["source_type"]),
                str(row["source_id"]),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def collect_operation_source_refs(
        self,
        ranking_items: list[dict[str, Any]],
        recommend_items: list[dict[str, Any]],
        topics: list[dict[str, Any]],
    ) -> list[SourceRef]:
        refs: dict[tuple[str, str], SourceRef] = {}
        for item in ranking_items:
            self.add_operation_ref(refs, item.get("source_type"), item.get("source_id"))
        for item in recommend_items:
            if item.get("target_type") == "album":
                self.add_operation_ref(
                    refs, item.get("source_type"), item.get("source_id")
                )
        for topic in topics:
            for item in topic.get("items", []):
                self.add_operation_ref(
                    refs, item.get("source_type"), item.get("source_id")
                )
        return list(refs.values())

    def add_operation_ref(
        self,
        refs: dict[tuple[str, str], SourceRef],
        source_type: Any,
        source_id: Any,
    ) -> None:
        if source_type not in {"book", "album"} or not source_id:
            return
        source_type_text = str(source_type)
        source_id_text = str(source_id)
        refs.setdefault(
            (source_type_text, source_id_text),
            SourceRef(
                source_type_text,
                source_id_text,
                self.normalize_url(f"/{source_type_text}/{source_id_text}"),
            ),
        )

    def merge_source_refs(
        self, primary_refs: list[SourceRef], required_refs: list[SourceRef]
    ) -> list[SourceRef]:
        refs: dict[tuple[str, str], SourceRef] = {}
        for ref in primary_refs:
            refs.setdefault((ref.source_type, ref.source_id), ref)
        for ref in required_refs:
            refs.setdefault((ref.source_type, ref.source_id), ref)
        return list(refs.values())

    def collect_source_refs(
        self, start_urls: list[str], max_list_pages: int
    ) -> list[SourceRef]:
        refs: dict[tuple[str, str], SourceRef] = {}
        queue: list[str] = [self.normalize_url(url) for url in start_urls]
        visited: set[str] = set()

        while queue and len(visited) < max_list_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            logger.info(
                "fetch list page: %s/%s refs=%s queue=%s url=%s",
                len(visited),
                max_list_pages,
                len(refs),
                len(queue),
                url,
            )

            page_html = self.fetch_text(url)
            self.discovered_categories.update(self.parse_category_refs(url, page_html))
            for ref in self.parse_source_refs(page_html):
                refs.setdefault((ref.source_type, ref.source_id), ref)

            for next_url in self.parse_next_list_urls(page_html):
                normalized = self.normalize_url(next_url)
                if normalized not in visited and normalized not in queue:
                    queue.append(normalized)

        return list(refs.values())

    def enrich_narrators(self, narrators: dict[str, dict[str, Any]]) -> None:
        total = len(narrators)
        for index, narrator in enumerate(narrators.values(), start=1):
            source_url = narrator.get("source_url")
            if not source_url:
                continue
            if index == 1 or index % 20 == 0 or index == total:
                logger.info("fetch narrator profile: %s/%s %s", index, total, source_url)
            try:
                profile_html = self.fetch_text(str(source_url))
            except RuntimeError as exc:
                logger.warning(str(exc))
                continue
            narrator.update(self.parse_narrator_profile(str(source_url), profile_html))

    def parse_narrator_profile(self, source_url: str, page_html: str) -> dict[str, Any]:
        source_id = self.first_match(urlparse(source_url).path, r"^/user/(\d+)")
        avatar_url = self.first_match(
            page_html,
            r'<img[^>]+class=["\'][^"\']*photo-lx[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
        )
        profile_name = self.first_match(
            page_html,
            r'<img[^>]+class=["\'][^"\']*photo-lx[^"\']*["\'][^>]+alt=["\']([^"\']+)["\']',
        )
        book_count = self.first_match(
            page_html,
            rf'href=["\']/user/{re.escape(source_id)}/book["\'][^>]*><span>(\d+)</span><br\s*/?>书籍</a>',
        )
        album_count = self.first_match(
            page_html,
            rf'href=["\']/user/{re.escape(source_id)}/album["\'][^>]*><span>(\d+)</span><br\s*/?>节目</a>',
        )
        following_count = self.first_match(
            page_html, r"<span>(\d+)</span><br\s*/?>关注</a>"
        )
        follower_count = self.first_match(
            page_html, r"<span>(\d+)</span><br\s*/?>粉丝</a>"
        )
        meta_description = self.first_match(
            page_html,
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
        )

        return {
            "profile_name": self.clean_text(profile_name),
            "avatar_url": html.unescape(avatar_url or ""),
            "book_count": self.parse_int(book_count),
            "album_count": self.parse_int(album_count),
            "following_count": self.parse_int(following_count),
            "follower_count": self.parse_int(follower_count),
            "profile_summary": self.truncate_text(
                self.clean_text(meta_description), self.summary_max_chars
            ),
        }

    def parse_category_refs(
        self, url: str, page_html: str
    ) -> dict[str, dict[str, Any]]:
        categories: dict[str, dict[str, Any]] = {}

        for category_id, name in re.findall(
            r'href=["\']/book/category/(\d+)["\'][^>]*>\s*(?:<i[^>]*></i>)?\s*([^<]+)</a>',
            page_html,
        ):
            category_name = self.clean_text(name)
            if not category_name or category_name == "全部":
                continue
            categories[f"book:{category_id}"] = {
                "source_category_id": category_id,
                "source_category_name": category_name,
                "parent_source_category_id": "",
                "parent_category_name": "",
                "category_level": 1,
                "category_type": "audiobook",
            }

        parent_category_id = self.first_match(
            urlparse(url).path, r"^/book/category/(\d+)"
        )
        parent_category_name = ""
        if parent_category_id:
            parent = categories.get(f"book:{parent_category_id}")
            parent_category_name = (
                str(parent.get("source_category_name", "")) if parent else ""
            )

        filter_block = self.first_match(
            page_html, r'<section class=["\']category-filter["\']>([\s\S]*?)</section>'
        )
        if filter_block and parent_category_id:
            for category_id, name in re.findall(
                r'href=["\']/book/category/(\d+)["\'][^>]*>([^<]+)</a>', filter_block
            ):
                category_name = self.clean_text(name)
                if (
                    not category_name
                    or category_name == "全部"
                    or category_id == parent_category_id
                ):
                    continue
                categories[f"book:{category_id}"] = {
                    "source_category_id": category_id,
                    "source_category_name": category_name,
                    "parent_source_category_id": parent_category_id,
                    "parent_category_name": parent_category_name,
                    "category_level": 2,
                    "category_type": "audiobook",
                }

        for category_id, name in re.findall(
            r'href=["\']/explore/album/category/(\d+)/[^"\']*["\'][^>]*>\s*(?:<i[^>]*></i>)?\s*([^<]+)</a>',
            page_html,
        ):
            category_name = self.clean_text(name)
            if not category_name or category_name == "全部":
                continue
            categories[f"album:{category_id}"] = {
                "source_category_id": category_id,
                "source_category_name": category_name,
                "parent_source_category_id": "",
                "parent_category_name": "",
                "category_level": 1,
                "category_type": "program",
            }

        return categories

    def parse_source_refs(self, page_html: str) -> list[SourceRef]:
        refs: list[SourceRef] = []
        page = self.selector(page_html)
        for href in sorted(
            set(
                page.css('a[href^="/book/"]::attr(href)').getall()
                + page.css('a[href^="/album/"]::attr(href)').getall()
            )
        ):
            source_id = self.first_match(href, r"^/(?:book|album)/(\d+)")
            if not source_id:
                continue
            source_type = "book" if href.startswith("/book/") else "album"
            refs.append(SourceRef(source_type, source_id, self.normalize_url(href)))
        return refs

    def parse_next_list_urls(self, page_html: str) -> list[str]:
        urls: list[str] = []
        for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>', page_html):
            if not self.is_internal_list_url(href):
                continue
            if (
                'rel="next"' in href
                or "/recommend/" in href
                or "/hot/" in href
                or "/latest/" in href
            ):
                urls.append(href)
        return urls

    def is_internal_list_url(self, href: str) -> bool:
        parsed = urlparse(urljoin(BASE_URL, href))
        if parsed.netloc != "www.lrts.me":
            return False
        path = parsed.path
        return (
            path.startswith("/book/category")
            or path.startswith("/rank/")
            or path.startswith("/explore/album")
        )

    def parse_detail_page(
        self, ref: SourceRef, page_html: str
    ) -> dict[str, Any] | None:
        title = self.first_match(page_html, r"<h1[^>]*>(.*?)</h1>")
        if not title:
            return None

        status = self.first_match(
            title, r'<i[^>]*class=["\'][^"\']*d-status[^"\']*["\'][^>]*>(.*?)</i>'
        )
        title = self.clean_text(re.sub(r"<i[^>]*>.*?</i>", "", title))
        cover_url = self.first_match(
            page_html,
            r'<div class=["\'][^"\']*d-cover[^"\']*["\'][\s\S]*?<img[^>]+src=["\']([^"\']+)["\']',
        )
        description = self.first_match(
            page_html, r'<div class=["\']d-desc f14["\'][\s\S]*?<p>([\s\S]*?)</p>'
        )
        category_name = self.first_match(
            page_html, r"<span[^>]*>类型：</span>\s*([^<\n]+)"
        )
        track_count = self.first_match(
            page_html, r"<span[^>]*>(?:章节|声音)：</span>\s*(\d+)"
        )
        size_text = self.first_match(page_html, r"<span[^>]*>大小：</span>\s*([^<]*)")
        duration_text = self.first_match(
            page_html, r"<span[^>]*>时长：</span>\s*([^<]+)"
        )
        last_update = self.first_match(
            page_html, r"<span[^>]*>最后更新：</span>\s*([^<]+)"
        )
        play_count_text = self.first_match(page_html, r"<em>\s*([^<]+?)\s*</em>\s*播放")
        meta_description = self.first_match(
            page_html,
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
        )

        authors = []
        author_block = self.first_match(
            page_html, r"<span[^>]*>原著：</span>([\s\S]*?)</li>"
        )
        if author_block:
            authors = [
                self.clean_text(x)
                for x in re.findall(r"<a[^>]*>(.*?)</a>", author_block)
            ]
            if not authors:
                authors = [self.clean_text(author_block)]

        narrators: list[dict[str, Any]] = []
        narrator_block = self.first_match(
            page_html, r"<span[^>]*>主播：</span>([\s\S]*?)</li>"
        )
        if narrator_block:
            for user_id, name in re.findall(
                r'href=["\']/user/(\d+)["\'][^>]*>(.*?)</a>', narrator_block
            ):
                narrators.append(
                    {
                        "source_narrator_id": user_id,
                        "narrator_name": self.clean_text(name),
                        "source_url": self.normalize_url(f"/user/{user_id}"),
                    }
                )
            if not narrators:
                name = self.clean_text(narrator_block)
                if name:
                    narrators.append(
                        {
                            "source_narrator_id": "",
                            "narrator_name": name,
                            "source_url": "",
                        }
                    )

        uploader = self.first_match(
            page_html,
            r"<span[^>]*>\s*上传\s*：</span><a[^>]+href=[\"']/user/(\d+)[\"'][^>]*>(.*?)</a>",
        )

        return {
            "source_type": ref.source_type,
            "source_id": ref.source_id,
            "source_url": ref.url,
            "title": title,
            "status": self.clean_text(status),
            "cover_url": html.unescape(cover_url or ""),
            "authors": authors,
            "narrators": narrators,
            "category_name": self.clean_text(category_name),
            "track_count": self.parse_int(track_count),
            "size_text": self.clean_text(size_text),
            "duration_text": self.clean_text(duration_text),
            "last_update": self.clean_text(last_update),
            "play_count_text": self.clean_text(play_count_text),
            "description": self.truncate_text(
                self.clean_text(description), self.summary_max_chars
            ),
            "meta_description": self.truncate_text(
                self.clean_text(meta_description), self.summary_max_chars
            ),
            "uploader": self.clean_text(uploader),
            "crawled_at": self.now_text(),
        }

    def collect_tracks(
        self, ref: SourceRef, detail_html: str, max_track_pages: int
    ) -> list[dict[str, Any]]:
        tracks = self.parse_tracks_from_html(ref, detail_html)
        if max_track_pages == 1:
            return tracks

        total_count = self.parse_int(
            self.first_match(detail_html, r"var totalCount='(\d+)'")
        ) or len(tracks)
        page_size = (
            self.parse_int(self.first_match(detail_html, r"pageSize='(\d+)'")) or 10
        )
        total_page_count = max(1, (total_count + page_size - 1) // page_size)
        page_count = (
            total_page_count
            if max_track_pages <= 0
            else min(max_track_pages, total_page_count)
        )
        if page_count > 1:
            logger.debug(
                "collect track pages: %s:%s total_count=%s page_size=%s pages=%s",
                ref.source_type,
                ref.source_id,
                total_count,
                page_size,
                page_count,
            )

        for page_index in range(1, page_count):
            logger.debug(
                "fetch track page: %s:%s page=%s/%s",
                ref.source_type,
                ref.source_id,
                page_index + 1,
                page_count,
            )
            if page_count > 10 and (
                page_index == 1
                or page_index % 20 == 0
                or page_index == page_count - 1
            ):
                logger.info(
                    "fetch track page: %s:%s page=%s/%s",
                    ref.source_type,
                    ref.source_id,
                    page_index + 1,
                    page_count,
                )
            ajax_url = self.normalize_url(
                f"/ajax/{ref.source_type}/{ref.source_id}/{page_index}/{page_size}"
            )
            payload = "showCover=false" if ref.source_type == "album" else None
            try:
                response_text = self.fetch_text(ajax_url, method="POST", data=payload)
            except RuntimeError as exc:
                logger.warning(str(exc))
                continue
            tracks.extend(self.parse_tracks_from_ajax(ref, response_text))

        return self.dedupe_tracks(tracks)

    def parse_tracks_from_html(
        self, ref: SourceRef, page_html: str
    ) -> list[dict[str, Any]]:
        block = self.first_match(page_html, r'<ul id=["\']pul["\']>([\s\S]*?)</ul>')
        if not block:
            return []

        tracks: list[dict[str, Any]] = []
        for item_html in re.findall(r"<li[\s\S]*?</li>", block):
            section = self.first_match(item_html, r"sections=(\d+)")
            title = self.first_match(
                item_html,
                r"<a[^>]*(?:player-info|href)[^>]*>(?!<i\b)([\s\S]*?)</a>\s*$",
            )
            if not title:
                anchors = re.findall(r"<a[^>]*>([\s\S]*?)</a>", item_html)
                title = anchors[-1] if anchors else ""
            update_date = self.first_match(
                item_html, r"<time>\s*更新时间:\s*([^<]+)</time>"
            )
            pay_type = "paid" if "pay-section" in item_html else "free"
            sound_id = self.first_match(item_html, r'href=["\']/sound/(\d+)["\']')
            tracks.append(
                {
                    "source_album_type": ref.source_type,
                    "source_album_id": ref.source_id,
                    "source_track_id": sound_id
                    or self.make_track_id(ref.source_id, section),
                    "track_no": self.parse_int(section),
                    "track_title": self.clean_text(title),
                    "pay_type": pay_type,
                    "last_update": self.clean_text(update_date),
                    "duration_seconds": None,
                    "file_size_bytes": None,
                    "play_count": None,
                    "source_url": ref.url,
                }
            )
        return [track for track in tracks if track["track_title"]]

    def parse_tracks_from_ajax(
        self, ref: SourceRef, response_text: str
    ) -> list[dict[str, Any]]:
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError:
            return []

        rows = payload.get("data", {}).get("data", [])
        tracks = []
        for row in rows:
            section = (
                row.get("section") if ref.source_type == "book" else row.get("sections")
            )
            tracks.append(
                {
                    "source_album_type": ref.source_type,
                    "source_album_id": ref.source_id,
                    "source_track_id": str(
                        row.get("resId")
                        or row.get("id")
                        or self.make_track_id(ref.source_id, section)
                    ),
                    "track_no": self.parse_int(section),
                    "track_title": self.clean_text(
                        row.get("resName") or row.get("name")
                    ),
                    "pay_type": "paid" if row.get("payType") else "free",
                    "last_update": self.clean_text(
                        row.get("lastModify") or row.get("updateTimeStr")
                    ),
                    "duration_seconds": row.get("playTime"),
                    "file_size_bytes": row.get("fileSize"),
                    "play_count": row.get("playCount"),
                    "source_url": ref.url,
                }
            )
        return [track for track in tracks if track["track_title"]]

    def dedupe_tracks(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int | None]] = set()
        for track in tracks:
            key = (
                str(track["source_album_type"]),
                str(track["source_album_id"]),
                track.get("track_no"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(track)
        return result

    def write_csv_outputs(
        self,
        albums: list[dict[str, Any]],
        tracks: list[dict[str, Any]],
        authors: dict[str, dict[str, Any]],
        narrators: dict[str, dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        organizations: list[dict[str, Any]],
        ranking_list: list[dict[str, Any]],
        ranking_items: list[dict[str, Any]],
        recommend_slots: list[dict[str, Any]],
        recommend_items: list[dict[str, Any]],
        topics: list[dict[str, Any]],
    ) -> None:
        self.write_csv(
            self.foundation_dir / "dim_audio_category.csv",
            [
                {
                    "source_category_name": item["source_category_name"],
                    "source_category_id": item.get("source_category_id", ""),
                    "category_code": self.category_code(item, index),
                    "parent_source_category_id": item.get(
                        "parent_source_category_id", ""
                    ),
                    "parent_category_name": item.get("parent_category_name", ""),
                    "category_name": item["source_category_name"],
                    "category_level": item.get("category_level", 1),
                    "category_type": item["category_type"],
                    "sort_no": index,
                    "yn": 1,
                    "source": "lrts",
                }
                for index, item in enumerate(categories.values(), start=1)
            ],
        )
        self.write_csv(
            self.foundation_dir / "dim_content_tag.csv",
            self.build_content_tags(albums, categories, topics),
        )
        self.write_csv(
            self.foundation_dir / "dim_channel.csv",
            self.build_channels(),
        )
        self.write_csv(
            self.foundation_dir / "dim_language.csv",
            self.build_languages(),
        )
        self.write_csv(
            self.foundation_dir / "dim_currency.csv",
            self.build_currencies(),
        )
        self.write_csv(
            self.foundation_dir / "content_organization.csv",
            [
                {
                    "source_organization_id": item["source_organization_id"],
                    "organization_code": f"LR_ORG_{index:06d}",
                    "organization_name": item["organization_name"],
                    "organization_type": item["organization_type"],
                    "intro": item["intro"],
                    "source_url": item["source_url"],
                    "source": item["source"],
                }
                for index, item in enumerate(organizations, start=1)
            ],
        )
        self.write_csv(
            self.content_dir / "content_author.csv",
            [
                {
                    "source_author_name": name,
                    "author_code": f"LR_AUTHOR_{index:06d}",
                    "author_name": name,
                    "author_type": item["author_type"],
                    "source": "lrts",
                }
                for index, (name, item) in enumerate(authors.items(), start=1)
            ],
        )
        self.write_csv(
            self.content_dir / "content_narrator.csv",
            [
                {
                    "source_narrator_id": item.get("source_narrator_id", ""),
                    "narrator_code": f"LR_NARRATOR_{index:06d}",
                    "narrator_name": item.get("narrator_name", ""),
                    "profile_name": item.get("profile_name", ""),
                    "avatar_url": item.get("avatar_url", ""),
                    "book_count": item.get("book_count") or "",
                    "album_count": item.get("album_count") or "",
                    "following_count": item.get("following_count") or "",
                    "follower_count": item.get("follower_count") or "",
                    "profile_summary": item.get("profile_summary", ""),
                    "source_url": item.get("source_url", ""),
                    "source": "lrts",
                }
                for index, item in enumerate(narrators.values(), start=1)
            ],
        )
        self.write_csv(
            self.content_dir / "audio_album.csv",
            [
                {
                    "source_type": album["source_type"],
                    "source_id": album["source_id"],
                    "album_code": f"LR_ALB_{index:08d}",
                    "album_title": album["title"],
                    "album_type": "program"
                    if album["source_type"] == "album"
                    else "audiobook",
                    "category_name": album.get("category_name", ""),
                    "track_count": album.get("track_count", ""),
                    "duration_text": album.get("duration_text", ""),
                    "last_update": album.get("last_update", ""),
                    "play_count_text": album.get("play_count_text", ""),
                    "cover_url": album.get("cover_url", ""),
                    "source_url": album.get("source_url", ""),
                    "summary": album.get("description")
                    or album.get("meta_description", ""),
                }
                for index, album in enumerate(albums, start=1)
            ],
        )
        self.write_csv(
            self.content_dir / "audio_track.csv",
            [
                {
                    "source_album_type": track["source_album_type"],
                    "source_album_id": track["source_album_id"],
                    "source_track_id": track["source_track_id"],
                    "track_no": track["track_no"],
                    "track_title": track["track_title"],
                    "pay_type": track["pay_type"],
                    "last_update": track["last_update"],
                    "duration_seconds": track.get("duration_seconds") or "",
                    "file_size_bytes": track.get("file_size_bytes") or "",
                    "play_count": track.get("play_count") or "",
                    "source_url": track["source_url"],
                }
                for track in tracks
            ],
        )
        self.write_csv(
            self.operation_dir / "ranking_list.csv",
            ranking_list,
        )
        self.write_csv(
            self.operation_dir / "ranking_item.csv",
            ranking_items,
        )
        self.write_csv(
            self.operation_dir / "recommend_slot.csv",
            recommend_slots,
        )
        self.write_csv(
            self.operation_dir / "recommend_item.csv",
            recommend_items,
        )
        self.write_csv(
            self.operation_dir / "content_topic.csv",
            [
                {
                    "source_topic_id": topic["source_topic_id"],
                    "topic_code": f"LR_TOPIC_{index:06d}",
                    "topic_title": topic.get("topic_title", ""),
                    "topic_type": "editorial",
                    "cover_url": topic.get("cover_url", ""),
                    "summary": topic.get("summary", ""),
                    "book_count": topic.get("book_count", ""),
                    "play_count_text": topic.get("play_count_text", ""),
                    "updated_at_text": topic.get("updated_at_text", ""),
                    "source_url": topic["source_url"],
                    "source": topic["source"],
                }
                for index, topic in enumerate(topics, start=1)
            ],
        )
        topic_items = []
        for topic_index, topic in enumerate(topics, start=1):
            topic_code = f"LR_TOPIC_{topic_index:06d}"
            for sort_no, item in enumerate(topic.get("items", []), start=1):
                topic_items.append(
                    {
                        "topic_code": topic_code,
                        "source_topic_id": topic["source_topic_id"],
                        "source_type": item["source_type"],
                        "source_id": item["source_id"],
                        "title": item["title"],
                        "sort_no": sort_no,
                        "source": topic["source"],
                    }
                )
        self.write_csv(self.operation_dir / "content_topic_item.csv", topic_items)
        self.write_csv(
            self.trade_dir / "vip_plan.csv",
            self.build_vip_plans(),
        )

    def build_channels(self) -> list[dict[str, Any]]:
        return [
            self.channel_row("LR_WEB", "官网 Web", "web", 1, "lrts"),
            self.channel_row("LR_APP", "移动 App", "app", 2, "generated"),
            self.channel_row("LR_MINI_PROGRAM", "小程序", "mini_program", 3, "generated"),
            self.channel_row("LR_VEHICLE", "车载端", "vehicle", 4, "generated"),
            self.channel_row("LR_PARTNER", "合作渠道", "partner", 5, "generated"),
        ]

    def channel_row(
        self,
        channel_code: str,
        channel_name: str,
        channel_type: str,
        sort_no: int,
        source: str,
    ) -> dict[str, Any]:
        return {
            "channel_code": channel_code,
            "channel_name": channel_name,
            "channel_type": channel_type,
            "sort_no": sort_no,
            "yn": 1,
            "source": source,
        }

    def build_languages(self) -> list[dict[str, Any]]:
        return [
            self.language_row("zh-CN", "普通话", 1),
            self.language_row("zh-HK", "粤语", 2),
            self.language_row("en", "英语", 3),
        ]

    def language_row(
        self, language_code: str, language_name: str, sort_no: int
    ) -> dict[str, Any]:
        return {
            "language_code": language_code,
            "language_name": language_name,
            "sort_no": sort_no,
            "yn": 1,
            "source": "generated",
        }

    def build_currencies(self) -> list[dict[str, Any]]:
        return [
            {
                "currency_code": "CNY",
                "currency_name": "人民币",
                "symbol": "¥",
                "precision_scale": 2,
                "yn": 1,
                "source": "generated",
            }
        ]

    def build_vip_plans(self) -> list[dict[str, Any]]:
        return [
            self.vip_plan_row("LR_VIP_MONTHLY", "VIP 月度会员", "vip", "month", 1, 19),
            self.vip_plan_row(
                "LR_VIP_QUARTERLY", "VIP 季度会员", "vip", "quarter", 3, 49
            ),
            self.vip_plan_row("LR_VIP_YEARLY", "VIP 年度会员", "vip", "year", 12, 159),
            self.vip_plan_row(
                "LR_SVIP_MONTHLY", "SVIP 月度会员", "svip", "month", 1, 29
            ),
            self.vip_plan_row(
                "LR_SVIP_YEARLY", "SVIP 年度会员", "svip", "year", 12, 229
            ),
        ]

    def vip_plan_row(
        self,
        plan_code: str,
        plan_name: str,
        plan_type: str,
        billing_cycle: str,
        duration_months: int,
        price_amount: int,
    ) -> dict[str, Any]:
        return {
            "plan_code": plan_code,
            "plan_name": plan_name,
            "plan_type": plan_type,
            "billing_cycle": billing_cycle,
            "duration_months": duration_months,
            "currency_code": "CNY",
            "price_amount": f"{price_amount:.2f}",
            "yn": 1,
            "source": "generated",
        }

    def build_content_tags(
        self,
        albums: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        topics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = [
            self.content_tag_row(
                "LR_TAG_GROUP_GENRE", "", "题材", "题材", "genre", 1, "system"
            ),
            self.content_tag_row(
                "LR_TAG_GROUP_STYLE", "", "风格", "风格", "style", 2, "system"
            ),
            self.content_tag_row(
                "LR_TAG_GROUP_TOPIC", "", "专题主题", "专题主题", "topic", 3, "system"
            ),
        ]

        seen = {row["tag_code"] for row in rows}
        sort_no = len(rows)
        for item in categories.values():
            tag_name = self.clean_text(item.get("source_category_name"))
            if not tag_name:
                continue
            tag_code = f"LR_TAG_GENRE_{self.slug_text(tag_name).upper()}"
            if tag_code in seen:
                continue
            sort_no += 1
            rows.append(
                self.content_tag_row(
                    tag_code,
                    "LR_TAG_GROUP_GENRE",
                    tag_name,
                    tag_name,
                    "genre",
                    sort_no,
                    "lrts",
                )
            )
            seen.add(tag_code)

        for tag_name in self.extract_style_tags(albums):
            tag_code = f"LR_TAG_STYLE_{self.slug_text(tag_name).upper()}"
            if tag_code in seen:
                continue
            sort_no += 1
            rows.append(
                self.content_tag_row(
                    tag_code,
                    "LR_TAG_GROUP_STYLE",
                    tag_name,
                    tag_name,
                    "style",
                    sort_no,
                    "lrts",
                )
            )
            seen.add(tag_code)

        for topic in topics:
            tag_name = self.clean_text(topic.get("topic_title"))
            if not tag_name:
                continue
            tag_code = f"LR_TAG_TOPIC_{self.slug_text(tag_name).upper()}"
            if tag_code in seen:
                continue
            sort_no += 1
            rows.append(
                self.content_tag_row(
                    tag_code,
                    "LR_TAG_GROUP_TOPIC",
                    tag_name,
                    tag_name,
                    "topic",
                    sort_no,
                    "lrts",
                )
            )
            seen.add(tag_code)

        return rows

    def content_tag_row(
        self,
        tag_code: str,
        parent_tag_code: str,
        source_tag_name: str,
        tag_name: str,
        tag_type: str,
        sort_no: int,
        source: str,
    ) -> dict[str, Any]:
        return {
            "source_tag_name": source_tag_name,
            "tag_code": tag_code,
            "parent_tag_code": parent_tag_code,
            "tag_name": tag_name,
            "tag_type": tag_type,
            "sort_no": sort_no,
            "yn": 1,
            "source": source,
        }

    def extract_style_tags(self, albums: list[dict[str, Any]]) -> list[str]:
        tags: dict[str, int] = {}
        stop_words = {
            "有声书",
            "有声剧",
            "精品",
            "多人",
            "全集",
            "合集",
            "上架",
            "完结",
            "免费",
            "懒人听书",
        }
        for album in albums:
            title = self.clean_text(album.get("title"))
            for token in re.split(r"[|｜/／+＋【】\[\]（）()·,，:：;；\s]+", title):
                token = token.strip("-_")
                if len(token) < 2 or len(token) > 12:
                    continue
                if token in stop_words or token.isdigit():
                    continue
                tags[token] = tags.get(token, 0) + 1
        return [
            name
            for name, count in sorted(
                tags.items(), key=lambda item: (-item[1], item[0])
            )
            if count >= 2
        ][:80]

    def fetch_text(
        self, url: str, *, method: str = "GET", data: str | None = None
    ) -> str:
        normalized_url = self.normalize_url(url)
        cache_path = self.cache_path(normalized_url, method, data)
        if cache_path.exists() and not self.refresh_cache:
            logger.debug("cache hit: %s %s", method, normalized_url)
            return cache_path.read_text(encoding="utf-8")

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Referer": BASE_URL,
        }
        if method == "POST":
            headers["X-Requested-With"] = "XMLHttpRequest"
            if data is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        last_error: Exception | None = None
        for attempt in range(1, 4):
            self.wait_for_slot()
            logger.debug("fetch: attempt=%s method=%s url=%s", attempt, method, normalized_url)
            try:
                if method == "POST":
                    response = self.http.post(
                        normalized_url,
                        data=data or "",
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                else:
                    response = self.http.get(
                        normalized_url,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                raw = response.content
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(self.delay_seconds * attempt)
        else:
            raise RuntimeError(
                f"fetch failed: {method} {normalized_url}: {last_error}"
            ) from last_error

        text = raw.decode("utf-8", errors="replace")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
        return text

    def cache_path(self, url: str, method: str, data: str | None) -> Path:
        key = f"{method}:{url}:{data or ''}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        suffix = "json" if "/ajax/" in url else "html"
        return self.page_cache_dir / f"{digest}.{suffix}"

    def wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self.last_request_at = time.monotonic()

    def normalize_url(self, url: str) -> str:
        return urljoin(BASE_URL, url)

    def selector(self, page_html: str) -> Selector:
        return Selector(page_html)

    def _ensure_dirs(self) -> None:
        for path in [
            self.page_cache_dir,
            self.json_dir,
            self.foundation_dir,
            self.content_dir,
            self.trade_dir,
            self.operation_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def first_match(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else ""

    def clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = html.unescape(str(value))
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def parse_int(self, value: Any) -> int | None:
        if value is None:
            return None
        text = re.sub(r"[^\d]", "", str(value))
        return int(text) if text else None

    def make_track_id(self, album_id: str, section: Any) -> str:
        return f"{album_id}_{section or 'unknown'}"

    def truncate_text(self, value: str, max_chars: int) -> str:
        if max_chars <= 0 or len(value) <= max_chars:
            return value
        return value[:max_chars].rstrip() + "..."

    def category_code(self, item: dict[str, Any], index: int) -> str:
        category_id = item.get("source_category_id")
        if category_id:
            prefix = "LR_PCAT" if item.get("category_type") == "program" else "LR_CAT"
            return f"{prefix}_{category_id}"
        return f"LR_CAT_{index:04d}"

    def slug_text(self, value: str) -> str:
        text = self.clean_text(value).lower()
        text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        if len(text) <= 24:
            return text
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"{text[:16]}_{digest}"

    def now_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl public lrts.me metadata for audio-data seeds."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "audio-data",
        help="audio-data project root that receives generated seed files.",
    )
    parser.add_argument("--max-list-pages", type=int, default=3)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument(
        "--max-track-pages", type=int, default=2, help="0 means crawl all track pages."
    )
    parser.add_argument("--max-topic-pages", type=int, default=5)
    parser.add_argument(
        "--max-operation-refs",
        type=int,
        default=300,
        help="-1 means crawl every album referenced by operation seeds.",
    )
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--summary-max-chars", type=int, default=240)
    parser.add_argument("--skip-narrator-pages", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument("--start-url", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    crawler = LrtsCrawler(
        args.output_root,
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
        refresh_cache=args.refresh_cache,
        summary_max_chars=args.summary_max_chars,
    )
    start_urls = args.start_url or DEFAULT_START_URLS
    summary = crawler.run(
        start_urls=start_urls,
        max_list_pages=args.max_list_pages,
        max_items=args.max_items,
        max_track_pages=args.max_track_pages,
        max_topic_pages=args.max_topic_pages,
        max_operation_refs=args.max_operation_refs,
        crawl_narrator_pages=not args.skip_narrator_pages,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
