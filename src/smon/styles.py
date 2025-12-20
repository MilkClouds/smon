"""CSS styles for smon dashboard."""

APP_CSS = """
Screen { layout: vertical; overflow: hidden; }
.bar { height: 1; }
.pane { height: 1fr; overflow: hidden; }

/* Split View Layout */
.split-container {
    height: 1fr;
    width: 100%;
    overflow: hidden;
}

.list-pane {
    width: 55%;
    min-width: 60;
    height: 100%;
    border-right: solid $primary;
    overflow: hidden;
}

/* Filter bar */
.filter-bar {
    height: 3;
    padding: 0 1;
}

.search-input {
    width: 1fr;
}

.state-select {
    width: 20;
    margin-left: 1;
}

.detail-pane {
    width: 45%;
    height: 100%;
    padding-left: 1;
    overflow: hidden;
}

.table-container {
    height: 1fr;
    overflow-y: auto;
    scrollbar-background: $surface;
    scrollbar-color: $primary;
}

/* Detail sections in right pane */
.detail-section {
    height: 10;
    border: round $surface;
    padding: 0 1;
    overflow-y: auto;
}

.script-section {
    height: 2fr;
    margin-top: 1;
}

.section-header {
    height: 1;
    background: $primary-darken-2;
    padding-left: 1;
}

.script-scroll {
    height: 1fr;
    border: solid $accent;
    overflow-y: auto;
}

.output-section {
    height: 1fr;
    min-height: 8;
    margin-top: 1;
}

.output-split {
    height: 1fr;
}

.output-half {
    width: 1fr;
    padding: 0 1;
}

.output-label {
    height: 1;
    text-align: center;
}

.output-viewer {
    height: 1fr;
    border: solid $surface-lighten-1;
    padding: 0 1;
    overflow-y: auto;
}

"""
