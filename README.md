# LedgerLens

LedgerLens is an advanced, offline-first personal finance dashboard built over **3,000+ lines of Python** and **PyQt6**. It ingests, analyzes, and visualizes raw bank statements (PDFs and CSVs) seamlessly. With its modern dark-theme UI, predictive forecasting, AI-assisted categorization, and robust SQLite persistence, it serves as a fully featured local ledger that guarantees absolute data privacy.

## ✨ Key Features 

- **100% Offline Privacy:** Processes and persists `10,000+` rows of transactions entirely locally via an embedded SQLite ledger with zero cloud dependencies.
- **4-in-1 Dockable Dashboard:** Engineered using Qt's native `QDockWidget` architecture allowing users to drag, float, and snap **4** independent analysis modules (Trends, Balances, Raw Data, Budgets) into completely personalized layouts.
- **2-Tiered Categorization Engine:** Employs explicit string-matching tracking for mapped keywords and an intelligent fallback heuristic dictionary for predicting missing merchant mappings natively.
- **7-Day Predictive Forecasting:** Leverages `pandas` to calculate rolling velocity averages, accurately plotting end-of-month spend trajectories onto `matplotlib` bar graphs.
- **Dynamic Tag Sandbox:** A customized UI table matrix allowing users to test regex-matching rules dynamically using distinct, visual Tag Chips (built with customized `0px` inline paddings).
- **3 Universal Export Formats:** Serializes cleansed SQL database streams seamlessly into raw **CSV**, automatically formatted **Excel (.xlsx)**, and programmatic multi-page **PDF** output reports (`reportlab`).
- **Headless CLI & REST API:** Fully featured `FastAPI` server and built-in Python CLI allowing programmatic data access, pipeline automation, and JSON endpoint serving without launching the graphical interface.

## 🏗️ Architecture

The codebase was rigorously refactored, breaking down a rigid monolithic script into a clean, scalable **5-module Python package ecosystem**:

- **`main.py`**: A minimal bootloader **(< 20 lines of code)**.
- **`core/`**: Houses the heavy `.py` analytics logic handling `pandas` DataFrame aggregations, statement parsing, and predictive math rendering.
- **`database/`**: Dedicated schema definitions orchestrating SQLite cursor operations, relational queries, and non-destructive table migrations.
- **`ui/`**: 
  - **`theme.py` Engine**: A centralized **150+ line global cascaded stylesheet (QSS)** delivering the dark-mode glassmorphism aesthetic uniformly.
  - Isolated subdirectories (`windows/`, `dialogs/`, and `components/`) decoupling the `QDockWidget` routing from the raw pandas data.
- **`cli.py` & `server.py`**: Dedicated headless entrypoints exposing the core database layers to terminal scripts and RESTful JSON endpoints (via FastAPI) respectively.

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

- **Core:** Python 3.10+, argparse
- **GUI:** PyQt6
- **Server / API:** FastAPI, Uvicorn
- **Data Science:** pandas, pdfplumber
- **Graphics:** matplotlib
- **Database:** SQLite3
- **I/O & Logging:** openpyxl, reportlab

## 📥 Installation

LedgerLens requires Python 3.10+ and uses standard `pip` for dependency management. No heavy databases or external servers are required to be installed manually, as it uses an embedded SQLite database!

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MysticsWinner/LedgerLens.git
   cd LedgerLens
   ```

2. **Create a Virtual Environment (Recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate       # On Linux/macOS
   .\venv\Scripts\activate        # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Running the App

LedgerLens provides three distinct entrypoints to interact with your local financial data:

### 1. Graphical Dashboard (GUI)
Launch the primary visual application to view the dockable dashboard, interact with your transactions, and modify categorization rules.
```bash
python main.py
```

### 2. Command Line Interface (CLI)
Interact with your data directly from the terminal without launching the GUI. Perfect for quick headless checks.
```bash
# View a high-level summary of your expenses and top categories
python cli.py insights

# View your 5 most recent transactions
python cli.py transactions --limit 5
```

### 3. REST API Server (FastAPI)
Spin up a local HTTP server to access your LedgerLens data programmatically via JSON endpoints. This is incredibly useful if you want to query your data via external local services or automate scripting pipelines.
```bash
python server.py
```
*The API will mount locally at `http://127.0.0.1:8000`. You can query endpoints such as `/api/insights` or `/api/transactions`.*

## 💻 Usage Guide

### Ingesting Data
- **Through the UI**: Open the application via `python main.py`, navigate to the Data/Upload module (depending on your dock layout), and select your raw bank statement PDFs or CSVs. LedgerLens will automatically parse, cleanse, and insert these into the local SQLite database.

### Categorizing Transactions
- **Tag Sandbox**: Use the visual Tag Chips in the dashboard to map explicit keywords (e.g., "target", "doordash", "shell") to customized categories.
- **Heuristic Fallback**: If a transaction doesn't match your explicit tags, the engine will attempt to guess the category using a built-in heuristic dictionary before defaulting to "Other".

### Reviewing Forecasts & Insights
- **Trends Module**: View the 7-day predictive forecasting and visual velocity charts summarizing where your expenditures are going month-over-month.
- **REST Equivalent**: Run `curl http://localhost:8000/api/insights` while the server is running to get this same forecast strictly in JSON format.

### Exporting Reports
- Click the necessary export buttons on the GUI dashboard to generate comprehensive `.xlsx` spreadsheets, raw `.csv` dumps, or heavily formatted, multi-page `.pdf` reports of your cleansed ledger data. Every export happens entirely offline!
