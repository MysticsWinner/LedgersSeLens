# BankAnalyzerQt

BankAnalyzerQt is an advanced, offline-first personal finance dashboard built over **3,000+ lines of Python** and **PyQt6**. It ingests, analyzes, and visualizes raw bank statements (PDFs and CSVs) seamlessly. With its modern dark-theme UI, predictive forecasting, AI-assisted categorization, and robust SQLite persistence, it serves as a fully featured local ledger that guarantees absolute data privacy.

## ✨ Key Features 

- **100% Offline Privacy:** Processes and persists `10,000+` rows of transactions entirely locally via an embedded SQLite ledger with zero cloud dependencies.
- **4-in-1 Dockable Dashboard:** Engineered using Qt's native `QDockWidget` architecture allowing users to drag, float, and snap **4** independent analysis modules (Trends, Balances, Raw Data, Budgets) into completely personalized layouts.
- **2-Tiered Categorization Engine:** Employs explicit string-matching tracking for mapped keywords and an intelligent fallback heuristic dictionary for predicting missing merchant mappings natively.
- **7-Day Predictive Forecasting:** Leverages `pandas` to calculate rolling velocity averages, accurately plotting end-of-month spend trajectories onto `matplotlib` bar graphs.
- **Dynamic Tag Sandbox:** A customized UI table matrix allowing users to test regex-matching rules dynamically using distinct, visual Tag Chips (built with customized `0px` inline paddings).
- **3 Universal Export Formats:** Serializes cleansed SQL database streams seamlessly into raw **CSV**, automatically formatted **Excel (.xlsx)**, and programmatic multi-page **PDF** output reports (`reportlab`).

## 🏗️ Architecture

The codebase was rigorously refactored, breaking down a rigid monolithic script into a clean, scalable **5-module Python package ecosystem**:

- **`main.py`**: A minimal bootloader **(< 20 lines of code)**.
- **`core/`**: Houses the heavy `.py` analytics logic handling `pandas` DataFrame aggregations, statement parsing, and predictive math rendering.
- **`database/`**: Dedicated schema definitions orchestrating SQLite cursor operations, relational queries, and non-destructive table migrations.
- **`ui/`**: 
  - **`theme.py` Engine**: A centralized **150+ line global cascaded stylesheet (QSS)** delivering the dark-mode glassmorphism aesthetic uniformly.
  - Isolated subdirectories (`windows/`, `dialogs/`, and `components/`) decoupling the `QDockWidget` routing from the raw pandas data.

## ⏱️ Development Journey & Effort

This project represented a significant investment of time and engineering rigor, spanning approximately **60+ hours over 4 weeks** of focused development. What started as a basic data-parsing script rapidly escalated into a robust, 3,000+ line highly optimized local finance application.

The iterative effort broke down into:
- **Phase 1 (Data Engineering & Persistence):** ~25 hours engineering the `pdfplumber` parsing algorithms to extract messy tabular bank data accurately and establishing the robust SQLite relational database schemas.
- **Phase 2 (Core UI & Analytics):** ~20 hours mastering `PyQt6` to build the foundational interactive event loops, complex `QTreeWidget` data layers, and the native `matplotlib` visualization pipelines.
- **Phase 3 (V2 UI Overhaul & Polish):** ~15 hours decoupling the monolithic codebase into a 5-module MVC package, building the floating `QDockWidget` architecture, and engineering a pristine 150-line global custom QSS dark theme.

## 🧠 What I Learned (New Skills Acquired)

Building this application pushed the bounds of my technical comfort zone and drastically expanded my capabilities as a Python software engineer:
- **Memory Management in PyQt6:** Uncovered deep intricacies in Qt's C++ bindings, specifically mastering how to safely detach, garbage-collect, and inject custom `QWidget` classes (like our native Tag/Chip Editors) inside heavily redrawn `QTableWidget` structures without triggering pointer deletion crashes.
- **Advanced State Synching:** Learned how to seamlessly sync complex graphical user interface (GUI) layouts with a live SQLite backend, ensuring the multi-panel dashboard dynamically repainted instantly across all metrics after any rule modification.
- **Complex Data Transformations:** Extracted highly unstructured, multi-page PDFs using `pdfplumber` and mapped them into pristine `pandas` DataFrames using advanced string heuristics and regex slicing.
- **Algorithmic Visualization:** Bridged raw structured SQL queries directly into `pandas` to calculate 7-day rolling velocity math, allowing me to plot temporal predictive forecast trajectories natively entirely without external graphical APIs.
- **Scalable Architecture:** Evolved my functional scripting skills into professional object-oriented (OOP) software engineering, massively utilizing the Model-View-Controller (MVC) paradigm to cleanly decouple the SQLite backend `(models)`, the UI arrays `(views)`, and the analytics processing `(controllers)` across distinct physical Python packages.

## 🛠️ Technologies Used

- **Core:** Python 3.10+
- **GUI:** PyQt6
- **Data Science:** pandas, pdfplumber
- **Graphics:** matplotlib
- **Database:** SQLite3
- **I/O & Logging:** openpyxl, reportlab

## ⚙️ Getting Started

### Prerequisites
- Python 3.10+
- Pip package manager

### Build Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/BankAnalyzerQt.git
   cd BankAnalyzerQt
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python main.py
   ```
