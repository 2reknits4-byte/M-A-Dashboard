import yfinance as yf
import pandas as pd
import os
import time
import requests

# FRED Risk Free Rate Fetch (cache)
_FRED_CACHE = {"ts": 0.0, "value": None}

def get_risk_free_rate_fred(
        series_id: str = "DGS10", # 10-Year Treasury Constant Maturity Rate
        api_key:str | None = None,
        cache_ttl_seconds: int = 60*60, # 1 hour
) -> float:

# Gets RiskFreeRate as decimal 
    now = time.time()
    if _FRED_CACHE["value"] is not None and (now - _FRED_CACHE["ts"]) < cache_ttl_seconds:
        return _FRED_CACHE["value"]
    
    api_key = api_key or os.getenv("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED API key not provided. Set FRED_API_KEY environment variable or pass api_key parameter.")
    
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,  #gets last 10 observations
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()

    obs = payload.get("observations", [])
    if not obs:
        raise ValueError(f"No observations found for series {series_id}.")
    
    # Find most recent non-null value
    latest_val = None
    for o in obs:
        v = o.get("value")
        try:
            latest_val = float(v)
            break
        except (TypeError, ValueError):
            continue
    
    if latest_val is None:
        raise ValueError(f"No valid observations found for series {series_id}.")

    # Convert to decimal
    rf = latest_val / 100.0

    _FRED_CACHE["ts"] = now
    _FRED_CACHE["value"] = rf
    return rf

# Fetch company info from YahooFinance
def get_company_financials(ticker) -> dict:
    try: 
        company = yf.Ticker(ticker)
        info = company.info
        financials = company.financials if isinstance(company.financials, pd.DataFrame) else pd.DataFrame()
        cashflow = getattr(company, "cashflow", pd.DataFrame())
        balance_sheet = getattr(company, "balance_sheet", pd.DataFrame())

# yfinance Error Handling
        if company is None:
            print({"Warning": f"Could not fetch data for ticker {ticker}."})
        elif info is None or info =={}:
            print([{"Warning": f"No info data found for ticker {ticker}."}])
        elif financials is None or financials.empty:
            print([{"Warning": f"No financials data found for ticker {ticker}."}])
        elif cashflow is None or cashflow.empty:
            print([{"Warning": f"No cashflow data found for ticker {ticker}."}])
        elif balance_sheet is None or balance_sheet.empty:
            print([{"Warning": f"No balance sheet data found for ticker {ticker}."}])
        
# Net Income Pull
        net_income = 0
        if isinstance(financials, pd.DataFrame) and not financials.empty and "Net Income" in financials.index:
            net_income_series = financials.loc["Net Income"].dropna()
            if not net_income_series.empty:
                net_income = net_income_series.iloc[0]

# Revenue Pull
        revenue = 0
        if isinstance(financials, pd.DataFrame) and not financials.empty and "Total Revenue" in financials.index:
            revenue_series = financials.loc["Total Revenue"].dropna()
            if not revenue_series.empty:
                revenue = revenue_series.iloc[0]
            # If Revenue not found, try info dict
        if revenue == 0:
            revenue = info.get("totalRevenue", 0) or 0

# Depreciation & Amortization Pull
        depreciation_amortization = 0
        if isinstance(cashflow, pd.DataFrame) and not cashflow.empty:
            for label in ("Depreciation", "Depreciation & Amortization", "Depreciation And Amortization", "Depreciation Amortization"):
                if label in cashflow.index:
                    depreciation_series = cashflow.loc[label].dropna()
                    if not depreciation_series.empty:
                        depreciation_amortization = abs(depreciation_series.iloc[0])
                        break

# EBITDA Pull
        ebitda = 0
            # If EBITDA is in Income Statement
        if isinstance(financials, pd.DataFrame) and not financials.empty and "EBITDA" in financials.index:
            ebitda_series = financials.loc["EBITDA"].dropna()
            if not ebitda_series.empty:
                ebitda = ebitda_series.iloc[0]
            # If EBITDA not found, calculate from EBIT + D&A
        if ebitda == 0:
            ebit = 0
            if "Operating Income" in financials.index:
                operating_income_series = financials.loc["Operating Income"].dropna()
                if not operating_income_series.empty:
                    ebit = operating_income_series.iloc[0]
            if ebit != 0 and depreciation_amortization != 0:
                ebitda = ebit + depreciation_amortization
            # EBITDA from info dict as last resort
        if ebitda == 0:
            ebitda = info.get("ebitda", 0) or 0

