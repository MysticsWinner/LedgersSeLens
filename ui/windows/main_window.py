import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
                             QFrame, QGraphicsDropShadowEffect, QAbstractItemView,
                             QScrollArea, QProgressBar, QSizePolicy, QMenu,
                             QTabWidget, QTreeWidget, QTreeWidgetItem, QInputDialog, QComboBox, QDockWidget)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QCursor, QIcon, QAction

from core.analyzer import parse_statement, generate_insights, load_all_transactions_df
from ui.dialogs.settings_dialog import SettingsDialog
from database.db_manager import get_categories
from ui.components.charts import MplCanvas
from ui.components.cards import create_card

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LedgerLens Dashboard")
        self.resize(1300, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        # Top Bar
        top_bar = QHBoxLayout()
        self.main_layout.addLayout(top_bar)

        header_layout = QVBoxLayout()
        title = QLabel("Financial Overview")
        title.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        self.lbl_status = QLabel("Ready.")
        self.lbl_status.setFont(QFont("Inter", 11))
        self.lbl_status.setStyleSheet("color: #8e8e93;")
        header_layout.addWidget(title)
        header_layout.addWidget(self.lbl_status)
        top_bar.addLayout(header_layout)
        
        top_bar.addStretch()

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_settings.clicked.connect(self.open_settings)
        top_bar.addWidget(self.btn_settings, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.btn_export = QPushButton("Export Data")
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.clicked.connect(self.export_data)
        top_bar.addWidget(self.btn_export, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_upload = QPushButton("Import Statement")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.clicked.connect(self.import_statement)
        top_bar.addWidget(self.btn_upload, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Account Filter
        self.cb_account = QComboBox()
        self.cb_account.addItem("All Accounts")
        self.cb_account.currentTextChanged.connect(self.on_filter_changed)
        top_bar.addWidget(self.cb_account, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Date Filter
        self.cb_date = QComboBox()
        self.cb_date.addItems(["All Time", "This Month", "Last Month", "Year to Date"])
        self.cb_date.currentTextChanged.connect(self.on_filter_changed)
        top_bar.addWidget(self.cb_date, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Summary Cards
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(20)
        self.main_layout.addLayout(summary_layout)

        self.card_income, self.lbl_income = create_card("Total Income")
        self.lbl_income.setStyleSheet("color: #30d158; border: none; background: transparent;")
        summary_layout.addWidget(self.card_income)

        self.card_spent, self.lbl_spent = create_card("Total Expenses")
        self.lbl_spent.setStyleSheet("color: #ff453a; border: none; background: transparent;")
        summary_layout.addWidget(self.card_spent)
        
        self.card_net, self.lbl_net = create_card("Net Total")
        summary_layout.addWidget(self.card_net)

        # Dock Manager (Internal QMainWindow)
        self.dock_manager = QMainWindow()
        self.dock_manager.setWindowFlags(Qt.WindowType.Widget)
        
        self.dock_manager.setDockNestingEnabled(True)
        # Empty central widget for dock manager so it purely holds floating/docked widgets
        dummy = QWidget()
        dummy.setFixedSize(0,0)
        self.dock_manager.setCentralWidget(dummy)
        self.main_layout.addWidget(self.dock_manager)
        
        # Pie Card
        self.pie_card = QFrame()
        self.pie_card.setObjectName("DashboardCard")
        pie_layout = QVBoxLayout(self.pie_card)
        pie_layout.setContentsMargins(10, 10, 10, 10)
        self.pie_canvas = MplCanvas(self, width=3, height=3, dpi=100)
        pie_layout.addWidget(self.pie_canvas)
        
        # Bar Card
        self.bar_card = QFrame()
        self.bar_card.setObjectName("DashboardCard")
        bar_layout = QVBoxLayout(self.bar_card)
        bar_layout.setContentsMargins(10, 10, 10, 10)
        self.bar_canvas = MplCanvas(self, width=3, height=3, dpi=100)
        bar_layout.addWidget(self.bar_canvas)
        
        # Budgets Card
        self.budget_card = QFrame()
        self.budget_card.setObjectName("DashboardCard")
        bc_layout = QVBoxLayout(self.budget_card)
        bc_layout.setContentsMargins(15, 15, 15, 15)
        self.budget_container = QWidget()
        self.budget_container_layout = QVBoxLayout(self.budget_container)
        self.budget_container_layout.setContentsMargins(0, 0, 0, 0)
        self.budget_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.budget_container.setStyleSheet("background-color: transparent;")
        self.budget_scroll = QScrollArea()
        self.budget_scroll.setWidgetResizable(True)
        self.budget_scroll.setWidget(self.budget_container)
        self.budget_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        bc_layout.addWidget(self.budget_scroll)

        # Data Area (Tabs)
        self.data_tabs = QTabWidget()

        # Table Area
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Category", "Amount"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.on_transaction_double_clicked)
        self.data_tabs.addTab(self.table, "All Transactions")
        
        # Category Breakdown Area
        self.tree_categories = QTreeWidget()
        self.tree_categories.setColumnCount(3)
        self.tree_categories.setHeaderLabels(["Category / Date", "Description", "Amount"])
        self.tree_categories.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_categories.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree_categories.itemDoubleClicked.connect(self.on_tree_double_clicked)
        self.data_tabs.addTab(self.tree_categories, "Category Breakdown")
        
        # Build Docks
        self.pie_dock = QDockWidget("Category Breakdown", self.dock_manager)
        self.pie_dock.setWidget(self.pie_card)
        self.pie_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        self.bar_dock = QDockWidget("Temporal Trends", self.dock_manager)
        self.bar_dock.setWidget(self.bar_card)
        self.bar_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        self.budget_dock = QDockWidget("Montly Budgets", self.dock_manager)
        self.budget_dock.setWidget(self.budget_card)
        self.budget_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        self.data_dock = QDockWidget("Data Navigator", self.dock_manager)
        self.data_dock.setWidget(self.data_tabs)
        self.data_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        self.dock_manager.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.pie_dock)
        self.dock_manager.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.bar_dock)
        self.dock_manager.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.budget_dock)
        self.dock_manager.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.data_dock)
        
        # Set Default Dock proportions
        self.dock_manager.splitDockWidget(self.pie_dock, self.bar_dock, Qt.Orientation.Horizontal)
        self.dock_manager.splitDockWidget(self.bar_dock, self.budget_dock, Qt.Orientation.Horizontal)

        self.load_historical_data()

    def load_historical_data(self):
        from database.db_manager import get_accounts
        accounts = get_accounts()
        current_acc = self.cb_account.currentText()
        self.cb_account.blockSignals(True)
        self.cb_account.clear()
        self.cb_account.addItem("All Accounts")
        for acc in accounts:
            self.cb_account.addItem(acc)
        idx = self.cb_account.findText(current_acc)
        if idx >= 0:
            self.cb_account.setCurrentIndex(idx)
        self.cb_account.blockSignals(False)
        self.on_filter_changed()

    def on_filter_changed(self):
        from datetime import datetime, date, timedelta
        import calendar
        
        acc = self.cb_account.currentText()
        date_sel = self.cb_date.currentText()
        
        start_date = None
        end_date = None
        
        today = date.today()
        if date_sel == "This Month":
            start_date = today.replace(day=1).strftime('%Y-%m-%d')
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day).strftime('%Y-%m-%d')
        elif date_sel == "Last Month":
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            start_date = last_day_last_month.replace(day=1).strftime('%Y-%m-%d')
            end_date = last_day_last_month.strftime('%Y-%m-%d')
        elif date_sel == "Year to Date":
            start_date = today.replace(month=1, day=1).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
            
        df = load_all_transactions_df(start_date=start_date, end_date=end_date, account_filter=acc)
        
        if not df.empty:
            insights = generate_insights(df)
            self.update_dashboard(insights)
            self.lbl_status.setText(f"View: {date_sel} - {acc}")
            self.lbl_status.setStyleSheet("color: #30d158;")
        else:
            self.update_dashboard({"empty": True})
            self.lbl_status.setText(f"No data for {acc} in {date_sel}.")
            self.lbl_status.setStyleSheet("color: #ff9f0a;")

    def on_transaction_double_clicked(self, item):
        row = item.row()
        date_item = self.table.item(row, 0)
        tx_id = date_item.data(Qt.ItemDataRole.UserRole)
        if tx_id:
            from ui.dialogs.transaction_detail import TransactionDetailDialog
            dlg = TransactionDetailDialog(tx_id, self)
            if dlg.exec():
                self.load_historical_data()
                
    def on_tree_double_clicked(self, item, column):
        tx_id = item.data(0, Qt.ItemDataRole.UserRole)
        if tx_id:
            from ui.dialogs.transaction_detail import TransactionDetailDialog
            dlg = TransactionDetailDialog(tx_id, self)
            if dlg.exec():
                self.load_historical_data()

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.on_filter_changed()

    def export_data(self):
        menu = QMenu(self)
        
        action_csv = QAction("Export to CSV", self)
        action_excel = QAction("Export to Excel", self)
        action_pdf = QAction("Generate PDF Report", self)
        
        action_csv.triggered.connect(lambda: self.save_export('csv'))
        action_excel.triggered.connect(lambda: self.save_export('excel'))
        action_pdf.triggered.connect(lambda: self.save_export('pdf'))
        
        menu.addAction(action_csv)
        menu.addAction(action_excel)
        menu.addAction(action_pdf)
        
        menu.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))

    def save_export(self, format_type):
        from export_utils import export_to_csv, export_to_excel, export_to_pdf
        
        filters = {
            'csv': "CSV Files (*.csv)",
            'excel': "Excel Files (*.xlsx)",
            'pdf': "PDF Files (*.pdf)"
        }
        
        ext = {'csv': '.csv', 'excel': '.xlsx', 'pdf': '.pdf'}
        
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", f"financial_report{ext[format_type]}", filters[format_type])
        if filepath:
            try:
                if format_type == 'csv':
                    export_to_csv(filepath)
                elif format_type == 'excel':
                    export_to_excel(filepath)
                elif format_type == 'pdf':
                    export_to_pdf(filepath)
                    
                self.lbl_status.setText(f"Exported successfully to {filepath.split('/')[-1]}")
                self.lbl_status.setStyleSheet("color: #30d158;")
            except Exception as e:
                self.lbl_status.setText(f"Export failed: {e}")
                self.lbl_status.setStyleSheet("color: #ff453a;")

    def import_statement(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Bank Statement", "", "Supported Files (*.pdf *.csv);;PDF Files (*.pdf);;CSV Files (*.csv)")
        if file_path:
            account_name, ok = QInputDialog.getText(self, "Account Route", "Enter the account name for these transactions (e.g. Checking, Credit Card):", Qt.EchoMode.Normal, "Main Account")
            if not ok or not account_name.strip():
                return
            
            self.lbl_status.setText(f"Processing: {file_path.split('/')[-1]}...")
            self.lbl_status.setStyleSheet("color: #0a84ff;")
            QApplication.processEvents()
            
            try:
                df = parse_statement(file_path, account_name.strip())
                self.load_historical_data() # Force UI refresh matching current filters
                self.lbl_status.setText(f"Successfully loaded: {file_path.split('/')[-1]} to {account_name.strip()}")
                self.lbl_status.setStyleSheet("color: #30d158;")
            except Exception as e:
                self.lbl_status.setText(f"Error parsing file: {e}")
                self.lbl_status.setStyleSheet("color: #ff453a;")

    def update_dashboard(self, insights):
        if insights.get("empty", False):
            self.lbl_income.setText("$0.00")
            self.lbl_spent.setText("$0.00")
            self.lbl_net.setText("$0.00")
            self.table.setRowCount(0)
            self.tree_categories.clear()
            self.pie_canvas.axes.clear()
            self.pie_canvas.draw()
            self.bar_canvas.axes.clear()
            self.bar_canvas.draw()
            while self.budget_container_layout.count():
                child = self.budget_container_layout.takeAt(0)
                if child.widget(): child.widget().deleteLater()
            return

        total_inc = insights['total_received']
        total_exp = insights['total_spent']
        net = total_inc - total_exp
        
        self.lbl_income.setText(f"${total_inc:,.2f}")
        self.lbl_spent.setText(f"${total_exp:,.2f}")
        self.lbl_net.setText(f"${net:,.2f}")
        
        if net >= 0:
            self.lbl_net.setStyleSheet("color: #30d158; border: none; background: transparent;")
        else:
            self.lbl_net.setStyleSheet("color: #ff453a; border: none; background: transparent;")
            self.lbl_net.setText(f"-${abs(net):,.2f}")
        
        # Update table
        df = insights['transactions']
        self.table.setRowCount(len(df))
        if not df.empty:
            for row_idx, row in df.iterrows():
                date_item = QTableWidgetItem(str(row['Date'].date()))
                date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                date_item.setData(Qt.ItemDataRole.UserRole, int(row['ID']))
                self.table.setItem(row_idx, 0, date_item)
                
                desc = str(row['Description']).title()
                if row.get('Notes') or row.get('Receipt'):
                    desc += " 📎"
                desc_item = QTableWidgetItem(desc)
                self.table.setItem(row_idx, 1, desc_item)
                
                cat_item = QTableWidgetItem(str(row['Category']))
                cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, 2, cat_item)
                
                amt_str = f"${row['Amount']:,.2f}"
                if row['Amount'] < 0:
                     amt_item = QTableWidgetItem(f"-${abs(row['Amount']):,.2f}")
                     amt_item.setForeground(QColor('#ff453a'))
                else:
                     amt_item = QTableWidgetItem(f"+${row['Amount']:,.2f}")
                     amt_item.setForeground(QColor('#30d158'))
                     
                amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 3, amt_item)

        # Update Tree Categories
        self.tree_categories.clear()
        if not df.empty:
            categories = df['Category'].unique()
            for cat in sorted(categories):
                cat_df = df[df['Category'] == cat]
                cat_total = cat_df['Amount'].sum()
                
                parent = QTreeWidgetItem(self.tree_categories)
                parent.setText(0, str(cat))
                parent.setFont(0, QFont("Inter", 11, QFont.Weight.Bold))
                
                if cat_total < 0:
                    amt_text = f"-${abs(cat_total):,.2f}"
                    parent.setForeground(2, QColor('#ff453a'))
                else:
                    amt_text = f"+${cat_total:,.2f}"
                    parent.setForeground(2, QColor('#30d158'))
                    
                parent.setText(2, amt_text)
                parent.setFont(2, QFont("Inter", 11, QFont.Weight.Bold))
                parent.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                for _, row in cat_df.iterrows():
                    child = QTreeWidgetItem(parent)
                    child.setText(0, str(row['Date'].date()))
                    child.setData(0, Qt.ItemDataRole.UserRole, int(row['ID']))
                    
                    desc = str(row['Description']).title()
                    if row.get('Notes') or row.get('Receipt'):
                        desc += " 📎"
                    child.setText(1, desc)
                    
                    amt = row['Amount']
                    if amt < 0:
                        child.setText(2, f"-${abs(amt):,.2f}")
                        child.setForeground(2, QColor('#ff453a'))
                    else:
                        child.setText(2, f"+${amt:,.2f}")
                        child.setForeground(2, QColor('#30d158'))
                        
                    child.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    
            self.tree_categories.expandAll()

        # Update Pie Chart (Categories)
        self.pie_canvas.axes.clear()
        categories = insights['category_breakdown']
        if not categories.empty:
            cat_sorted = categories.sort_values(ascending=False)
            colors = ['#ff453a', '#ff9f0a', '#ffd60a', '#32d74b', '#64d2ff', '#0a84ff', '#bf5af2']
            wedges, texts, autotexts = self.pie_canvas.axes.pie(
                cat_sorted, labels=cat_sorted.index, autopct='%1.1f%%',
                startangle=90, textprops={'color':"#8e8e93", 'fontsize': 10},
                colors=colors[:len(cat_sorted)], 
                wedgeprops={'linewidth': 2, 'edgecolor': '#1c1c1e'}
            )
            self.pie_canvas.axes.set_title("Expenses by Category")
            self.pie_canvas.fig.tight_layout()
        self.pie_canvas.draw()
        
        # Update Bar Chart (Timeline)
        self.bar_canvas.axes.clear()
        timeline = insights['timeline']
        forecast = insights['forecast']
        if not timeline.empty:
            dates = [d.strftime('%b %d') for d in timeline.index]
            amounts = [abs(v) if v < 0 else 0 for v in timeline.values]
            
            self.bar_canvas.axes.bar(dates, amounts, color='#0a84ff', width=0.6, edgecolor='none', alpha=0.85, label='Daily Spend')
            
            # Forecast line plotting logic
            if not forecast.empty:
                f_amounts = [abs(v) if v < 0 else 0 for v in forecast.values]
                if len(dates) == len(f_amounts):
                    self.bar_canvas.axes.plot(dates, f_amounts, color='#ffd60a', linestyle='--', linewidth=2, label='7-Day Trend')
                    self.bar_canvas.axes.legend(loc='upper right', frameon=False, labelcolor='#8e8e93', fontsize=9)
                    
            self.bar_canvas.axes.set_title("Expenses Over Time")
            self.bar_canvas.axes.tick_params(axis='x', rotation=45)
            self.bar_canvas.axes.grid(axis='y', linestyle='-', alpha=0.1, color='#ffffff')
            self.bar_canvas.fig.tight_layout()
        self.bar_canvas.draw()

        # Update Budgets
        cats = get_categories()
        
        while self.budget_container_layout.count():
            child = self.budget_container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        budget_cats = [c for c in cats if c.get('budget_limit', 0) > 0]
        
        if not budget_cats:
            lbl = QLabel("No budgets set. Go to Settings to set them.")
            lbl.setStyleSheet("color: #8e8e93; font-size: 12px;")
            lbl.setWordWrap(True)
            self.budget_container_layout.addWidget(lbl)
        else:
            for cat in budget_cats:
                cat_name = cat['name']
                limit = float(cat['budget_limit'])
                spent = float(insights['category_breakdown'].get(cat_name, 0.0))
                
                pct = int((spent / limit) * 100) if limit > 0 else 0
                pct = min(pct, 100)
                
                item_widget = QWidget()
                item_layout = QVBoxLayout(item_widget)
                item_layout.setContentsMargins(0, 5, 0, 5)
                
                lbl_layout = QHBoxLayout()
                name_lbl = QLabel(cat_name)
                # handle None values for color gracefully
                cat_color = cat.get('color') or '#ffffff'
                name_lbl.setStyleSheet(f"color: {cat_color}; font-weight: bold; font-size: 12px;")
                amt_lbl = QLabel(f"${spent:,.0f} / ${limit:,.0f}")
                amt_lbl.setStyleSheet("color: #8e8e93; font-size: 11px;")
                
                lbl_layout.addWidget(name_lbl)
                lbl_layout.addStretch()
                lbl_layout.addWidget(amt_lbl)
                item_layout.addLayout(lbl_layout)
                
                bar = QProgressBar()
                bar.setFixedHeight(10)
                bar.setTextVisible(False)
                bar.setRange(0, 100)
                bar.setValue(pct)
                
                chunk_color = "#32d74b" # green
                if pct > 90:
                    chunk_color = "#ff453a" # red
                elif pct > 75:
                    chunk_color = "#ffd60a" # yellow
                    
                bar.setStyleSheet(f"QProgressBar {{ background-color: #2c2c2e; border-radius: 5px; border: none; }} QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 5px; }}")
                item_layout.addWidget(bar)
                
                self.budget_container_layout.addWidget(item_widget)
                
            self.budget_container_layout.addStretch()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
