"""CSS styles for smon dashboard."""

APP_CSS = """
Screen { layout: vertical; }
.bar { height: 1; }
.pane { height: 1fr; }
.detail { padding: 1; }
.detail-container { height: 15; border: round $surface; padding: 1; overflow-y: auto; }
.script { height: 20; border: round green; padding: 1; overflow-y: auto; }
.syntax-viewer { height: 1fr; border: round blue; padding: 1; overflow-y: auto; }
.log-viewer { height: 1fr; border: round yellow; padding: 1; overflow-y: auto; }
.log-container { height: 1fr; }

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

.output-log-viewer {
    height: 1fr;
    background: $surface;
    border: solid $primary;
    margin-bottom: 1;
    padding: 1;
    overflow: auto;
    scrollbar-background: $panel;
    scrollbar-color: $success;
}
"""

