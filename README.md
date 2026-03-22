# BankAnalyzerQt

BankAnalyzerQt is a comprehensive desktop application built with Python and PyQt6 designed to parse, analyze, visualize, and persist bank statements. By leveraging data manipulation libraries, it extracts transaction data securely and generates actionable financial insights, all running entirely offline natively on your machine to guarantee absolute privacy for your sensitive data.

## 🚀 Features

- **Local Data Persistence:** Uses an embedded `SQLite` database to save all imported transactions and configurations, acting as a permanent local ledger for your finances.
- **Multi-Format Processing:** Automatically parses standard bank statement **PDFs** (via `pdfplumber`) and universal **CSV** exports seamlessly into structured data.
- **Custom Categorization Engine:** A dynamic Settings UI lets you add custom categories, assign visual colors, and define comma-separated keyword matching to intelligently track spending per your definitions.
- **Interactive Budgeting:** Set monthly expense limits per-category and watch real-time progress bars turn yellow and red as you approach your limits.
- **Modern Premium Interface:** A custom-built, dark-themed PyQt6 dashboard featuring detailed tabular breakdowns and expanding hierarchical Tree Views separating transactions by category.
- **Dynamic Visualizations:** Integrates `matplotlib` natively providing responsive pie charts and temporal bar charts.
- **Exporting & Reporting:** Export your clean data straight into **CSV**, beautifully formatted **Excel (.xlsx)** spreadsheets, or generate professional **PDF** summary reports powered by `reportlab`.

## 🏗️ Architecture

The project is structured into distinct, modular components:

- `main.py`: The PyQt6 graphical UI controller, managing the main dashboard state, tabs, and interactive elements.
- `analyzer.py`: The core ingestion engine supporting PDF extraction, CSV reading, and pandas-driven data transformations.
- `database.py`: The SQLite data layer handling local persistence of transactions, categories, and custom keywords.
- `settings_dialog.py`: A dedicated configuration panel for managing the category engine and defining budget constraints.
- `export_utils.py`: The reporting module capable of generating CSV, Excel sheets, and PDF summary reports.

## 🧠 What I Learned

Building this project provided me with invaluable experience and pushed my skills in software engineering and data handling:

- **Advanced UI Design with PyQt6:** Learned how to build complex, responsive, and modern graphical interfaces in Python. Built robust components combining `QTabWidget`, `QTreeWidget`, layouts, and deep styling via QSS.
- **Data Architecture & Persistence:** Evolved a single-session tool into a fully persistent application using structured SQLite queries to manage rules, budgets, and historical finances securely locally.
- **Data Extraction & Manipulation:** Mastered extracting structured tabular data from semi-structured PDFs and raw CSV files. Enhanced my proficiency in `pandas` by transforming, cleaning, and aggregating DataFrames.
- **Reporting & Generation:** Extended an application's lifecycle by learning how to generate standard Excel documents (`openpyxl`) and programmatic PDF documents (`reportlab`).
- **Software Architecture:** Structured a robust, multi-file Python application ensuring clean separation between data analysis, persistence, and the presentation layer.

## 🛠️ Technologies Used

- **Language:** Python 3
- **UI Framework:** PyQt6
- **Data Processing:** pandas, pdfplumber
- **Visualization:** matplotlib
- **Database:** SQLite3
- **Reporting:** openpyxl, reportlab

## ⚙️ Getting Started

### Prerequisites

- Python 3.8+ installed
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
   *(Installs PyQt6, pandas, pdfplumber, matplotlib, reportlab, and openpyxl)*

3. **Run the application:**
   ```bash
   python main.py
   ```
