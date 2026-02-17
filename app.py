import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

#imports calculations from model.py
from model import forecast_fcff, dcf_valuation
from model import compute_wacc
from model import wacc_compute_weight_ovrride

#import data fetched assumptions and raw statements
from data_fetcher import create_assumptions_from_ticker, fetch_statements_raw

# Streamlit page config
st.set_page_config(page_title="MNA Dashboard", layout="wide")
st.title("Mergers & Acquisitions Financial Dashboard")


# AI Helper Placeholder for every Tab
def ai_summary_block(tab_name: str):
    # Placeholder for AI-generated summary
    st.markdown("### AI Summary")
    st.info(
        f"[{tab_name}] AI-generated summary will be displayed here."
    )


# Initialize session state for assumptions
if "assump" not in st.session_state:
    st.session_state.assump = {
        "revenue0": 100_000_000.0,
        "revenue_growth": 0.06,
        "years": 5,
        "ebitda_margin": 0.25,
        "da_pct_revenue": 0.05,
        "capex_pct_revenue": 0.05,
        "nwc_pct_revenue": 0.02,
        "tax_rate": 0.25,
        "wacc": 0.10,
        "exit_multiple": 8.0,
        "equity_risk_premium": 0.055,
    }
assump = st.session_state.assump

# Initiallize session state for raw financials
if "financials_raw" not in st.session_state:
    st.session_state.financials_raw = None

# Initialize session state for financial statement period
if "statement_period" not in st.session_state:
    st.session_state.statement_period = "annual"

# Initialize sessions state for WACC slider overrides
if "wacc_slider" not in st.session_state:
    st.session_state.wacc_slider = 0.10 # Default WACC until ticker is loaded

if "fcff_forecast" not in st.session_state:    # Persist session states across runs
    st.session_state.fcff_forecast = None

if "val" not in st.session_state:
    st.session_state.val = None

# Ticker Input in Sidebar
st.sidebar.header("Load Company (Ticker)")
ticker = st.sidebar.text_input("Enter Ticker", value="AAPL")

if st.sidebar.button("Load Ticker Data"):
    fetched = create_assumptions_from_ticker(ticker)

    if fetched is None:
        st.sidebar.error(f"Could not be fetched for ticker {ticker}. Please check the ticker symbol.")
    elif isinstance(fetched, dict) and "error" in fetched:
        st.sidebar.error(fetched["error"])
    else:
        meta, fetched_assump = fetched  # <- correct unpack

        # mutate the session-state dict directly
        assump.update(fetched_assump)

        assump = st.session_state.assump

        # Update WACC slider default
        wacc_base = compute_wacc(
            market_cap = assump["market_cap"],
            total_debt = assump["total_debt"],
            interest_expense = assump.get("interest_expense", 0.0),
            beta = assump["beta"],
            tax_rate = assump.get("tax_rate", 0.25),
            risk_free_rate = assump.get("risk_free_rate", 0.03),
            erp = assump.get("equity_risk_premium", 0.055),
        )
        # Set the WACC in assumptions
        st.session_state.wacc_slider = float(wacc_base["WACC"])

        # store metadata for display
        st.session_state.company_meta = meta

        # Fetch raw financial statements for Core Financials tab
        try:
            st.session_state.financials_raw = fetch_statements_raw(ticker, period=st.session_state.statement_period)
        except Exception as e:
            st.session_state.financials_raw = None
            st.sidebar.warning(f"Could not fetch full financial statements: {e}")

        st.sidebar.success(f"Loaded data for {meta['company_name']} ({meta['ticker']})")

#Subheader for WACC and CAPM
st.sidebar.subheader("WACC and CAPM Assumptions")
# Keep assumption of ERP as 5.5%
equity_risk_premium = st.sidebar.slider(
    "Equity Risk Premium (ERP)",
    min_value = 0.03,
    max_value = 0.08,
    value = float(assump.get("equity_risk_premium", 0.055)),
    step = 0.005,
    format = "%.3f",
    )
wacc_base = wacc_compute_weight_ovrride(
    market_cap = assump["market_cap"],
    total_debt = assump["total_debt"],
    interest_expense = assump.get("interest_expense", 0.0),
    beta = assump["beta"],
    tax_rate = assump.get("tax_rate", 0.25),
    risk_free_rate = assump.get("risk_free_rate", 0.03),
    erp = equity_risk_premium,
)
default_equity_weight = float(wacc_base["Equity_Weight"])

equity_weight = st.sidebar.slider(
    "Equity Weight (E/V)",
    0.0, 1.0,
    value = default_equity_weight,
    step = 0.05
)

wacc_out = wacc_compute_weight_ovrride(
    market_cap = assump["market_cap"],
    total_debt = assump["total_debt"],
    interest_expense = assump.get("interest_expense", 0.0),
    beta = assump["beta"],
    tax_rate = assump.get("tax_rate", 0.25),
    risk_free_rate = assump.get("risk_free_rate", 0.03),
    erp = equity_risk_premium,
    equity_weight_override = equity_weight,
)

