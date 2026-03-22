from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import random
from datetime import datetime, timedelta

def generate_mock_statement(filename="mock_statement.pdf"):
    doc = SimpleDocTemplate(filename, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Bank Statement", styles['Title']))
    elements.append(Paragraph("Account ending in x1234", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Table data
    data = [['Date', 'Description', 'Amount']]
    
    start_date = datetime.now() - timedelta(days=30)
    
    # Generate some mock transactions
    merchants = [
        ("Starbucks Store #491", -5.50),
        ("Uber Rides", -15.00),
        ("Amazon.com", -49.99),
        ("Netflix Subscription", -14.99),
        ("Whole Foods Market", -85.20),
        ("Comcast Internet", -70.00),
        ("Payroll Deposit", 3500.00),
        ("Target Store", -120.50),
        ("Shell Station", -45.00)
    ]
    
    curr_date = start_date
    for i in range(25):
        desc, base_amt = random.choice(merchants)
        # Add some variance
        if base_amt < 0:
            amt = base_amt + random.uniform(-5, 5)
        else:
            amt = base_amt
            
        date_str = curr_date.strftime("%Y-%m-%d")
        data.append([date_str, desc, f"{amt:.2f}"])
        
        curr_date += timedelta(days=random.randint(1, 2))
        
    table = Table(data, colWidths=[100, 250, 100])
    
    # Style
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ])
    table.setStyle(style)
    
    elements.append(table)
    doc.build(elements)
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_mock_statement("mock_statement.pdf")
