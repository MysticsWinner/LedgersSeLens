from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt6.QtGui import QFont, QColor

def create_card(title_text):
    card = QFrame()
    card.setObjectName("DashboardCard")
    
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setColor(QColor(0, 0, 0, 80))
    shadow.setOffset(0, 5)
    card.setGraphicsEffect(shadow)
    
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(10)
    
    title = QLabel(title_text)
    title.setFont(QFont("Inter", 12, QFont.Weight.Medium))
    title.setStyleSheet("color: #A0A0A0; border: none; background: transparent;")
    layout.addWidget(title)
    
    value = QLabel("$0.00")
    value.setFont(QFont("Inter", 28, QFont.Weight.Bold))
    value.setStyleSheet("color: #ffffff; border: none; background: transparent;")
    layout.addWidget(value)
    
    return card, value
