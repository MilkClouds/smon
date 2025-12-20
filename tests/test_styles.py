"""Tests for smon.styles module."""

from smon.styles import APP_CSS


class TestStyles:
    """Tests for CSS styles."""

    def test_app_css_is_string(self) -> None:
        """Test that APP_CSS is a non-empty string."""
        assert isinstance(APP_CSS, str)
        assert len(APP_CSS) > 0

    def test_app_css_contains_essential_selectors(self) -> None:
        """Test that APP_CSS contains essential CSS selectors."""
        essential_selectors = [
            ".bar",
            ".pane",
            "Screen",
            ".split-container",
            ".list-pane",
            ".detail-pane",
        ]
        for selector in essential_selectors:
            assert selector in APP_CSS, f"Missing selector: {selector}"

    def test_app_css_valid_syntax(self) -> None:
        """Test that CSS has balanced braces (basic syntax check)."""
        open_braces = APP_CSS.count("{")
        close_braces = APP_CSS.count("}")
        assert open_braces == close_braces, "Unbalanced braces in CSS"