wacc = float(wacc_out["WACC"])
assump["wacc"] = wacc

#Sidebar for Sim
st.sidebar.header("Simulation Assumptions")
a = st.session_state.assump

a["revenue0"] = st.sidebar.number_input("Initial Revenue", value=float(a["revenue0"]))

a["years"] = st.sidebar.number_input("Forecast Years", value=int(a["years"]), min_value=1, max_value=20)

a["revenue_growth"] = st.sidebar.slider("Revenue Growth Rate", min_value=0.0, max_value=0.5, value=float(a["revenue_growth"]), step=0.01)

a["ebitda_margin"] = st.sidebar.slider("EBITDA Margin", min_value=0.0, max_value=1.0, value=float(a["ebitda_margin"]), step=0.01)

a["wacc"] = st.sidebar.slider("WACC", min_value=0.0, max_value=0.5, value=float(a["wacc"]), step=0.005)

a["exit_multiple"] = st.sidebar.number_input("Exit Multiple", value=float(a["exit_multiple"]))

#Run calc
if st.sidebar.button("Run Simulation"):
    try:    
            #Operating CF Forecast
            a = st.session_state.assump

            fcff_forecast = forecast_fcff(
                revenue0=a["revenue0"],
                years=a["years"],
                revenue_growth=a["revenue_growth"],
                ebitda_margin=a["ebitda_margin"],
                da_pct_revenue=a["da_pct_revenue"],
                capex_pct_revenue=a["capex_pct_revenue"],
                nwc_pct_revenue=a["nwc_pct_revenue"],
                tax_rate=a["tax_rate"],
                )
            
            # Computed WACC from ticker data
            a["wacc"] = wacc

            # DCF Valuation
            val = dcf_valuation(
                fcff_forecast=fcff_forecast,
                wacc=float(a["wacc"]),
                exit_multiple=float(a["exit_multiple"]),
                )
            
            st.session_state.fcff_forecast = fcff_forecast
            st.session_state.val = val
    except Exception as e:
        st.error(f"Simulation failed: {e}")
        st.exception(e)

# Always-available aliases for tab rendering
company_meta = st.session_state.get("company_meta")
fcff_forecast = st.session_state.get("fcff_forecast")
val = st.session_state.get("val")

# Create Tabs
tab_home, tab_core, tab_forecast, tab_sens, tab_mna = st.tabs([
    "Home",
    "Core Financials",
    "FCFF Forecast",
    "Sensitivity Index",
    "M&A Deal",
])

if st.session_state.fcff_forecast is not None and st.session_state.val is not None:
# ---------------------------
# TAB 1: Home
# ---------------------------   
    with tab_home:
        st.subheader("Company Loader")

        # AI summary on this tab too (optional)
        ai_summary_block("Home")

        st.markdown("### Current Company")
        if company_meta:
            c1, c2, c3 = st.columns(3)
            c1.metric("Company", company_meta.get("company_name", "—"))
            c2.metric("Ticker", company_meta.get("ticker", "—"))
            c3.metric("Currency", company_meta.get("currency", "—"))

            st.markdown("### Snapshot")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Revenue (Latest)", f"${assump.get('revenue0', 0):,.0f}")
            s2.metric("Market Cap", f"${assump.get('market_cap', 0):,.0f}")
            s3.metric("Total Debt", f"${assump.get('total_debt', 0):,.0f}")
            s4.metric("WACC", f"{assump.get('wacc', 0):.2%}")

            st.success("Use the tabs above to explore financials, forecast, and sensitivity.")
        else:
            st.info("Load a ticker from the sidebar to begin.")

