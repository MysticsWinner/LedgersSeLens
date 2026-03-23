from fastapi import FastAPI, HTTPException
import pandas as pd
import json
from core.analyzer import load_all_transactions_df, generate_insights, detect_subscriptions

app = FastAPI(
    title="LedgerLens API",
    description="A local REST API serving insights and transaction data from the LedgerLens database.",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the LedgerLens API. Try /api/insights or /api/transactions"}

@app.get("/api/transactions")
def get_transactions(limit: int = 50, offset: int = 0):
    df = load_all_transactions_df()
    if df.empty:
        return {"data": [], "total": 0}
        
    df_sliced = df.iloc[offset:offset+limit].copy()
    # Convert dates to string for JSON serialization
    df_sliced['Date'] = df_sliced['Date'].dt.strftime('%Y-%m-%d')
    
    # We replace NaNs with None so it translates to JSON null
    df_sliced = df_sliced.where(pd.notnull(df_sliced), None)
    
    records = df_sliced.to_dict(orient="records")
    return {"data": records, "total": len(df), "limit": limit, "offset": offset}

@app.get("/api/insights")
def get_insights():
    df = load_all_transactions_df()
    if df.empty:
        raise HTTPException(status_code=404, detail="No transactions found")
        
    insights = generate_insights(df)
    
    # Format and serialize the complex pandas objects for our JSON response
    response_data = {
        "total_spent": float(insights["total_spent"]),
        "total_received": float(insights["total_received"]),
        "category_breakdown": insights["category_breakdown"].to_dict(),
        "timeline": {str(k): float(v) for k, v in insights["timeline"].items()},
        "forecast": {str(k): float(v) for k, v in insights["forecast"].items()}
    }
    
    return response_data

@app.get("/api/subscriptions")
def get_subscriptions():
    df = load_all_transactions_df()
    if df.empty:
        return {"data": []}
        
    subs = detect_subscriptions(df)
    return {"data": subs}

@app.post("/api/plaid/sync")
def sync_plaid_data(access_token: str = "mock-sandbox-token"):
    """
    Mocks a Plaid API synchronization endpoint. In production, this would use 
    the `plaid-python` client to pull real transactions using the user's access_token.
    """
    from database.db_manager import save_transaction
    import datetime
    
    # Mock some data from "Plaid"
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    mock_plaid_data = [
        {"date": today, "desc": "AMAZON WEB SERVICES", "amount": -15.42, "category": "Utilities"},
        {"date": today, "desc": "PAYROLL DIRECT DEPOSIT", "amount": 2500.00, "category": "Income"},
        {"date": today, "desc": "UBER TRIP SF", "amount": -22.50, "category": "Transport"}
    ]
    
    for tx in mock_plaid_data:
        save_transaction(
            tx["date"],
            tx["desc"],
            tx["amount"],
            tx["category"],
            "Plaid Linked Account"
        )
        
    return {
        "status": "success", 
        "message": f"Successfully synced {len(mock_plaid_data)} transactions from Plaid.",
        "transactions_imported": mock_plaid_data
    }

if __name__ == "__main__":
    import uvicorn
    # Make sure to run the server on localhost to maintain privacy
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