# Capex Pull
        capital_expenditures = 0
        if isinstance(cashflow, pd.DataFrame) and not cashflow.empty and "Capital Expenditures" in cashflow.index:
            capex_series = cashflow.loc["Capital Expenditures"].dropna()
            if not capex_series.empty:
                capital_expenditures = abs(capex_series.iloc[0])
        
# TCA TCL Pull to calculate NWC
        net_working_capital = 0
        if isinstance(balance_sheet, pd.DataFrame) and not balance_sheet.empty:
            if {"Total Current Assets", "Total Current Liabilities"}.issubset(balance_sheet.index):
                assets_series = balance_sheet.loc["Total Current Assets"].dropna()
                liabilities_series = balance_sheet.loc["Total Current Liabilities"].dropna()
                if not assets_series.empty and not liabilities_series.empty:
                    net_working_capital = assets_series.iloc[0] - liabilities_series.iloc[0]

# Income Tax Expense Pull *tax rate est.
        income_tax_expense = 0
        tax_labels = ["Income Tax Expense", "Provision for Income Taxes", "Income Taxes", "Provision for Taxes",""
        "Tax Provision"]
        if isinstance(financials, pd.DataFrame) and not financials.empty:
            for label in tax_labels:
                if label in financials.index:
                    s = financials.loc[label].dropna()
                    if not s.empty:
                        income_tax_expense = s.iloc[0]
                        break
        
# Pre Tax Income Pull *tax rate est.
        pre_tax_income = 0
        pretax_labels = ["Pretax Income", "Income Before Tax", "Pre-Tax Income"]
        if isinstance(financials, pd.DataFrame) and not financials.empty:
            for label in pretax_labels:
                if label in financials.index:
                    s = financials.loc[label].dropna()
                    if not s.empty:
                        pre_tax_income = s.iloc[0]
                        break

# Tax Rate Estimation
        def _first_value_by_labels(df, labels, default=0.0):
            if df is None or df.empty:
                return default
            for label in labels:
                if label in df.index:
                    s = df.loc[label].dropna()
                    if not s.empty:
                        return s.iloc[0]
            return default
        
        # Prefer Yahoo Disclosed Tax Rate
        tax_rate_est = _first_value_by_labels(
            financials,
            labels=("Tax Rate For Calcs", "Effective Tax Rate", "Tax Rate"),
            default=0.0
        )

        # Nullify if outside reasonable bounds
        if not (0.05 <= tax_rate_est <= 0.40):
            tax_rate_est = 0.0

        # If no disc. tax, or if outside reasonable bounds, estimate from income tax & pre-tax income
        if pre_tax_income not in (0, None) and income_tax_expense not in (0, None):
            try:
                raw_rate = abs(income_tax_expense / pre_tax_income)
                tax_rate_est = min(max(raw_rate, 0.05), 0.40) # Clamp between 5% and 40%
            except Exception:
                tax_rate_est = 0
        # If estimation fails, set default 25%
        if tax_rate_est == 0:
            tax_rate_est = 0.25
            print(f"Warning: Not disclosed and could not estimate tax rate for ticker {ticker}. Setting to 25%.")

# Interest Expense Pull
        interest_expense = info.get("interestExpense", 0) or 0
        interest_expense_labels = ["Interest Expense", "Interest Expense Non Operating", "Interest Expense, Net"]

        if interest_expense == 0 and isinstance(financials, pd.DataFrame) and not financials.empty:
            for label in interest_expense_labels:
                if label in financials.index:
                    interest_series = financials.loc[label].dropna()
                    if not interest_series.empty:
                        interest_expense = abs(interest_series.iloc[0])
                        break
        
# Total Debt Pull
        total_debt = info.get("totalDebt")
        debt_labels = ["Total Debt", "Long Term Debt", "Short Long Term Debt"]

        if total_debt is None and isinstance(balance_sheet, pd.DataFrame) and not balance_sheet.empty:
            debt_candidates = {}

            for label in debt_labels:
                if label in balance_sheet.index:
                    debt_series = balance_sheet.loc[label].dropna()
                    if not debt_series.empty:
                        debt_candidates[label] = abs(debt_series.iloc[0])
            if "Total Debt" in debt_candidates:
                total_debt = debt_candidates["Total Debt"]
            elif debt_candidates:
                total_debt = sum(debt_candidates.values())
    
# Currency Pull
        currency = company.info['currency']

