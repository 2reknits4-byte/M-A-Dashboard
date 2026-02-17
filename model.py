import pandas as pd
import numpy as np

# Data_fetched from Yahoo Finance
# Tax Rate Calc

def forecast_fcff(
    revenue0: float,
    years: int,
    revenue_growth: float,
    ebitda_margin: float,
    da_pct_revenue: float,
    capex_pct_revenue: float,
    nwc_pct_revenue: float,
    tax_rate: float,
) -> pd.DataFrame:
    year = np.arange(1, years + 1)
    revenue = revenue0 * (1 + revenue_growth) ** year
    ebitda = revenue * ebitda_margin
    da = revenue * da_pct_revenue
    ebit = ebitda - da
    taxes = np.maximum(ebit,0) * tax_rate
    nopat = ebit - taxes
    capex = revenue * capex_pct_revenue
    nwc = revenue * nwc_pct_revenue

    nwc0 = revenue0 * nwc_pct_revenue
    delta_nwc = np.empty(years)
    delta_nwc[0] = nwc[0] - nwc0
    delta_nwc[1:] = nwc[1:] - nwc[:-1]

    fcff = nopat + da - capex - delta_nwc

    return pd.DataFrame({
        "Year": year,
        "Revenue": revenue,
        "EBITDA": ebitda,
        "D&A": da,
        "EBIT": ebit,
        "Taxes": taxes,
        "NOPAT": nopat,
        "CapEx": capex,
        "NWC": nwc,
        "ΔNWC": delta_nwc,
        "FCFF": fcff,
    })

def dcf_valuation(fcff_forecast: pd.DataFrame, wacc: float, exit_multiple: float) -> dict:
    fcff = fcff_forecast["FCFF"].values
    ebitda_exit = float(fcff_forecast["EBITDA"].iloc[-1])

    t = np.arange(1, len(fcff) + 1)
    discount_factors = 1 / (1 + wacc) ** t

    pv_fcff = float((fcff * discount_factors).sum())
    terminal_value = ebitda_exit * exit_multiple
    pv_terminal = float(terminal_value / (1 + wacc) ** len(fcff))
    enterprise_value = pv_fcff + pv_terminal

    return {
        "PV_FCFF": pv_fcff,
        "Terminal_Value": float(terminal_value),
        "PV_Terminal": pv_terminal,
        "Enterprise_Value": enterprise_value,
    }

def compute_wacc(
        market_cap, 
        total_debt,
        interest_expense,
        beta, 
        tax_rate,
        risk_free_rate,
        erp = 0.055,       # Assumed Equity Risk Premium...Add slider for this
):
    if market_cap <= 0:
        raise ValueError("Market cap must be positive")
    
    E = float(market_cap)
    D = float(max(total_debt or 0, 0))
    V = E + D

    if V <= 0:
        raise ValueError("Total Capital (E + D) must be positive.")

    cost_of_equity = float(risk_free_rate) + float(beta) * float(erp)

    if D > 0 and interest_expense:
        cost_of_debt = abs(float(interest_expense)) / D
    else:
        cost_of_debt = 0.0
        print("Warning: No debt found, setting cost of debt to 0 assuming all-equity financing.")
    
    tax_rate = min(max(float(tax_rate), 0.0), 0.5)

    wacc = ((E/V) * cost_of_equity + (D/V) * cost_of_debt * (1- tax_rate))

    return {
        "WACC": wacc,
        "Cost_of_Equity": cost_of_equity,
        "Cost_of_Debt": cost_of_debt,
        "Equity_Weight": E/V,
        "Debt_Weight": D/V,
        "wacc_Enterprise_Value": V,
    }

# Uses compute_wacc() but allows weight override from the user then recalculates weights and WACC to keep app.py clean
def wacc_compute_weight_ovrride(
        market_cap,
        total_debt,
        interest_expense,
        beta,
        tax_rate,
        risk_free_rate,
        erp= 0.055,
        equity_weight_override=None,
):
    base = compute_wacc(
        market_cap=market_cap,
        total_debt=total_debt,
        interest_expense=interest_expense,
        beta=beta,
        tax_rate=tax_rate,
        risk_free_rate=risk_free_rate,
        erp=erp,
    )

    if equity_weight_override is None:
        return base
    
    ew = float(equity_weight_override)
    ew = min(max(ew, 0.0), 1.0)

    V = float(base["wacc_Enterprise_Value"])
    E_new = V * ew
    D_new = V * (1.0 - ew)

    overriden = compute_wacc(
        market_cap = E_new,
        total_debt = D_new,
        interest_expense=interest_expense,
        beta=beta,
        tax_rate=tax_rate,
        risk_free_rate=risk_free_rate,
        erp=erp,
    )

    overriden["Base_Equity_Weight"] = base["Equity_Weight"]
    overriden["Base_Debt_Weight"] = base["Debt_Weight"]
    overriden["Base_Enterprise_Value"] = base["wacc_Enterprise_Value"]
    
    return overriden

if __name__ == "__main__":
    # Optional quick test (won't run when imported by Streamlit)
    fcff_forecast = forecast_fcff(
        revenue0=5_000,
        years=5,
        revenue_growth=0.06,
        ebitda_margin=0.22,
        da_pct_revenue=0.03,
        capex_pct_revenue=0.04,
        nwc_pct_revenue=0.10,
        tax_rate=0.25,
    )
    print(dcf_valuation(fcff_forecast, wacc=0.09, exit_multiple=8.0))
