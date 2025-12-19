"""CSS styles for smon dashboard."""

APP_CSS = """
Screen { layout: vertical; }
.bar { height: 1; }
.pane { height: 1fr; }

/* Split View Layout */
.split-container {
    height: 1fr;
    width: 100%;
}

.list-pane {
    width: 45%;
    min-width: 40;
    height: 100%;
    border-right: solid $primary;
}

.detail-pane {
    width: 55%;
    height: 100%;
    padding-left: 1;
}

.table-container {
    height: 1fr;
    overflow-y: auto;
    scrollbar-background: $surface;
    scrollbar-color: $primary;
}

/* Detail sections in right pane */
.detail-section {
    height: 6;
    border: round $surface;
    padding: 0 1;
    overflow-y: auto;
}

.script-section {
    height: 12;
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

/* Beautiful Modal screen styles */
ScriptModal {
    align: center middle;
    background: $surface-darken-2 90%;
}

#script_modal_container {
    width: 85%;
    height: 80%;
    background: $panel;
    border: thick $accent;
    border-title-color: $accent;
    border-title-background: $panel;
}

.script-header {
    height: 3;
    background: $primary-darken-1;
    color: $text;
    text-align: center;
    padding: 1;
    border-bottom: solid $accent;
}

.script-content {
    height: 1fr;
    background: $surface;
    padding: 1;
    overflow: auto;
    scrollbar-background: $panel;
    scrollbar-color: $accent;
}

OutputModal {
    align: center middle;
    background: $surface-darken-2 90%;
}

#output_modal_container {
    width: 95%;
    height: 90%;
    background: $panel;
    border: thick $success;
    border-title-color: $success;
    border-title-background: $panel;
}

.output-header {
    height: 3;
    background: $success-darken-1;
    color: $text;
    text-align: center;
    padding: 1;
    border-bottom: solid $success;
}

.output-content {
    height: 1fr;
    padding: 1;
}

.output-section-header {
    height: 1;
    background: $primary-darken-2;
    color: $text;
    padding-left: 1;
    margin-top: 1;
}

.output-scroll-container {
    height: 1fr;
    overflow-y: auto;
    scrollbar-background: $panel;
    scrollbar-color: $success;
    border: solid $primary;
    margin-bottom: 1;
}

.output-log-viewer {
    height: auto;
    background: $surface;
    padding: 1;
}
"""
