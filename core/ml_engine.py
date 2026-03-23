import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from database.db_manager import get_all_transactions
import threading

# Global model cache to avoid retraining on every prediction
_model_cache = None
_model_lock = threading.Lock()
_fallback_default = "Other"

def train_model():
    """
    Fetches all historical transactions and trains a Naive Bayes text classifier 
    on the Description -> Category mapping.
    """
    global _model_cache
    
    rows = get_all_transactions(account_filter="All Accounts")
    if not rows or len(rows) < 5:
        # Not enough data to train a meaningful model
        with _model_lock:
            _model_cache = None
        return False
        
    df = pd.DataFrame(rows, columns=['ID', 'Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
    
    # Filter out empty descriptions or 'Other' categories to prevent pollution
    # Actually, we might want to train on everything except 'Other'
    train_df = df[df['Category'] != _fallback_default].copy()
    
    if len(train_df) < 5:
        with _model_lock:
            _model_cache = None
        return False

    # Create an NLP pipeline: Vectorize Text -> Train Naive Bayes
    model = make_pipeline(CountVectorizer(ngram_range=(1, 2)), MultinomialNB())
    
    try:
        model.fit(train_df['Description'], train_df['Category'])
        with _model_lock:
            _model_cache = model
        return True
    except Exception as e:
        print(f"ML Engine Training Error: {e}")
        return False

def predict_category(description):
    """
    Predicts the category of a transaction description using the trained Naive Bayes model.
    If the model isn't trained, it tries to train it once. If it fails, returns 'Other'.
    """
    global _model_cache
    
    if not _model_cache:
        # Try to train if we haven't yet
        success = train_model()
        if not success or not _model_cache:
            return _fallback_default
            
    try:
        with _model_lock:
            prediction = _model_cache.predict([description])[0]
        return prediction
    except Exception as e:
        print(f"ML Engine Prediction Error: {e}")
        return _fallback_default
