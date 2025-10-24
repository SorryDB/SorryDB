import json
import os
import re
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from langchain_core.tools import tool
import logging
import sys
import os
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool
from tavily import TavilyClient


def setup_logger(name: str = None, level: str = "INFO") -> logging.Logger:
    """
    Set up a logger with rich formatting that shows file, line, and function.

    Args:
        name: Logger name (defaults to root logger)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)

        # Create formatter with file, function, and line info
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(message)s",  # noqa: E501
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Set formatter
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        # Set level
        logger.setLevel(getattr(logging, level.upper()))

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get or create a logger with the standard configuration.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    if name is None:
        # Get the caller's module name
        import inspect

        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "ax_agent"

    return setup_logger(name)


logger = get_logger(__name__)


def format_lean_errors(error_output: str, file_path: str, file_content: str) -> str:
    """Format Lean compiler errors with code context (only for errors, not warnings)."""
    lines = file_content.splitlines()
    pattern = re.compile(rf"{re.escape(str(file_path))}:(\d+):(\d+):\s*(.*)")
    formatted = []

    for error_line in error_output.splitlines():
        match = pattern.match(error_line)
        if match:
            line_num = int(match.group(1))
            col_num = int(match.group(2))
            msg = match.group(3)

            # Only format errors, not warnings
            if "error:" in msg.lower():
                if 0 < line_num <= len(lines):
                    code = lines[line_num - 1]
                    marker = " " * (col_num - 1) + "^^^"

                    formatted.extend(
                        [
                            f"\n╭─ Error at line {line_num}:{col_num}",
                            f"│  {code}",
                            f"│  {marker}",
                            f"╰─ {msg}",
                        ]
                    )
                    continue

        formatted.append(error_line)

    return "\n".join(formatted)


def trim_warnings(output: str) -> str:
    """Remove warning lines from Lean compiler output.

    Filters out common warnings like:
    - declaration uses 'sorry'
    - unused variables
    - other warning messages

    Args:
        output: Raw Lean compiler output

    Returns:
        Output with warning lines removed
    """
    filtered_lines = []
    for line in output.splitlines():
        # Skip lines containing common warnings
        if any(
            warning in line.lower()
            for warning in [
                "warning:",
                "declaration uses 'sorry'",
                "uses sorry",
                "unused variable",
                "unused parameter",
            ]
        ):
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def read_file(base_folder: str, file_path: str) -> str:
    """Read a file's content.

    Args:
        base_folder: Base folder path
        file_path: Path to file relative to base_folder

    Returns:
        File content or directory listing if path is a directory
    """
    try:
        full_path = Path(base_folder) / file_path
        if not full_path.exists():
            return ""

        # Check if it's a directory
        if full_path.is_dir():
            files = sorted([f.name for f in full_path.iterdir()])
            return f"[Directory: {file_path}]\nContents:\n" + "\n".join(
                f"  - {f}" for f in files
            )

        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return f"Error reading file: {e}"


def read_file_with_context(
    base_folder: str,
    file_path: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
    context_lines: int = 10,
) -> str:
    """Read a file with a window around a specific location, highlighting the target range.

    Args:
        base_folder: Base folder path
        file_path: Path to file relative to base_folder
        start_line: Starting line number (1-indexed)
        start_column: Starting column number (0-indexed)
        end_line: Ending line number (1-indexed)
        end_column: Ending column number (0-indexed)
        context_lines: Number of lines to show before and after the target location

    Returns:
        File content with context window and highlighted target location
    """
    try:
        full_path = Path(base_folder) / file_path
        if not full_path.exists():
            return f"File not found: {file_path}"

        if full_path.is_dir():
            return f"Path is a directory: {file_path}"

        content = full_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Calculate window boundaries
        window_start = max(1, start_line - context_lines)
        window_end = min(len(lines), end_line + context_lines)

        # Build output with highlighting
        result = [f"File: {file_path}"]
        result.append(f"Showing lines {window_start}-{window_end}")
        result.append("=" * 80)

        for line_num in range(window_start, window_end + 1):
            line_content = lines[line_num - 1] if line_num <= len(lines) else ""

            # Check if this line contains the target
            if start_line <= line_num <= end_line:
                # Highlight the target by wrapping it with markers
                if start_line == end_line:
                    # Single line - wrap the target text
                    highlighted = (
                        line_content[:start_column]
                        + "<<<TARGET>>> "
                        + line_content[start_column:end_column]
                        + " <<<END>>>"
                        + line_content[end_column:]
                    )
                    result.append(f">>> {highlighted}")
                else:
                    # Multi-line range
                    if line_num == start_line:
                        highlighted = (
                            line_content[:start_column]
                            + "<<<TARGET>>> "
                            + line_content[start_column:]
                        )
                        result.append(f">>> {highlighted}")
                    elif line_num == end_line:
                        highlighted = (
                            line_content[:end_column]
                            + " <<<END>>>"
                            + line_content[end_column:]
                        )
                        result.append(f">>> {highlighted}")
                    else:
                        result.append(f">>> {line_content}")
            else:
                # Regular line
                result.append(f"    {line_content}")

        result.append("=" * 80)
        return "\n".join(result)

    except Exception as e:
        logger.error(f"Error reading file with context {file_path}: {e}")
        return f"Error reading file with context: {e}"


def create_read_lean_file_tool(repo_path: str):
    """Create a tool for reading Lean files from a repository.

    Args:
        repo_path: Base path to the repository

    Returns:
        Tool for reading Lean files
    """

    @tool
    def read_lean_file(file_path: str) -> str:
        """
        Read a Lean file from the repository to understand context.

        Args:
            file_path: Path to the Lean file relative to repository root

        Returns:
            Content of the file
        """
        return read_file(repo_path, file_path)

    return read_lean_file


def create_read_lean_file_around_location_tool(repo_path: str):
    """Create a tool for reading Lean files with context around a location.

    Args:
        repo_path: Base path to the repository

    Returns:
        Tool for reading Lean files with context
    """

    @tool
    def read_lean_file_around_location(
        file_path: str,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int,
        context_lines: int = 10,
    ) -> str:
        """
        Read a Lean file with a context window around a specific location.
        Shows surrounding code with the target location highlighted using >>> markers.

        Args:
            file_path: Path to the Lean file relative to repository root
            start_line: Starting line number (1-indexed)
            start_column: Starting column number (0-indexed)
            end_line: Ending line number (1-indexed)
            end_column: Ending column number (0-indexed)
            context_lines: Number of lines to show before and after (default: 10)

        Returns:
            File content window with highlighted target location
        """
        return read_file_with_context(
            repo_path,
            file_path,
            start_line,
            start_column,
            end_line,
            end_column,
            context_lines,
        )

    return read_lean_file_around_location


def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the web and return formatted results for LLM consumption.

    Args:
        query: Search query string
        max_results: Maximum number of results (default 5)

    Returns:
        Formatted string with search results or error message
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        error_msg = "TAVILY_API_KEY not found in environment variables"
        logger.error(error_msg)
        return f"Error: {error_msg}"

    try:
        # Use Tavily directly
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=query,
            max_results=max_results,
            include_answer=True,
            search_depth="advanced",
        )

        results = response.get("results", [])
        logger.info(f"Searched for '{query}', found {len(results)} results")

        # Format results for LLM
        parts = []

        # Add AI-generated answer if available
        if answer := response.get("answer"):
            parts.append(f"Summary: {answer}\n")

        # Add search results
        if results:
            parts.append("Results:")
            for i, result in enumerate(results, 1):
                if result.get("title"):  # Skip answer-only entries
                    parts.append(f"\n{i}. {result['title']}")
                    parts.append(f"   URL: {result.get('url', '')}")
                    if content := result.get("content"):
                        # Truncate long content
                        if len(content) > 3000:
                            content = content[:3000] + "..."
                        parts.append(f"   {content}")

        return "\n".join(parts) if parts else "No results found"

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Search failed: {str(e)}"


@tool
def web_search_tool(query: str) -> str:
    """Search the web for mathematical concepts, definitions, or examples.

    Use this when you need:
    - Real-world context or applications
    - Mathematical definitions not in Lean yet
    - Examples or counterexamples
    - Background on unfamiliar concepts
    """
    return search_web(query, max_results=3)


def search_wikipedia(query: str, max_results: int = 3, max_chars: int = 4000) -> str:
    """
    Search Wikipedia for information on a given topic.

    Args:
        query: Search query string
        max_results: Maximum number of Wikipedia pages to return (default 3)
        max_chars: Maximum characters to return per document (default 4000)

    Returns:
        Formatted string with Wikipedia content or error message
    """
    try:
        # Configure and run Wikipedia search
        wiki_wrapper = WikipediaAPIWrapper(
            top_k_results=max_results, doc_content_chars_max=max_chars
        )

        wiki_tool = WikipediaQueryRun(api_wrapper=wiki_wrapper)

        result = wiki_tool.run(query)
        logger.info(f"Searched Wikipedia for '{query}'")

        return result if result else f"No Wikipedia results found for: {query}"

    except Exception as e:
        logger.error(f"Wikipedia search failed: {e}")
        return f"Wikipedia search failed: {str(e)}"


@tool
def wikipedia_search_tool(query: str) -> str:
    """Search Wikipedia for detailed mathematical definitions and concepts.

    Use this for:
    - Formal mathematical definitions
    - Historical context and development
    - Comprehensive explanations with examples
    - Standard notation and terminology
    """
    return search_wikipedia(query, max_results=2)




def loogle(query: str, max_results: int = 10) -> str:
    """
    Search Lean 4/Mathlib definitions using Loogle.

    Examples:
        loogle("List.map")           # Find List.map
        loogle("_ * (_ ^ _)")        # Find patterns with multiplication and power
        loogle("Real.sin, tsum")     # Multiple filters (AND)

    Args:
        query: Search pattern, constant name, or substring
        max_results: Max results to show (default 10)

    Returns:
        Formatted search results or error message
    """
    try:
        # Create SSL context that doesn't verify certificates (for development)
        # TODO: In production, you should properly configure certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Call Loogle API
        url = f"https://loogle.lean-lang.org/json?q={urllib.parse.quote(query)}"
        with urllib.request.urlopen(url, timeout=10, context=ssl_context) as response:
            data = json.loads(response.read())

        if "error" in data:
            # If errors: we need to add "" to make it search a string (no keyword found)
            url = f'https://loogle.lean-lang.org/json?q="{urllib.parse.quote(query)}"'
            with urllib.request.urlopen(url, timeout=10, context=ssl_context) as response:
                data = json.loads(response.read())

        if not data.get("hits"):
            logger.info(f"Loogle: No results for '{query}'")
            return f"No results found for: {query}. Don't try this query again, it will not work."

        # Format results
        count = data.get("count", 0)
        hits = data["hits"][:max_results]
        logger.info(f"Loogle: Found {count} results for '{query}', returning {len(hits)}")

        results = [f"Found {count} results (showing {len(hits)}):\n"]

        for hit in hits:
            name = hit.get("name", "?")
            module = hit.get("module", "")
            type_sig = hit.get("type", "").strip().removeprefix(":")

            result = f"• {name}"
            if module:
                result += f" ({module})"
            if type_sig:
                result += f"\n  {type_sig}"

            results.append(result)

        return "\n\n".join(results)

    except Exception as e:
        logger.error(f"Loogle error: {e}")
        return f"Search failed: {str(e)}"


@tool
def search_loogle_tool(query: str) -> str:
    """Search for Lean definitions, theorems, and patterns using Loogle.

    IMPORTANT: Loogle uses EXACT pattern matching for names!
    - Use exact names: 'List.map' (not 'list.map' or 'map')
    - For substrings, use quotes: '"continuous"' finds names containing 'continuous'
    - For patterns: '_ * (_ ^ _)' finds multiplication with power
    - Multiple filters: 'Real.sin, continuous' (comma-separated)

    DO NOT RETRY FAILED QUERIES! If a query returns no results:
    - Try a different search strategy (e.g., substring with quotes)
    - Try simpler/broader terms
    - Try searching for related concepts
    But never repeat the same query - it won't suddenly work!

    Examples:
    - 'Real.exp' - finds exactly Real.exp
    - '"exp"' - finds all names containing 'exp'
    - 'Continuous.comp' - finds exactly this function
    - '_ → _ → _' - finds functions with two arguments
    """
    return loogle(query, max_results=5)


def lean_explore(query: str, max_results: int = 5) -> str:
    """
    Semantic search for Lean 4/Mathlib using LeanExplore.

    Unlike Loogle (exact pattern matching), LeanExplore uses semantic search
    to find conceptually related definitions and theorems.

    Args:
        query: Natural language description of what you're looking for
        max_results: Maximum results to return

    Returns:
        Formatted search results or error message
    """

    try:
        api_key = os.environ.get("LEAN_EXPLORE_API_KEY")
        if not api_key:
            return "LeanExplore API key not found. Set LEAN_EXPLORE_API_KEY environment variable."

        # Create SSL context that doesn't verify certificates (for development)
        # TODO: In production, you should properly configure certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # API request
        url = f"https://www.leanexplore.com/api/v1/search?{urllib.parse.urlencode({'q': query})}"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})

        with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
            items = json.loads(response.read()).get("results", [])[:max_results]

        if not items:
            logger.info(f"LeanExplore: No results for '{query}'")
            return f"No results found for: {query}"

        logger.info(f"LeanExplore: Found {len(items)} results for '{query}'")

        # Format results
        results = [f"Found {len(items)} semantic matches:\n"]
        for item in items:
            # Extract primary declaration name
            primary = item.get("primary_declaration", {})
            name = primary.get("lean_name", item.get("display_statement_text", "?"))[:80]

            # Get source info
            source = item.get("source_file", "")
            line = item.get("range_start_line", "")

            # Get statement/docstring
            statement = item.get("statement_text", "")
            docstring = item.get("docstring", "")

            result = f"• {name}"
            if source:
                result += f" ({source}:{line})"
            if docstring:
                result += f"\n  {docstring.strip()}"
            if statement:
                result += f"\n  {statement}..."

            results.append(result)

        return "\n\n".join(results)

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "Invalid LeanExplore API key"
        logger.error(f"LeanExplore HTTP error {e.code}")
        return f"Search failed: HTTP {e.code}"
    except Exception as e:
        logger.error(f"LeanExplore error: {e}")
        return f"Search failed: {str(e)}"


def lean_search(query: str, max_results: int = 6) -> str:
    """
    Search for Lean 4/Mathlib theorems and definitions using LeanSearch.

    Args:
        query: Module path OR natural language description
               Examples: "Mathlib.Analysis.InnerProductSpace.Adjoint" or "continuity of functions"
        max_results: Maximum results to return

    Returns:
        Formatted search results
    """
    # Create SSL context that doesn't verify certificates (for development)
    # TODO: In production, you should properly configure certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    url = "https://leansearch.net/search"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ax-agent",
    }
    # API expects a list even for single query
    data = json.dumps({"query": [query], "num_results": max_results}).encode("utf-8")

    # Retry logic for rate limiting
    max_retries = 3
    result_data = None

    for attempt in range(max_retries):
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
                result_data = json.loads(response.read())
                break

        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                # Rate limited - wait before retry
                wait_time = 2
                logger.warning(
                    f"LeanSearch rate limited for '{query}'. Waiting {wait_time}s before retry"
                )
                time.sleep(wait_time)
                continue
            elif e.code == 429:
                logger.error(f"LeanSearch rate limited after all retries for '{query}'")
                return "LeanSearch rate limited. Please try again later."
            else:
                logger.error(f"LeanSearch HTTP error {e.code} for '{query}': {e.reason}")
                return f"LeanSearch failed: HTTP {e.code} - {e.reason}"
        except Exception as e:
            logger.error(f"LeanSearch error for '{query}': {e}")
            return f"LeanSearch failed: {str(e)}"

    # Process the response (only once, after successful request)
    if not result_data or not result_data[0]:  # result_data is a list with one element
        logger.info(f"LeanSearch: No results for '{query}'")
        return f"No results found for: {query}"

    # Get the results for our single query
    matches = result_data[0]
    logger.info(f"LeanSearch: Found {len(matches)} matches for '{query}'")

    # Format results
    output = [f"=== {query} ({len(matches)} matches) ==="]

    for item in matches[:max_results]:
        result = item.get("result", {})

        # Get name and signature
        name = ".".join(result.get("name", ["Unknown"]))
        kind = result.get("kind", "")
        signature = result.get("signature", "")
        docstring = result.get("docstring", "")

        output.append(f"\n• {name} [{kind}]")
        if signature:
            output.append(f"  {signature}")
        if docstring:
            output.append(f"  Doc: {docstring.strip()[:3000]}")

    return "\n".join(output)


@tool
def search_lean_search_tool(query: str) -> str:
    """Search for Lean theorems using module paths or natural language.

    LeanSearch accepts both precise module paths and natural language descriptions.

    Examples of module paths:
    - "Mathlib.Analysis.InnerProductSpace.Adjoint"
    - "Mathlib.Topology.Basic"
    - "Mathlib.Data.Real.Basic"

    Examples of natural language:
    - "continuity of functions"
    - "prime number theorems"
    - "adjoint operators in Hilbert spaces"
    """
    if not query.strip():
        return "Please provide a module path or search query"
    return lean_search(query.strip(), max_results=6)


@tool
def search_lean_explore_tool(query: str) -> str:
    """Semantic search for Lean concepts using natural language.

    Use this for conceptual searches when you don't know exact names:
    - 'functions about continuity' - finds continuity-related theorems
    - 'lemmas about prime numbers' - finds prime number results
    - 'topology on metric spaces' - finds metric space theorems

    Unlike Loogle (exact matching), this uses AI to find semantically related content.
    Great for initial exploration before using Loogle for specific lookups.
    """
    return lean_explore(query, max_results=5)
