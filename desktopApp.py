import sys, os
from datetime import datetime
from collections import defaultdict

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QTabWidget,
    QComboBox,
    QTextEdit,
    QDateEdit,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QTableWidget, 
    QTableWidgetItem,QHeaderView
)
from PyQt5.QtGui import QPixmap, QPalette, QColor
from PyQt5.QtCore import Qt

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates
import mplcursors

_chart_css = """
                               QFrame {
                               background-color: #ffffff;
                               border: 1px solid #555;
                               border-radius: 20px;
                               padding: 8px;
                               }
                               """

_gauge_css = """
                               QFrame {
                               background-color: #ffffff;
                               border: 1px solid #555;
                               border-radius: 20px;
                               padding: 8px;
                               }
                               """


# ---------------- Dashboard Gauge Helper ----------------
def create_gauge(value, maximum, title, color="green"):
    fig, ax = plt.subplots(figsize=(3, 3), subplot_kw={"projection": "polar"})
    # Simple polar bar to mimic a gauge fill
    ax.bar(0, value, width=3.14, bottom=0, color=color, alpha=0.7)
    ax.set_ylim(0, max(maximum, 1))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{title}\n{value}/{maximum}", fontsize=12)
    fig.tight_layout()
    return fig


# ---------------- Helpers ----------------
def txt_is_pass(text: str) -> bool:
    """
    Determine pass/fail from TXT content.
    Treat as PASS if 'Job.Pass:1' present.
    Treat as FAIL if 'Job.Fail:1' present or Job.Pass != 1.
    """
    labels = [p.strip() for p in text.split(",") if p.strip()]
    has_pass = any(lbl.replace(" ", "").upper() == "JOB.PASS:1" for lbl in labels)
    if has_pass:
        return True
    # explicit fail flag counts as fail
    has_fail = any(lbl.replace(" ", "").upper() == "JOB.FAIL:1" for lbl in labels)
    if has_fail:
        return False
    # Default to fail when there is no pass flag
    return False


def load_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""

# ---------------- FolderViewer with clickable list ----------------

