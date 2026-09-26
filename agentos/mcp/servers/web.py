"""
Web Search & Retrieval MCP Server.

Performs real network operations:
  - web_search hits DuckDuckGo's HTML endpoint and parses organic results.
  - web_fetch does a real HTTP GET with size/time limits and HTML->text.

Both degrade gracefully: on network failure they return a structured error
result (not fabricated content) so the failure detector can react.
"""

from typing import Dict, Any, List, Optional
import html
import re
import httpx

from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.config import settings


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
_MAX_FETCH_BYTES = 2_000_000  # cap downloaded body at ~2 MB
_MAX_TEXT_CHARS = 8000        # cap extracted text returned to the agent


class WebMCPServer(BaseMCPServer):
    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(name="web_mcp")
        self.timeout = timeout_seconds if timeout_seconds is not None else 10.0

    # ------------------------------------------------------------------ #
    # web_search
    # ------------------------------------------------------------------ #
    def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search the web via DuckDuckGo's HTML endpoint and parse results."""
        q = (query or "").strip()
        if not q:
            raise ValueError("Search query cannot be empty.")

        max_results = max(1, min(int(max_results or 5), 10))

        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": _UA}) as client:
                resp = client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": q},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                results = self._parse_ddg_results(resp.text, max_results)
        except Exception as e:
            # Real failure — report it honestly so callers/self-healing react.
            return {
                "query": q,
                "total_results": 0,
                "results": [],
                "error": f"Web search failed: {e}",
            }

        return {
            "query": q,
            "total_results": len(results),
            "results": results,
        }

    @staticmethod
    def _parse_ddg_results(page: str, max_results: int) -> List[Dict[str, str]]:
        """Extract organic results from DuckDuckGo HTML output."""
        results: List[Dict[str, str]] = []

        # Result titles/links live in <a class="result__a" href="...">title</a>
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        # Snippets live in <a class="result__snippet">...</a>
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        links = link_pattern.findall(page)
        snippets = snippet_pattern.findall(page)

        for i, (url, title) in enumerate(links):
            if len(results) >= max_results:
                break
            snippet = snippets[i] if i < len(snippets) else ""
            results.append(
                {
                    "title": WebMCPServer._strip_html(title),
                    "url": WebMCPServer._clean_ddg_url(url),
                    "snippet": WebMCPServer._strip_html(snippet),
                }
            )
        return results

    @staticmethod
    def _clean_ddg_url(url: str) -> str:
        """DuckDuckGo wraps target URLs in a redirect; extract the real one."""
        m = re.search(r"[?&]uddg=([^&]+)", url)
        if m:
            from urllib.parse import unquote

            return unquote(m.group(1))
        if url.startswith("//"):
            return "https:" + url
        return url

    # ------------------------------------------------------------------ #
    # web_fetch
    # ------------------------------------------------------------------ #
    def web_fetch(self, url: str) -> Dict[str, Any]:
        """Fetch a URL over HTTP and return cleaned text, with limits."""
        target = (url or "").strip()
        if not target:
            raise ValueError("URL cannot be empty.")
        if not target.lower().startswith(("http://", "https://")):
            target = "https://" + target

        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": _UA}) as client:
                with client.stream("GET", target, follow_redirects=True) as resp:
                    status = resp.status_code
                    ctype = resp.headers.get("content-type", "")
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) >= _MAX_FETCH_BYTES:
                            break
                    raw = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
        except Exception as e:
            return {
                "url": target,
                "status_code": 0,
                "error": f"Failed to fetch URL: {e}",
                "content": "",
            }

        title = self._extract_title(raw)
        if "html" in ctype.lower() or "<html" in raw[:2000].lower():
            content = self._html_to_text(raw)
        else:
            content = re.sub(r"\s+", " ", raw).strip()

        return {
            "url": target,
            "status_code": status,
            "content_type": ctype,
            "title": title,
            "content": content[:_MAX_TEXT_CHARS],
            "truncated": len(content) > _MAX_TEXT_CHARS,
        }

    @staticmethod
    def _extract_title(page: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
        return WebMCPServer._strip_html(m.group(1)) if m else ""

    @staticmethod
    def _html_to_text(page: str) -> str:
        """Strip scripts/styles/tags and collapse whitespace."""
        page = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.IGNORECASE | re.DOTALL)
        page = re.sub(r"<[^>]+>", " ", page)
        page = html.unescape(page)
        return re.sub(r"\s+", " ", page).strip()

    @staticmethod
    def _strip_html(fragment: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", fragment or "")).strip()

    # ------------------------------------------------------------------ #
    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="web_search",
            description="Search the web for queries, research topics, and technical documentation.",
            category="web",
            risk_level="LOW",
            parameters={
                "query": ToolParameter(name="query", type="string", description="Search query string"),
                "max_results": ToolParameter(name="max_results", type="integer", description="Maximum number of items to return", required=False, default=5),
            },
            handler=self.web_search,
        ))

        registry.register(ToolDefinition(
            name="web_fetch",
            description="Fetch page text and documentation content from a specific URL.",
            category="web",
            risk_level="LOW",
            parameters={
                "url": ToolParameter(name="url", type="string", description="URL to fetch content from"),
            },
            handler=self.web_fetch,
        ))