# ---------------------------
# TAB 2: Core Financials
# ---------------------------
    with tab_core:
        st.subheader("Core Financials")

        # AI summary on this tab
        ai_summary_block("Core Financials")

        # Guard: require ticker load
        if not st.session_state.get("company_meta"):
            st.info("Load a ticker in the sidebar to view core financials.")
        elif not st.session_state.get("financials_raw"):
            st.warning("Ticker loaded, but full financial statements could not be fetched.")
        else:
            fin = st.session_state["financials_raw"]
            meta = fin.get("meta", {})
            
           # Annual / Quarterly Button Toggle 
            period_label = st.radio(
                "Statement Period",
                options=["Annual", "Quarterly"],
                index=0 if st.session_state.statement_period == "annual" else 1,
                horizontal=True,
            )
            period = period_label.lower()

            # If user changes period, refetch statements
            if period != st.session_state.statement_period:
                st.session_state.statement_period = period

                try:
                    st.session_state.financials_raw = fetch_statements_raw(
                        st.session_state.company_meta["ticker"],
                        period=period,
                    )
                    st.rerun()
                    fin = st.session_state["financials_raw"]
                    meta = fin.get("meta", {})
                except Exception as e:
                    st.session_state.financials_raw = None
                    st.warning(f"Could not fetch {period} statements: {e}")

            st.caption(f"{meta.get('company_name', '-')} ({meta.get('ticker', '-')}) | {meta.get('currency', '-')} | {period}")
            stmts = fin.get("statements", {})

            with st.expander("Income Statement", expanded = True):
                st.dataframe(stmts.get("income_statement", pd.DataFrame()), use_container_width=True)
            
            with st.expander("Balance Sheet", expanded = False):
                st.dataframe(stmts.get("balance_sheet", pd.DataFrame()), use_container_width=True)
            
            with st.expander("Cash Flow Statement", expanded = False):
                st.dataframe(stmts.get("cashflow_statement", pd.DataFrame()), use_container_width=True)

            st.info(
                "Core Financials tab is ready.\n\n"
                "Next step: fetch full Income Statement / Balance Sheet / Cash Flow "
                "and store them in session_state (e.g., st.session_state.financials_raw)."
            )

            # Optional: show whatever you already have (snapshot assumptions from ticker)
            st.markdown("### Snapshot (from ticker-seeded assumptions)")
            snap_cols = st.columns(4)
            snap_cols[0].metric("Market Cap", f"${assump.get('market_cap', 0):,.0f}")
            snap_cols[1].metric("Total Debt", f"${assump.get('total_debt', 0):,.0f}")
            snap_cols[2].metric("Beta", f"{assump.get('beta', 0):.2f}")
            snap_cols[3].metric("Risk-Free Rate", f"{assump.get('risk_free_rate', 0):.2%}")


    # ---------------------------
    # TAB 3: FCFF Forecast (move your existing FCFF table + chart + valuation here)
    # ---------------------------
    with tab_forecast:
        st.subheader("FCFF Forecast")

        # AI summary on this tab
        ai_summary_block("FCFF Forecast")

        # Guard: require simulation run
        if fcff_forecast is None or val is None:
            st.warning("Run the simulation in the sidebar to view forecast and valuation.")
        else:
            # ---- Move your existing "Deal Assumptions" display here ----
            st.markdown("### Deal Assumptions")
            col1, col2, col3 = st.columns(3)
            col1.metric("Initial Revenue", f"${assump['revenue0']:,.2f}")
            col2.metric("Revenue Growth Rate", f"{assump['revenue_growth']*100:.2f}%")
            col3.metric("EBITDA Margin", f"{assump['ebitda_margin']*100:.2f}%")

            # ---- Move your FCFF Forecast table here ----
            st.markdown("### FCFF Forecast")
            st.dataframe(fcff_forecast.round(2), use_container_width=True)

            # ---- Move your FCFF chart here ----
            st.markdown("### FCFF Forecast Chart")

            # Prep data for Altair (keep your y-axis scaling logic)
            chart_df = fcff_forecast.reset_index(drop=True).copy()
            chart_df["Year"] = range(1, len(chart_df) + 1)

            fcff_min = chart_df["FCFF"].min()
            fcff_max = chart_df["FCFF"].max()
            padding = 0.10 * (fcff_max - fcff_min) if (fcff_max - fcff_min) != 0 else 1e-6
            y_min = fcff_min - padding
            y_max = fcff_max + padding

            fcff_chart = (
                alt.Chart(chart_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("Year:Q", title="Forecasted Year"),
                    y=alt.Y("FCFF:Q", title="FCFF (USD)", scale=alt.Scale(domain=[y_min, y_max])),
                    tooltip=[
                        alt.Tooltip("Year:Q", title="Year"),
                        alt.Tooltip("FCFF:Q", title="FCFF", format=",.0f")
                    ],
                )
            )
            st.altair_chart(fcff_chart, use_container_width=True)

            # ---- Move your Valuation Summary display here ----
            st.markdown("### Valuation Summary")
            col1, col2, col3 = st.columns(3)
            col1.metric("PV of FCFF", f"${val['PV_FCFF']:,.2f}")
            col2.metric("PV of Terminal Value", f"${val['PV_Terminal']:,.2f}")
            col3.metric("Enterprise Value", f"${val['Enterprise_Value']:,.2f}")


    # ---------------------------
    # TAB 4: Sensitivity Index (placeholder for now)
    # ---------------------------
    with tab_sens:
        st.subheader("Sensitivity Index")

        # AI summary on this tab
        ai_summary_block("Sensitivity Index")

        if fcff_forecast is None or val is None:
            st.warning("Run the simulation in the sidebar first.")
        else:
            st.info(
                "Sensitivity tab skeleton is ready.\n\n"
                "Next step: build WACC x Exit Multiple and Growth x Margin sensitivity tables in model.py,\n"
                "store them in session_state.model_outputs, and render them here."
            )


    # ---------------------------
    # TAB 5: M&A Deal (placeholder; you said separate page earlier, but you can do it as a tab)
    # ---------------------------
    with tab_mna:
        st.subheader("M&A Deal (Acquirer vs Target)")

        # AI summary on this tab
        ai_summary_block("M&A Deal")

        st.info(
            "M&A tab skeleton is ready.\n\n"
            "Next step: add a second ticker input (target) + deal assumptions (premium/synergy/financing),\n"
            "then compute: standalone EVs + synergy NPV + max premium / recommendation."
        )
    
        

    