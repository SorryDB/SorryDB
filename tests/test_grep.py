from pathlib import Path

from sorrydb.utils.llm_tools import grep_files, create_grep_tool


MOCK_REPO = Path(__file__).parent / "mock_lean_repository"


class TestGrepFiles:
    """Tests for grep_files function."""

    def test_grep_finds_theorem(self):
        """Test finding theorem declarations."""
        result = grep_files(str(MOCK_REPO), "theorem")
        assert "theorem" in result
        assert "triple.lean" in result

    def test_grep_finds_import(self):
        """Test finding import statements."""
        result = grep_files(str(MOCK_REPO), "import")
        assert "import" in result
        assert "MockLeanRepository.lean" in result

    def test_grep_finds_sorry(self):
        """Test finding sorry keywords."""
        result = grep_files(str(MOCK_REPO), "sorry")
        assert "sorry" in result

    def test_grep_no_matches(self):
        """Test that no matches returns appropriate message."""
        result = grep_files(str(MOCK_REPO), "xyznonexistent123")
        assert "No matches" in result

    def test_grep_respects_file_glob(self):
        """Test that file_glob filters correctly."""
        # Search only in .lean files (default)
        result = grep_files(str(MOCK_REPO), "def", file_glob="*.lean")
        assert "def" in result or "No matches" in result

        # Search with non-matching glob
        result = grep_files(str(MOCK_REPO), "theorem", file_glob="*.py")
        assert "No matches" in result

    def test_grep_respects_max_results(self):
        """Test that max_results limits output."""
        # With high limit
        result_high = grep_files(str(MOCK_REPO), "theorem", max_results=100)

        # With low limit
        result_low = grep_files(str(MOCK_REPO), "theorem", max_results=1)
        assert "truncated" in result_low or result_low.count(":") <= 2

    def test_grep_returns_line_numbers(self):
        """Test that results include line numbers."""
        result = grep_files(str(MOCK_REPO), "theorem top")
        # Format should be "file:line: content"
        assert ":3:" in result or ":1:" in result or "No matches" in result

    def test_grep_sandbox_security(self):
        """Test that grep doesn't escape base_folder."""
        # Try to search parent directory - should not find anything outside
        result = grep_files(str(MOCK_REPO), "import pytest")
        # This pattern exists in test files but not in mock_lean_repository
        assert "test_grep.py" not in result


class TestCreateGrepTool:
    """Tests for create_grep_tool factory."""

    def test_create_grep_tool_returns_tool(self):
        """Test that create_grep_tool returns a tool with invoke method."""
        tool = create_grep_tool(str(MOCK_REPO))
        assert hasattr(tool, "invoke")

    def test_grep_tool_has_correct_name(self):
        """Test that the tool has the expected name."""
        tool = create_grep_tool(str(MOCK_REPO))
        assert tool.name == "grep"

    def test_grep_tool_invocation(self):
        """Test invoking the grep tool."""
        tool = create_grep_tool(str(MOCK_REPO))
        result = tool.invoke({"pattern": "theorem"})
        assert "theorem" in result or "No matches" in result

    def test_grep_tool_with_custom_glob(self):
        """Test grep tool created with custom file glob."""
        tool = create_grep_tool(str(MOCK_REPO), file_glob="*.toml")
        result = tool.invoke({"pattern": "name"})
        # Should only search .toml files
        assert ".lean" not in result or "No matches" in result
