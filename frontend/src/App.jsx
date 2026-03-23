import { useState, useEffect } from 'react'

function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/insights')
      .then(res => {
        if (!res.ok) throw new Error("Could not fetch data.")
        return res.json()
      })
      .then(json => {
        setData(json)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="dashboard-container"><div className="header"><h2>Loading LedgerLens Web...</h2></div></div>
  if (error) return <div className="dashboard-container"><div className="header"><h2 style={{color: 'var(--accent-red)'}}>API Offline or No Data</h2><p>{error}</p></div></div>

  const categories = Object.entries(data.category_breakdown || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  return (
    <div className="dashboard-container animate-fade">
      <header className="header">
        <h1>LedgerLens Web</h1>
        <p>Your local financial data, projected beautifully.</p>
      </header>

      <div className="grid">
        <div className="glass-card">
          <h3>Total Expenses</h3>
          <p className="value spent">${data.total_spent.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</p>
        </div>
        <div className="glass-card">
          <h3>Total Income</h3>
          <p className="value received">${data.total_received.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</p>
        </div>
        
        <div className="glass-card" style={{gridColumn: '1 / -1'}}>
          <h3>Top Spending Categories</h3>
          <div className="list-container">
            {categories.length > 0 ? categories.map(([cat, amt]) => (
              <div key={cat} className="list-item">
                <span style={{fontWeight: 500}}>{cat}</span>
                <span className="value spent" style={{fontSize: '1.2rem', margin: 0}}>${amt.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
              </div>
            )) : <p>No expenses found.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