class FolderViewer(QWidget):
    def __init__(self, folder, outcome_filter='All', parent=None):
        super().__init__(parent)
        self.current_folder = folder
        self.outcome_filter = outcome_filter
        self.all_rows = []
        self.page_size = 10
        self.current_page = 0

        layout = QVBoxLayout(self)

        # --- Image Viewer ---
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label, 3)

        # --- Table for metadata ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Timestamp", "File", "Result", "Read String"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)  # non-editable
        self.table.setSelectionBehavior(QTableWidget.SelectRows)  # select entire row
        self.table.setSelectionMode(QTableWidget.SingleSelection)  # one row at a time
        self.table.cellClicked.connect(self.row_clicked)  # connect click event
        layout.addWidget(self.table, 2)

        # --- Pagination controls ---
        nav_layout = QHBoxLayout()
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "20", "50"])
        self.page_size_combo.setCurrentText("10")
        self.page_size_combo.currentTextChanged.connect(self.change_page_size)
        nav_layout.addWidget(QLabel("Rows per page:"))
        nav_layout.addWidget(self.page_size_combo)

        self.first_btn = QPushButton("First")
        self.prev_btn = QPushButton("Prev")
        self.next_btn = QPushButton("Next")
        self.last_btn = QPushButton("Last")

        self.first_btn.clicked.connect(self.first_page)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.last_btn.clicked.connect(self.last_page)

        nav_layout.addWidget(self.first_btn)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.last_btn)

        layout.addLayout(nav_layout)

        # Populate table + image
        self.populate_table()

    def populate_table(self):
        self.all_rows = []
        bmp_files = [f for f in os.listdir(self.current_folder) if f.lower().endswith('.bmp')]
        bmp_files.sort()

        for f in bmp_files:
            base = f[:-4]
            img_path = os.path.join(self.current_folder, f)
            txt_path = os.path.join(self.current_folder, base + '.txt')
            if not os.path.exists(txt_path):
                continue

            content = load_txt(txt_path)
            is_pass = txt_is_pass(content)

            # --- Apply outcome filter ---
            if self.outcome_filter == 'Pass' and not is_pass:
                continue
            if self.outcome_filter == 'Fail' and is_pass:
                continue

            # timestamp
            ts = datetime.fromtimestamp(os.path.getmtime(txt_path)).strftime("%Y-%m-%d %H:%M:%S")

            # shorten file name
            short_name = base if len(base) < 20 else base[:17] + "..."

            # result column
            result = "✔" if is_pass else "✘"

            # read string = everything except Job.Pass / Job.Fail
            parts = [p.strip() for p in content.split(",") if p.strip()]
            read_values = [p for p in parts if not p.upper().startswith("JOB.PASS") and not p.upper().startswith("JOB.FAIL")]
            read_string = ", ".join(read_values)

            self.all_rows.append((ts, short_name, result, read_string, img_path))

        self.current_page = 0
        self.refresh_page()

    def refresh_page(self):
        start = self.current_page * self.page_size
        end = start + self.page_size
        rows = self.all_rows[start:end]

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            ts, short_name, result, read_string, img_path = row
            self.table.setItem(r, 0, QTableWidgetItem(ts))
            self.table.setItem(r, 1, QTableWidgetItem(short_name))
            self.table.setItem(r, 2, QTableWidgetItem(result))
            self.table.setItem(r, 3, QTableWidgetItem(read_string))

        # --- Show first image of current page ---
        if rows:
            self.table.selectRow(0)  # highlight first row
            self.show_image(rows[0][4])
        else:
            self.image_label.clear()

    def show_image(self, img_path):
        pixmap = QPixmap(img_path).scaled(
            500, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(pixmap)

    def row_clicked(self, row, col):
        start = self.current_page * self.page_size
        actual_index = start + row
        if 0 <= actual_index < len(self.all_rows):
            img_path = self.all_rows[actual_index][4]
            self.show_image(img_path)

    def change_page_size(self, text):
        self.page_size = int(text)
        self.current_page = 0
        self.refresh_page()

    def first_page(self):
        self.current_page = 0
        self.refresh_page()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_page()

    def next_page(self):
        if (self.current_page + 1) * self.page_size < len(self.all_rows):
            self.current_page += 1
            self.refresh_page()

    def last_page(self):
        if self.all_rows:
            self.current_page = (len(self.all_rows) - 1) // self.page_size
            self.refresh_page()

# ---------------- Main Application ----------------
class AssureVisionApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AssureVision - Python Desktop (PyQt5)")
        self.resize(1400, 900)

        self.folder_path = None
        self.chart_type = "Line"
        self.outcome_filter = "All"  # All | Fail | Pass

        # Data structure: { prefix: [ { "ts": datetime, "is_pass": bool, "path": str, "content": str } , ... ] }
        self.all_data = {}
        self.filtered_data = {}

        self.layout = QVBoxLayout(self)

        # Top controls
        top_layout = QHBoxLayout()
        self.select_folder_btn = QPushButton("Select Parent Folder")
        self.select_folder_btn.clicked.connect(self.select_folder)
        top_layout.addWidget(self.select_folder_btn)

        top_layout.addWidget(QLabel("Chart Type:"))
        self.chart_type_dropdown = QComboBox()
        self.chart_type_dropdown.addItems(["Line", "Step", "Bar", "Scatter"])
        self.chart_type_dropdown.setCurrentText("Step")
        self.chart_type_dropdown.currentTextChanged.connect(self.change_chart_type)
        top_layout.addWidget(self.chart_type_dropdown)

        # Outcome filter
        top_layout.addWidget(QLabel("Filter:"))
        self.outcome_combo = QComboBox()
        self.outcome_combo.addItems(["All", "Fail Only", "Pass Only"])
        self.outcome_combo.currentTextChanged.connect(self.change_outcome_filter)
        top_layout.addWidget(self.outcome_combo)

        # Date filters
        top_layout.addWidget(QLabel("Start Date:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.dateChanged.connect(self.update_everything)
        top_layout.addWidget(self.start_date_edit)

        top_layout.addWidget(QLabel("End Date:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.dateChanged.connect(self.update_everything)
        top_layout.addWidget(self.end_date_edit)

        self.layout.addLayout(top_layout)

        # Main tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        self.dashboard_tab = QWidget()
        self.images_tab = QTabWidget()  # sub-tabs per subfolder
        self.charts_tab = QTabWidget()  # sub-tabs for charts
        self.system_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.charts_tab, "Charts")
        self.tabs.addTab(self.system_tab, "System Health")
        self.tabs.addTab(self.images_tab, "Images")

        self.dashboard_tab.setLayout(QVBoxLayout())
        self.images_tab.setLayout(QVBoxLayout())
        self.system_tab.setLayout(QVBoxLayout())
        self.system_tab.layout().addWidget(QLabel("System health goes here"))

        # Dashboard placeholders for gauges + cumulative step chart
        self.gauge_layout = QHBoxLayout()
        self.dashboard_tab.layout().addLayout(self.gauge_layout)
        self.dashboard_step_chart = QVBoxLayout()
        self.dashboard_tab.layout().addLayout(self.dashboard_step_chart)

        # store aggregated failure causes across parsed data (paths list per cause)
        self._aggregated_failure_causes = defaultdict(list)

    # ---------------- UI events ----------------
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Parent Folder")
        if not folder:
            return
        self.folder_path = folder
        self.all_data = self.parse_folder_data(folder)
        self.update_everything()

    def change_chart_type(self, text):
        self.chart_type = text
        self.load_charts()

    def change_outcome_filter(self, text):
        if text == "Fail Only":
            self.outcome_filter = "Fail"
        elif text == "Pass Only":
            self.outcome_filter = "Pass"
        else:
            self.outcome_filter = "All"
        self.update_everything()

    def update_everything(self):
        if not self.folder_path:
            return
        self.filtered_data = self.apply_filters(self.all_data)
        self.load_images()
        self.load_charts()
        self.update_dashboard()

    # ---------------- Data parsing ----------------
    def parse_folder_data(self, folder):
        data_by_prefix = defaultdict(list)
        # reset aggregated causes
        self._aggregated_failure_causes = defaultdict(list)

        for root, _, files in os.walk(folder):
            for file in files:
                if not file.lower().endswith(".txt"):
                    continue
                file_path = os.path.join(root, file)
                ts = datetime.fromtimestamp(os.path.getmtime(file_path))
                parts = file[:-4].split("_")
                prefix = "_".join(parts[:-1]) if len(parts) > 1 else parts[0]

                content = load_txt(file_path)
                is_pass = txt_is_pass(content)

                # collect failure causes: every label that is not Job.Pass / Job.Fail and not ':OK'
                labels = [p.strip() for p in content.split(",") if p.strip()]
                for lbl in labels:
                    norm = lbl.replace(" ", "")
                    up = norm.upper()
                    if up.startswith("JOB.PASS") or up.startswith("JOB.FAIL"):
                        continue
                    # also ignore explicit OK markers
                    if up.endswith(":OK") or up.endswith("=OK"):
                        continue
                    # this label considered a failure cause — store path
                    if not is_pass:  # only aggregate for failed items
                        self._aggregated_failure_causes[lbl].append(file_path)

                data_by_prefix[prefix].append(
                    {
                        "ts": ts,
                        "is_pass": is_pass,
                        "path": file_path,
                        "content": content,
                    }
                )
        return data_by_prefix

    # ---------------- Filtering ----------------
    def apply_filters(self, data):
        filtered = {}
        start_ok = self.start_date_edit.date().isValid()
        end_ok = self.end_date_edit.date().isValid()
        start_date = self.start_date_edit.date().toPyDate() if start_ok else None
        end_date = self.end_date_edit.date().toPyDate() if end_ok else None

        for prefix, events in data.items():
            out = []
            for ev in events:
                ts = ev["ts"]
                if start_ok and ts.date() < start_date:
                    continue
                if end_ok and ts.date() > end_date:
                    continue
                if self.outcome_filter == "Fail" and ev["is_pass"]:
                    continue
                if self.outcome_filter == "Pass" and not ev["is_pass"]:
                    continue
                out.append(ev)
            filtered[prefix] = out
        return filtered

    # ---------------- Dashboard ----------------
    def update_dashboard(self):
        # clear gauges
        for i in reversed(range(self.gauge_layout.count())):
            w = self.gauge_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        # clear step chart container
        for i in reversed(range(self.dashboard_step_chart.count())):
            w = self.dashboard_step_chart.itemAt(i).widget()
            if w:
                w.setParent(None)

        # totals computed from filtered_data
        total_count = sum(len(v) for v in self.filtered_data.values())
        total_pass = sum(
            sum(1 for ev in v if ev["is_pass"]) for v in self.filtered_data.values()
        )
        total_fail = total_count - total_pass

        gauges = [
            ("Total", total_count, total_count if total_count > 0 else 1, "blue"),
            ("Pass", total_pass, total_count if total_count > 0 else 1, "green"),
            ("Fail", total_fail, total_count if total_count > 0 else 1, "red"),
        ]
        for title, val, max_val, color in gauges:
            fig = create_gauge(val, max_val, title, color=color)
            canvas = FigureCanvas(fig)
            card = QFrame()
            card.setStyleSheet(_gauge_css)
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(canvas)
            self.gauge_layout.addWidget(card)

        # cumulative step chart (count events, not just pass)
        fig, ax = plt.subplots(figsize=(12, 3.5))
        for prefix, events in self.filtered_data.items():
            sorted_ev = sorted(events, key=lambda e: e["ts"])
            x_vals, y_vals = [], []
            total = 0
            for ev in sorted_ev:
                total += 1  # 1 per event after filters
                x_vals.append(ev["ts"])
                y_vals.append(total)
            if x_vals:
                ax.step(x_vals, y_vals, where="post", label=prefix)
        ax.set_title("Cumulative Step Chart")
        ax.set_xlabel("Time")
        ax.set_ylabel("Cumulative Count")
        ax.grid(True)
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        mplcursors.cursor(ax, hover=True)
        canvas = FigureCanvas(fig)
        card = QFrame()
        card.setStyleSheet(_chart_css)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(canvas)
        self.dashboard_step_chart.addWidget(card)

    # ---------------- Images (respect outcome filter) ----------------
    def load_images(self):
        self.images_tab.clear()
        if not self.folder_path:
            return
        subfolders = [
            f
            for f in os.listdir(self.folder_path)
            if os.path.isdir(os.path.join(self.folder_path, f))
        ]
        subfolders.sort()

        for sub in subfolders:
            sub_path = os.path.join(self.folder_path, sub)
            viewer = FolderViewer(sub_path, outcome_filter=self.outcome_filter)
            self.images_tab.addTab(viewer, sub)

    # ---------------- NEW: show filtered images by cause ----------------
    def filter_image_viewer(self, files, cause):
        """
        files: list of full paths to the .txt files which matched the cause
        cause: label string clicked
        """
        self.images_tab.clear()
        if not files:
            empty_tab = QWidget()
            empty_tab.setLayout(QVBoxLayout())
            empty_tab.layout().addWidget(QLabel(f"No images for cause: {cause}"))
            self.images_tab.addTab(empty_tab, "Filtered")
            return

        # group by folder name so we can create sub-tabs per folder (optional)
        subfolders = defaultdict(list)
        for f in files:
            subfolders[os.path.dirname(f)].append(f)

        for folder_path, flist in subfolders.items():
            viewer = FolderViewer(os.path.basename(folder_path), flist)
            tab_label = f"{os.path.basename(folder_path)} ({cause})"
            self.images_tab.addTab(viewer, tab_label)

        # add reset tab
        reset_tab = QWidget()
        reset_tab.setLayout(QVBoxLayout())
        reset_btn = QPushButton("Reset to All Images")
        reset_btn.clicked.connect(self.load_images)
        reset_tab.layout().addWidget(reset_btn)
        self.images_tab.addTab(reset_tab, "Reset")

    # ---------------- Charts ----------------
    def load_charts(self):
        self.charts_tab.clear()
        if not self.folder_path:
            return

        cumulative_tab = QWidget()
        heartbeat_tab = QWidget()
        summary_tab = QWidget()
        failures_tab = QWidget()  # failure causes tab

        self.charts_tab.addTab(cumulative_tab, "Cumulative")
        self.charts_tab.addTab(heartbeat_tab, "Heartbeat")
        self.charts_tab.addTab(summary_tab, "Summary")
        self.charts_tab.addTab(failures_tab, "Failure Causes")

        for tab in [cumulative_tab, heartbeat_tab, summary_tab, failures_tab]:
            tab.setLayout(QVBoxLayout())

        self.render_cumulative_chart(cumulative_tab)
        self.render_heartbeat_chart(heartbeat_tab)
        self.render_summary_chart(summary_tab)
        self.render_failure_causes_chart(failures_tab)

    def render_failure_causes_chart(self, tab):
        # Aggregate failure causes from filtered_data (only failed events)
        cause_counts = defaultdict(list)
        for prefix, events in self.filtered_data.items():
            for ev in events:
                if not ev["is_pass"]:
                    labels = [p.strip() for p in ev["content"].split(",") if p.strip()]
                    for lbl in labels:
                        up = lbl.replace(" ", "").upper()
                        if up.startswith("JOB.PASS") or up.startswith("JOB.FAIL"):
                            continue
                        # ignore OK markers
                        if up.endswith(":OK") or up.endswith("=OK"):
                            continue
                        cause_counts[lbl].append(ev["path"])

        fig, ax = plt.subplots(figsize=(10, 5))
        labels = list(cause_counts.keys())
        values = [len(v) for v in cause_counts.values()]

        if not labels:
            ax.text(0.5, 0.5, "No failure causes found", ha="center", va="center")
        else:
            bars = ax.bar(labels, values, color="orange")
            ax.set_xticklabels(labels, rotation=45, ha="right")
            # connect click/hover to open filtered image viewer
            cursor = mplcursors.cursor(bars, hover=True)

            # On select/click we will call filter_image_viewer
            def on_add(sel):
                idx = sel.index
                lbl = labels[idx]
                paths = cause_counts[lbl]
                # open images for this cause
                self.filter_image_viewer(paths, lbl)

            cursor.connect("add", on_add)

        ax.set_title("Aggregated Failure Causes")
        ax.set_ylabel("Count")
        ax.grid(True)
        fig.tight_layout()
        canvas = FigureCanvas(fig)
        card = QFrame()
        card.setStyleSheet(_chart_css)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(canvas)
        tab.layout().addWidget(card)

    # ---------------- Chart helpers (reuse from earlier) ----------------
    def render_cumulative_chart(self, tab):
        self._render_time_chart(tab, "Cumulative Count Over Time", cumulative=True)

    def render_summary_chart(self, tab):
        # count events per prefix (after filters)
        summary_counts = {k: len(v) for k, v in self.filtered_data.items()}
        fig, ax = plt.subplots(figsize=(10, 5))
        prefixes = list(summary_counts.keys())
        values = list(summary_counts.values())

        if self.chart_type == "Bar":
            ax.bar(prefixes, values)
        elif self.chart_type == "Line":
            ax.plot(prefixes, values, marker="o")
        elif self.chart_type == "Step":
            ax.step(prefixes, values, where="post")
        elif self.chart_type == "Scatter":
            ax.scatter(prefixes, values)

        ax.set_title("Summary Chart by Prefix")
        ax.set_xlabel("Prefix")
        ax.set_ylabel("Event Count")
        ax.grid(True)
        mplcursors.cursor(ax, hover=True)
        canvas = FigureCanvas(fig)
        card = QFrame()
        card.setStyleSheet(_chart_css)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(canvas)
        tab.layout().addWidget(card)

    def render_heartbeat_chart(self, tab):
        # per-minute bins of pass/fail per prefix
        time_bin = 60  # seconds
        grouped = defaultdict(lambda: defaultdict(lambda: {"pass": 0, "fail": 0}))
        for prefix, events in self.filtered_data.items():
            for ev in events:
                ts = ev["ts"]
                binned_ts = datetime.fromtimestamp(
                    ts.timestamp() // time_bin * time_bin
                )
                if ev["is_pass"]:
                    grouped[prefix][binned_ts]["pass"] += 1
                else:
                    grouped[prefix][binned_ts]["fail"] += 1

        fig, ax = plt.subplots(figsize=(10, 5))
        for prefix, bins in grouped.items():
            times = sorted(bins.keys())
            if not times:
                continue
            pass_vals = [bins[t]["pass"] for t in times]
            fail_vals = [bins[t]["fail"] for t in times]

            # Respect chart type and outcome filter
            show_pass = self.outcome_filter in ("All", "Pass")
            show_fail = self.outcome_filter in ("All", "Fail")

            if self.chart_type == "Line":
                if show_pass:
                    ax.plot(times, pass_vals, label=f"{prefix}-Pass", color="green")
                if show_fail:
                    ax.plot(times, fail_vals, label=f"{prefix}-Fail", color="red")
            elif self.chart_type == "Step":
                if show_pass:
                    ax.step(
                        times,
                        pass_vals,
                        where="post",
                        label=f"{prefix}-Pass",
                        color="green",
                    )
                if show_fail:
                    ax.step(
                        times,
                        fail_vals,
                        where="post",
                        label=f"{prefix}-Fail",
                        color="red",
                    )
            elif self.chart_type == "Bar":
                # bars at minute resolution (thin width)
                # matplotlib date units are days; convert 1 minute to days
                width = 1.0 / (24 * 60) * 0.8
                if show_pass:
                    ax.bar(
                        times,
                        pass_vals,
                        width=width,
                        label=f"{prefix}-Pass",
                        color="green",
                        align="center",
                    )
                if show_fail:
                    ax.bar(
                        times,
                        fail_vals,
                        width=width,
                        label=f"{prefix}-Fail",
                        color="red",
                        align="center",
                    )
            elif self.chart_type == "Scatter":
                if show_pass:
                    ax.scatter(times, pass_vals, label=f"{prefix}-Pass", color="green")
                if show_fail:
                    ax.scatter(times, fail_vals, label=f"{prefix}-Fail", color="red")

        ax.set_xlabel("Time")
        ax.set_ylabel("Count")
        ax.set_title("Heartbeat Chart (Pass/Fail by Prefix)")
        ax.grid(True)
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        mplcursors.cursor(ax, hover=True)
        canvas = FigureCanvas(fig)
        card = QFrame()
        card.setStyleSheet(_chart_css)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(canvas)
        tab.layout().addWidget(card)

    def _render_time_chart(self, tab, title, y_label="Value", cumulative=False):
        # clear existing
        for i in reversed(range(tab.layout().count())):
            w = tab.layout().itemAt(i).widget()
            if w:
                w.setParent(None)

        fig, ax = plt.subplots(figsize=(10, 5))
        for prefix, events in self.filtered_data.items():
            sorted_ev = sorted(events, key=lambda e: e["ts"])
            if not sorted_ev:
                continue
            x_vals, y_vals = [], []
            running = 0
            for ev in sorted_ev:
                x_vals.append(ev["ts"])
                if cumulative:
                    running += 1  # count each filtered event
                    y_vals.append(running)
                else:
                    y_vals.append(1)  # event per timestamp
            # draw by chart type
            if self.chart_type == "Line":
                ax.plot(x_vals, y_vals, label=prefix)
            elif self.chart_type == "Step":
                ax.step(x_vals, y_vals, where="post", label=prefix)
            elif self.chart_type == "Bar":
                width = 1.0 / (24 * 60) * 0.8  # narrow bar ~0.8 minute
                ax.bar(x_vals, y_vals, width=width, label=prefix, align="center")
            elif self.chart_type == "Scatter":
                ax.scatter(x_vals, y_vals, label=prefix)

        ax.set_title(title)
        ax.set_xlabel("Time")
        ax.set_ylabel(y_label)
        ax.grid(True)
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        mplcursors.cursor(ax, hover=True)
        canvas = FigureCanvas(fig)
        card = QFrame()
        card.setStyleSheet(_chart_css)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(canvas)
        tab.layout().addWidget(card)


# ---------------- Run Application ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Apply dark theme
    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    app.setPalette(dark_palette)

    # Apply stylesheet for modern buttons/tabs
    app.setStyleSheet(
        """
        QPushButton {
            background-color: #1976D2;
            color: white;
            border-radius: 8px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #1565C0;
        }
        QTabWidget::pane {
            border: 1px solid #444;
            background: #2b2b2b;
        }
        QTabBar::tab {
            background: #444;
            padding: 8px;
            border-radius: 6px;
            margin: 2px;
            color: white;
        }
        QTabBar::tab:selected {
            background: #1976D2;
            color: white;
        }
    """
    )
    window = AssureVisionApp()
    window.show()
    sys.exit(app.exec_())
