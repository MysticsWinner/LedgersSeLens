import csv
import os
import pandas as pd
from database.db_manager import get_all_transactions
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime

def export_to_csv(filepath):
    df = _get_data()
    if not df.empty:
        df.to_csv(filepath, index=False)

def export_to_excel(filepath):
    df = _get_data()
    if not df.empty:
        df.to_excel(filepath, index=False, sheet_name="Transactions")

def export_to_pdf(filepath):
    df = _get_data()
    if df.empty:
        return
        
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    title = Paragraph(f"Financial Report - {datetime.now().strftime('%b %d, %Y')}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 20))
    
    # Calculate totals
    total_spent = df[df['Amount'] < 0]['Amount'].abs().sum()
    total_received = df[df['Amount'] >= 0]['Amount'].sum()
    net = total_received - total_spent
    
    summary_data = [
        ["Total Income:", f"${total_received:,.2f}"],
        ["Total Expenses:", f"${total_spent:,.2f}"],
        ["Net:", f"${net:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[150, 100])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,0), (1,0), colors.green),
        ('TEXTCOLOR', (1,1), (1,1), colors.red),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Transactions table
    data = [['Date', 'Description', 'Category', 'Amount']]
    for _, row in df.iterrows():
        amt_str = f"${row['Amount']:,.2f}"
        data.append([str(row['Date'].date()), str(row['Description']), str(row['Category']), amt_str])
        
    t = Table(data, colWidths=[80, 200, 100, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    
    elements.append(t)
    doc.build(elements)

def _get_data():
    rows = get_all_transactions()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['Date', 'Description', 'Amount', 'Category'])
    df['Date'] = pd.to_datetime(df['Date'])
    df['Amount'] = df['Amount'].astype(float)
    df = df.sort_values(by='Date', ascending=False)
    return df
