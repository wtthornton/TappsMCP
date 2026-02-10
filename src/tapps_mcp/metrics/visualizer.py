"""ASCII chart visualizer for text-based dashboards.

Generates Windows-compatible ASCII bar and line charts for
embedding in markdown dashboards and MCP tool responses.
"""

from __future__ import annotations

# Use basic ASCII characters for Windows compatibility
_BAR_CHAR = "#"
_EMPTY_CHAR = "-"

class AnalyticsVisualizer:
    """Creates ASCII-based charts and tables."""

    @staticmethod
    def create_bar_chart(
        data: dict[str, float],
        title: str = "",
        width: int = 40,
        show_values: bool = True,
    ) -> str:
        """Create a horizontal ASCII bar chart.

        Args:
            data: Label -> value mapping.
            title: Chart title.
            width: Maximum bar width in characters.
            show_values: Show numeric values after bars.
        """
        if not data:
            return ""

        lines: list[str] = []
        if title:
            lines.append(title)
            lines.append("-" * len(title))

        max_val = max(data.values()) if data.values() else 1.0
        max_label = max(len(k) for k in data) if data else 0

        for label, value in data.items():
            bar_len = int((value / max_val) * width) if max_val > 0 else 0
            bar = _BAR_CHAR * bar_len + _EMPTY_CHAR * (width - bar_len)
            if show_values:
                lines.append(f"  {label:<{max_label}} |{bar}| {value:.2f}")
            else:
                lines.append(f"  {label:<{max_label}} |{bar}|")

        return "\n".join(lines)

    @staticmethod
    def create_sparkline(
        values: list[float],
        width: int = 20,
    ) -> str:
        """Create a simple ASCII sparkline.

        Uses block characters to show trend direction.
        """
        if not values:
            return ""

        # Normalize to 0-8 range for block elements
        min_v = min(values)
        max_v = max(values)
        range_v = max_v - min_v if max_v != min_v else 1.0

        # Simple block characters (Windows-safe)
        blocks = " ._-=*#@"

        # Resample if needed
        if len(values) > width:
            step = len(values) / width
            sampled = [values[int(i * step)] for i in range(width)]
        else:
            sampled = values

        chars: list[str] = []
        for v in sampled:
            idx = int(((v - min_v) / range_v) * (len(blocks) - 1))
            chars.append(blocks[idx])

        return "".join(chars)

    @staticmethod
    def create_metric_table(
        headers: list[str],
        rows: list[list[str]],
        title: str = "",
    ) -> str:
        """Create an ASCII table.

        Args:
            headers: Column headers.
            rows: Table rows (list of lists).
            title: Optional table title.
        """
        if not headers or not rows:
            return ""

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Build table
        lines: list[str] = []
        if title:
            lines.append(title)
            lines.append("")

        # Header
        header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        lines.append(header_line)
        lines.append("-+-".join("-" * w for w in col_widths))

        # Rows
        for row in rows:
            cells = [str(cell).ljust(col_widths[i]) if i < len(col_widths) else str(cell)
                     for i, cell in enumerate(row)]
            lines.append(" | ".join(cells))

        return "\n".join(lines)

    @staticmethod
    def create_metric_comparison(
        before: dict[str, float],
        after: dict[str, float],
        title: str = "Metric Comparison",
    ) -> str:
        """Create a side-by-side metric comparison table."""
        all_keys = sorted(set(list(before.keys()) + list(after.keys())))
        if not all_keys:
            return ""

        headers = ["Metric", "Before", "After", "Change"]
        rows: list[list[str]] = []

        for key in all_keys:
            b = before.get(key, 0.0)
            a = after.get(key, 0.0)
            delta = a - b
            sign = "+" if delta > 0 else ""
            rows.append([key, f"{b:.2f}", f"{a:.2f}", f"{sign}{delta:.2f}"])

        return AnalyticsVisualizer.create_metric_table(headers, rows, title)
