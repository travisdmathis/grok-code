"""Web tools: WebFetch and WebSearch"""

import re
from urllib.parse import urlparse

import httpx

from .base import Tool


class WebFetchTool(Tool):
    """Tool for fetching web content"""

    def __init__(self):
        self._client = None

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return """Fetch content from a URL and extract information. Use this to:
- Read documentation pages
- Fetch API responses
- Get content from public web pages

Note: Won't work for authenticated pages (login required)."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "prompt": {
                    "type": "string",
                    "description": "What information to extract from the page",
                },
            },
            "required": ["url", "prompt"],
        }

    async def execute(self, url: str, prompt: str) -> str:
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                url = "https://" + url
                parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return f"Error: Invalid URL scheme: {parsed.scheme}"
        except Exception as e:
            return f"Error: Invalid URL: {e}"

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": "grokCode/1.0"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if "application/json" in content_type:
                    # Return JSON as-is
                    text = response.text
                elif "text/html" in content_type:
                    # Extract text from HTML
                    text = self._html_to_text(response.text)
                else:
                    text = response.text

                # Truncate if too long
                max_chars = 50000
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n\n... (truncated)"

                return f"Content from {url}:\n\n{text}\n\n---\nUser prompt: {prompt}"

        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} - {e.response.reason_phrase}"
        except httpx.RequestError as e:
            return f"Error fetching URL: {e}"
        except Exception as e:
            return f"Error: {e}"

    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion"""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert some elements to text equivalents
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</?p[^>]*>", "\n\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</?div[^>]*>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.IGNORECASE)
        html = re.sub(r"<h[1-6][^>]*>", "\n\n## ", html, flags=re.IGNORECASE)
        html = re.sub(r"</h[1-6]>", "\n", html, flags=re.IGNORECASE)

        # Remove remaining tags
        html = re.sub(r"<[^>]+>", "", html)

        # Decode HTML entities
        html = html.replace("&nbsp;", " ")
        html = html.replace("&amp;", "&")
        html = html.replace("&lt;", "<")
        html = html.replace("&gt;", ">")
        html = html.replace("&quot;", '"')
        html = html.replace("&#39;", "'")

        # Clean up whitespace
        lines = [line.strip() for line in html.split("\n")]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        # Remove excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()


class WebSearchTool(Tool):
    """Tool for web search (using DuckDuckGo)"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return """Search the web for information. Returns search results with titles, URLs, and snippets.
Use for finding documentation, solutions, or current information."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5, max 10)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5) -> str:
        max_results = min(max_results, 10)

        try:
            # Use DuckDuckGo HTML search (no API key needed)
            async with httpx.AsyncClient(
                timeout=15.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; grokCode/1.0)",
                },
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                )
                response.raise_for_status()

                results = self._parse_ddg_results(response.text, max_results)

                if not results:
                    return f"No search results found for: {query}"

                output = [f"Search results for: {query}\n"]
                for i, result in enumerate(results, 1):
                    output.append(f"{i}. {result['title']}")
                    output.append(f"   URL: {result['url']}")
                    if result.get("snippet"):
                        output.append(f"   {result['snippet']}")
                    output.append("")

                return "\n".join(output)

        except Exception as e:
            return f"Error performing search: {e}"

    def _parse_ddg_results(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo HTML results"""
        results = []

        # Find result blocks
        result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
        snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+)</a>'

        matches = re.findall(result_pattern, html)
        snippets = re.findall(snippet_pattern, html)

        for i, (url, title) in enumerate(matches[:max_results]):
            result = {
                "title": title.strip(),
                "url": url,
                "snippet": snippets[i].strip() if i < len(snippets) else "",
            }
            # Clean up DuckDuckGo redirect URLs
            if "uddg=" in url:
                try:
                    from urllib.parse import unquote, parse_qs
                    parsed = parse_qs(urlparse(url).query)
                    if "uddg" in parsed:
                        result["url"] = unquote(parsed["uddg"][0])
                except:
                    pass
            results.append(result)

        return results
