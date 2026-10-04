"""
LedgerSeLens Payment Categorizer & Classification Engine
Provides fine-grained classification for payments, transfers, bills,
subscriptions, loans, and credit card settlements with robust heuristic fallbacks.
"""

import re
from typing import Dict, List, Optional, Tuple

# Comprehensive payment categories and their default visual themes
PAYMENT_CATEGORIES = {
    'Payment: Credit Card': {
        'color': '#30b0c7',
        'rules': 'credit card payment,autopay credit,card payment,chase card,amex epayment,citi autopay,capital one payment,discover payment,apple card payment,card payout'
    },
    'Payment: Loan & Mortgage': {
        'color': '#ac8e68',
        'rules': 'mortgage payment,auto loan,car payment,student loan,nelnet,sallie mae,sofi loan,lending club,home loan,chase mortgage,wells fargo mortgage'
    },
    'Payment: Transfer & P2P': {
        'color': '#40c8e0',
        'rules': 'venmo,zelle,paypal,cash app,wire transfer,ach transfer,account transfer,external transfer,transfer to,p2p payment,apple cash'
    },
    'Payment: Bill & Utility': {
        'color': '#e5a50a',
        'rules': 'online bill pay,utility bill,electric payment,water bill,gas bill,pg&e,coned,verizon bill,at&t bill,t-mobile bill,comcast bill,spectrum bill,trash service'
    },
    'Payment: Tax': {
        'color': '#8a8a8e',
        'rules': 'irs treas,tax payment,state tax,franchise tax,property tax,dmv renewal,county tax,excise tax,usataxpy'
    },
    'Payment: Subscription': {
        'color': '#af52de',
        'rules': 'recurring payment,monthly sub,annual subscription,apple.com/bill,google play,netflix,spotify,hulu,disney+,amazon prime,chatgpt,github sub,adobe'
    },
    'Payment: Insurance': {
        'color': '#5856d6',
        'rules': 'geico,progressive,state farm,allstate,liberty mutual,blue cross,kaiser,aetna,united health,cigna,dental insurance,vision insurance'
    }
}

# Standard non-payment default categories for general transactions
STANDARD_CATEGORIES = {
    'Food': {
        'color': '#ff9f0a',
        'rules': 'restaurant,cafe,starbucks,mcdonalds,grocery,whole foods,trader joe,doordash,ubereats,grubhub,instacart,safeway,kroger'
    },
    'Transport': {
        'color': '#64d2ff',
        'rules': 'uber,lyft,transit,gas,shell,chevron,arco,mta,bart,subway,delta,american airlines,united airlines,parking,toll'
    },
    'Utilities': {
        'color': '#ffd60a',
        'rules': 'electric,water,internet,comcast,pg&e,verizon,at&t,utilities'
    },
    'Shopping': {
        'color': '#bf5af2',
        'rules': 'amazon,walmart,target,apple,best buy,costco,home depot,ikea,clothing,nike,zara'
    },
    'Entertainment': {
        'color': '#ff453a',
        'rules': 'netflix,spotify,hulu,steam,amc,cinema,concert,ticketmaster,playstation,nintendo,xbox'
    },
    'Healthcare': {
        'color': '#ff375f',
        'rules': 'hospital,clinic,pharmacy,cvs,walgreens,doctor,dental,optometry,medicare,prescription'
    },
    'Education': {
        'color': '#5e5ce6',
        'rules': 'tuition,university,college,textbooks,coursera,udemy,school,books'
    },
    'Housing': {
        'color': '#0a84ff',
        'rules': 'rent,mortgage,hoa fee,landlord,apartment,lease'
    },
    'Income': {
        'color': '#32d74b',
        'rules': 'salary,payroll,direct deposit,transfer from,dividend,refund,interest earned,bonus,tax refund'
    },
    'Other': {
        'color': '#8e8e93',
        'rules': ''
    }
}

# All combined categories
ALL_DEFAULT_CATEGORIES = {**STANDARD_CATEGORIES, **PAYMENT_CATEGORIES}

# Regex patterns for payment channels & types
PAYMENT_PATTERNS = [
    (re.compile(r'\b(credit\s*card\s*pay(ment)?|chase\s*(epay|card)|amex\s*(epayment|autopay)|citi\s*(card|autopay)|cap(ital)?\s*one.*?(pymt|pay(ment)?)|discover\s*e-?pay)\b', re.I), 'Payment: Credit Card'),
    (re.compile(r'\b(mortgage\s*pay(ment)?|auto\s*loan|car\s*pay(ment)?|student\s*loan|nelnet|sallie\s*mae|sofi\s*(loan|lending))\b', re.I), 'Payment: Loan & Mortgage'),
    (re.compile(r'\b(venmo|zelle(\s*to|\s*from)?|paypal\s*(transfer|instant)?|cash\s*app|wire\s*transfer|ach\s*(transfer|pmt)|p2p\s*pay)\b', re.I), 'Payment: Transfer & P2P'),
    (re.compile(r'\b(online\s*bill\s*pay|utility\s*bill|pg&e\s*pay|coned\s*bill|water\s*dept|electric\s*bill|(verizon|at&t|t-mobile|comcast|spectrum|cox|pg&e|coned)\b.*?\b(bill|pay(ment)?))\b', re.I), 'Payment: Bill & Utility'),
    (re.compile(r'\b(irs\s*treas|state\s*tax|usataxpy|franchise\s*tax|county\s*property\s*tax|dmv\s*(renewal|fee))\b', re.I), 'Payment: Tax'),
    (re.compile(r'\b(recurring\s*pay(ment)?|apple\.com/bill|google\s*\*?(play|services)|spotify\s*sub|netflix\.com|gym\s*membership)\b', re.I), 'Payment: Subscription'),
    (re.compile(r'\b(geico\s*(direct|ins)?|progressive\s*ins|state\s*farm|blue\s*cross|kaiser\s*perm|allstate)\b', re.I), 'Payment: Insurance'),
]

def classify_payment(description: str, amount: Optional[float] = None) -> Optional[str]:
    """
    Checks if a description represents a specific payment category.
    Returns the category name if matched, else None.
    """
    if not description:
        return None
        
    desc_clean = str(description).strip()
    
    # 1. Regex pattern matching
    for pattern, category in PAYMENT_PATTERNS:
        if pattern.search(desc_clean):
            return category
            
    # 2. Keyword matching across PAYMENT_CATEGORIES
    desc_lower = desc_clean.lower()
    for cat_name, cat_data in PAYMENT_CATEGORIES.items():
        rules = cat_data.get('rules', '')
        if not rules:
            continue
        for kw in rules.split(','):
            kw = kw.strip().lower()
            if kw and kw in desc_lower:
                return cat_name
                
    # 3. Generic payment keywords fallback
    if re.search(r'\b(autopay|bill\s*pay|direct\s*debit|e-?payment|payment\s*thank\s*you)\b', desc_lower):
        if 'card' in desc_lower or 'credit' in desc_lower:
            return 'Payment: Credit Card'
        if 'loan' in desc_lower:
            return 'Payment: Loan & Mortgage'
        if 'utility' in desc_lower or 'electric' in desc_lower or 'water' in desc_lower:
            return 'Payment: Bill & Utility'
        return 'Payment: Transfer & P2P'

    return None

def is_payment(description: str) -> bool:
    """Check if the transaction description indicates any type of payment or transfer."""
    return classify_payment(description) is not None
