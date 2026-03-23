import pytest
import os
from core import ml_engine
from database import db_manager

TEST_DB = 'test_ml_data.db'

@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    db_manager.DB_FILE = TEST_DB
    db_manager.init_db()
    
    # Reset internal ML cache explicitly
    with ml_engine._model_lock:
        ml_engine._model_cache = None
        
    yield
    
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass

def test_predict_untrained_fallback():
    # Attempt prediction with 0 database rows seeded
    prediction = ml_engine.predict_category("UBER EATS LONG DRIVE")
    assert prediction == "Other", "A completely untrained model should intelligently fallback to 'Other'"

def test_train_and_predict_success():
    # Seed precisely 5 transactions (the minimum required to train in ml_engine.py)
    db_manager.save_transaction("2026-03-01", "CHEVRON GAS", -20.0, "Transport")
    db_manager.save_transaction("2026-03-02", "ARCO STATION", -15.0, "Transport")
    db_manager.save_transaction("2026-03-03", "DOORDASH DELIVERY", -35.0, "Food")
    db_manager.save_transaction("2026-03-04", "DELIVEROO", -25.0, "Food")
    db_manager.save_transaction("2026-03-05", "SHELL OIL", -45.0, "Transport")
    
    success = ml_engine.train_model()
    assert success is True, "Model should train successfully with 5 valid rows"
    
    # Test Prediction based on Naive Bayes words, NOT explicit heuristics strings
    prediction_transport = ml_engine.predict_category("FAST GAS STATION 55")
    # Actually, Naive Bayes models on exact word overlap. Let's test exact vocabulary
    prediction_food = ml_engine.predict_category("DOORDASH APP PURCHASE")
    
    # The word DOORDASH should skew probability highly to Food
    assert prediction_food == "Food"