# Risk Free Rate Fetch from def
        try:
            risk_free_rate = get_risk_free_rate_fred(series_id="DGS10")
        except Exception:
            risk_free_rate = 0.03
            print(f"Warning: Could not fetch risk free rate from FRED. Setting to default 3% for ticker {ticker}.") 

                    
        return {
            "ticker": ticker.upper(),
            "company_name": info.get("longName", "N/A"),
            "revenue": revenue,
            "ebitda": ebitda,
            "net_income": net_income,
            "depreciation_amortization": depreciation_amortization,
            "capital_expenditures": capital_expenditures,
            "net_working_capital": net_working_capital,
            "income_tax_expense": income_tax_expense,
            "pre_tax_income": pre_tax_income,
            "interest_expense": interest_expense,
            "total_debt": total_debt,
            "market_cap": info.get("marketCap",0) or 0,
            "beta": info.get("beta", 0) or 0,
            "financials": financials,
            "cashflow": cashflow,
            "balance_sheet": balance_sheet,
            "tax_rate_est": tax_rate_est,
            "risk_free_rate": risk_free_rate,
            "currency": currency,
        } 
    
    except Exception as e:
        print({"error": f"Could not fetch data for ticker {ticker}: {str(e)}"})
        return None
    

def create_assumptions_from_ticker(ticker):

    # fetches company data and models it as assumptions
    data = get_company_financials(ticker)
    if not data:
        return None
    
    # metadata for display
    metadata = {
        "ticker": data["ticker"],
        "company_name": data["company_name"],
        "currency": data["currency"],
    }
    
    revenue = float(data.get("revenue", 0) or 0)
    ebitda = float(data.get("ebitda", 0) or 0)
    da = float(data.get("depreciation_amortization", 0) or 0)
    capex = float(data.get("capital_expenditures", 0) or 0)
    nwc = float(data.get("net_working_capital", 0) or 0)
    tax_rate = float(data.get("tax_rate_est", 0) or 0.25)
    market_cap = float(data.get("market_cap", 0) or 0)
    total_debt = float(data.get("total_debt", 0) or 0)
    interest_expense = float(data.get("interest_expense", 0) or 0)
    beta = float(data.get("beta", 0) or 0)
    risk_free_rate = float(data.get("risk_free_rate", 0.03) or 0.03)

    if revenue <= 0:
        return {"error": f"Insufficient revenue data for ticker {ticker}. Cannot build assumptions."}
    
    # format for model.py
    assumptions = {
        "revenue0": revenue,
        "ebitda_margin": (ebitda / revenue) if revenue != 0 else 0.25,
        "da_pct_revenue": (da / revenue) if revenue != 0 else 0.05,
        "capex_pct_revenue": (capex / revenue) if revenue != 0 else 0.05,
        "nwc_pct_revenue": (nwc / revenue) if revenue != 0 else 0.02,
        "tax_rate": tax_rate,
        "market_cap": market_cap,
        "total_debt": total_debt,
        "interest_expense": interest_expense,
        "beta": beta,
        "risk_free_rate": risk_free_rate,
    }

    return metadata, assumptions

# Fetch raw statements

def fetch_statements_raw(ticker:str, period: str = "annual") -> dict:
    t = yf.Ticker(ticker)

    if period == "quarterly":
        income_statement = getattr(t, "quarterly_financials", pd.DataFrame())
        balance_sheet = getattr(t, "quarterly_balance_sheet", pd.DataFrame())
        cashflow_statement = getattr(t, "quarterly_cashflow", pd.DataFrame())
    else:
        income_statement = getattr(t, "financials", pd.DataFrame())
        balance_sheet = getattr(t, "balance_sheet", pd.DataFrame())
        cashflow_statement = getattr(t, "cashflow", pd.DataFrame())

    info = getattr(t, "info", {}) or {}
    company_name = info.get("longName", "N/A"), info.get("shortName", "N/A")
    currency = info.get("currency", "N/A")

    return {
        "meta": {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "currency": currency,
            "source": "yfinance",
            "period": period,
        },
        "statements": {
            "income_statement": income_statement if isinstance(income_statement, pd.DataFrame) else pd.DataFrame(),
            "balance_sheet": balance_sheet if isinstance(balance_sheet, pd.DataFrame) else pd.DataFrame(),
            "cashflow_statement": cashflow_statement if isinstance(cashflow_statement, pd.DataFrame) else pd.DataFrame(),
        }
    }


if __name__ == "__main__":
    print(f"get_company_financials: {get_company_financials('AAPL')}")

