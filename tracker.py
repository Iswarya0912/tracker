import streamlit as st
import pandas as pd
from datetime import datetime, date
from dateutil import parser
import plotly.express as px
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
import hashlib
import os

# -----------------------
# Database helpers
# -----------------------
DB_NAME = "expenses.db"

def get_engine():
    return create_engine(f"sqlite:///{DB_NAME}", connect_args={"check_same_thread": False})

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def get_user_id(username: str):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id FROM users WHERE username=:u"), {"u": username}).fetchone()
        return result[0] if result else None

def init_db():
    engine = get_engine()
    with engine.connect() as conn:
        # Create users table if not exists
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """))
        # Create expenses table if not exists
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            category TEXT
            -- user_id will be added below if missing
        )
        """))
        # Check if user_id column exists, add if missing
        res = conn.execute(text("PRAGMA table_info(expenses)")).fetchall()
        colnames = [r[1] for r in res]
        if "user_id" not in colnames:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN user_id INTEGER"))
    return engine

engine = init_db()

# -----------------------
# Categorization logic
# -----------------------
DEFAULT_CATEGORIES = [
    "Food", "Transport", "Groceries", "Entertainment", "Bills",
    "Shopping", "Health", "Education", "Rent", "Misc"
]

KEYWORD_CATEGORY_MAP = {
    "uber": "Transport", "taxi": "Transport", "bus": "Transport", "fuel": "Transport",
    "coffee": "Food", "restaurant": "Food", "dinner": "Food", "lunch": "Food", "breakfast": "Food",
    "grocery": "Groceries", "supermarket": "Groceries", "walmart": "Groceries",
    "netflix": "Entertainment", "movie": "Entertainment", "spotify": "Entertainment",
    "electricity": "Bills", "water": "Bills", "internet": "Bills", "bill": "Bills",
    "shirt": "Shopping", "amazon": "Shopping", "flipkart": "Shopping", "buy": "Shopping",
    "doctor": "Health", "hospital": "Health", "medicine": "Health",
    "tuition": "Education", "course": "Education", "books": "Education",
    "rent": "Rent"
}

def auto_categorize(description: str) -> str:
    desc = (description or "").lower()
    for kw, cat in KEYWORD_CATEGORY_MAP.items():
        if kw in desc:
            return cat
    return "Misc"

# -----------------------
# Data operations
# -----------------------
def add_expense(dt: str, amount: float, description: str, category: str, user_id: int):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO expenses (dt, amount, description, category, user_id) VALUES (:dt,:amount,:desc,:cat,:uid)"),
            {"dt": dt, "amount": amount, "desc": description, "cat": category, "uid": user_id}
        )

def fetch_expenses(start_date=None, end_date=None, user_id=None):
    engine = get_engine()
    query = "SELECT id, dt, amount, description, category FROM expenses WHERE user_id=:uid"
    params = {"uid": user_id}
    if start_date and end_date:
        query += " AND date(dt) BETWEEN :start AND :end"
        params.update({"start": start_date, "end": end_date})
    df = pd.read_sql_query(text(query), engine, params=params)
    if not df.empty:
        df['dt'] = pd.to_datetime(df['dt'])
        df = df.sort_values('dt', ascending=False)
    return df

def export_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode('utf-8')

# -----------------------
# Authentication helpers
# -----------------------
def register_user(username: str, password: str) -> bool:
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"),
                {"u": username, "p": hash_password(password)}
            )
        return True
    except IntegrityError:
        return False

def authenticate_user(username: str, password: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT password_hash FROM users WHERE username=:u"),
            {"u": username}
        ).fetchone()
        if result and verify_password(password, result[0]):
            return True
    return False

# -----------------------
# Session state for login
# -----------------------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = None
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None

def logout():
    st.session_state['logged_in'] = False
    st.session_state['username'] = None
    st.session_state['user_id'] = None

def login_form():
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            if authenticate_user(username, password):
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['user_id'] = get_user_id(username)
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

def register_form():
    st.subheader("Register")
    with st.form("register_form"):
        username = st.text_input("Username", key="reg_user")
        password = st.text_input("Password", type="password", key="reg_pass")
        confirm = st.text_input("Confirm Password", type="password", key="reg_conf")
        submit = st.form_submit_button("Register")
        if submit:
            if not username or not password:
                st.error("Username and password required.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif register_user(username, password):
                st.success("Registration successful! Please login.")
            else:
                st.error("Username already exists.")

# -----------------------
# Streamlit App
# -----------------------
st.set_page_config(page_title="Smart Expense App", layout="wide", page_icon="💸")
st.title("💸 Smart Expense Tracker App")

if not st.session_state['logged_in']:
    menu = ["Login", "Register"]
    choice = st.sidebar.selectbox("Navigate", menu)
    if choice == "Login":
        login_form()
    elif choice == "Register":
        register_form()
    st.stop()
else:
    st.sidebar.write(f"Logged in as: {st.session_state['username']}")
    if st.sidebar.button("Logout"):
        logout()
        st.rerun()

# Sidebar navigation (after login)
menu = ["Home", "Add Expense", "View & Export", "Visualizations", "Bulk Import", "Admin"]
choice = st.sidebar.selectbox("Navigate", menu)

# -----------------------
# Home
# -----------------------
if choice == "Home":
    st.subheader("Welcome!")
    st.markdown("Use the sidebar to navigate through the app.")
    df_all = fetch_expenses(user_id=st.session_state['user_id'])
    total = df_all['amount'].sum() if not df_all.empty else 0.0
    st.metric("Total Expenses", f"₹{total:,.2f}")
    month_start = date.today().replace(day=1).strftime("%Y-%m-%d")
    month_end = date.today().strftime("%Y-%m-%d")
    df_month = fetch_expenses(month_start, month_end, user_id=st.session_state['user_id'])
    month_total = df_month['amount'].sum() if not df_month.empty else 0.0
    st.metric(f"Expenses This Month", f"₹{month_total:,.2f}")

# -----------------------
# Add Expense
# -----------------------
elif choice == "Add Expense":
    st.subheader("Add New Expense")
    with st.form("add_expense_form", clear_on_submit=True):
        dt_input = st.date_input("Date", value=date.today())
        amount_input = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
        description_input = st.text_input("Description", "")
        suggested_category = auto_categorize(description_input)
        category_input = st.selectbox("Category (suggested)", options=DEFAULT_CATEGORIES,
                                      index=(DEFAULT_CATEGORIES.index(suggested_category)
                                             if suggested_category in DEFAULT_CATEGORIES else len(DEFAULT_CATEGORIES)-1))
        submitted = st.form_submit_button("Add Expense")
        if submitted:
            dt_str = datetime.combine(dt_input, datetime.min.time()).strftime("%Y-%m-%d")
            if amount_input <= 0:
                st.error("Amount should be greater than 0.")
            else:
                add_expense(dt_str, float(amount_input), description_input.strip(), category_input, st.session_state['user_id'])
                st.success("Expense added ✅")

# -----------------------
# View & Export
# -----------------------
elif choice == "View & Export":
    st.subheader("View Expenses")
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start date", value=(date.today().replace(day=1)))
    with col2:
        end_date = st.date_input("End date", value=date.today())
    with col3:
        text_search = st.text_input("Search description/category", "")

    if start_date > end_date:
        st.error("Start date cannot be after end date.")
    else:
        df_view = fetch_expenses(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), user_id=st.session_state['user_id'])
        if not df_view.empty and text_search.strip():
            mask = df_view['description'].str.contains(text_search, case=False, na=False) | \
                   df_view['category'].str.contains(text_search, case=False, na=False)
            df_view = df_view[mask]
        st.dataframe(df_view.reset_index(drop=True))
        if not df_view.empty:
            csv_bytes = export_csv(df_view)
            st.download_button("Download CSV", data=csv_bytes, file_name=f"expenses_{start_date}_{end_date}.csv", mime="text/csv")

# -----------------------
# Visualizations
# -----------------------
elif choice == "Visualizations":
    st.subheader("Visualizations")
    start_date = date.today().replace(day=1)
    end_date = date.today()
    viz_df = fetch_expenses(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), user_id=st.session_state['user_id'])
    if viz_df.empty:
        st.info("No data for visualizations.")
    else:
        cat_summary = viz_df.groupby('category')['amount'].sum().reset_index().sort_values('amount', ascending=False)
        fig_pie = px.pie(cat_summary, names='category', values='amount', title="Spending by Category")
        st.plotly_chart(fig_pie, use_container_width=True)

        viz_df['date_only'] = viz_df['dt'].dt.date
        daily_summary = viz_df.groupby('date_only')['amount'].sum().reset_index()
        fig_bar = px.bar(daily_summary, x='date_only', y='amount', title="Daily Spending", labels={'date_only':'Date','amount':'Amount (₹)'})
        st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------
# Bulk Import
# -----------------------
elif choice == "Bulk Import":
    st.subheader("Bulk CSV Import")
    st.markdown("Upload CSV with columns: `dt` (YYYY-MM-DD), `amount`, `description`, optional `category`.")
    uploaded = st.file_uploader("Upload CSV to import", type=["csv"])
    if uploaded is not None:
        try:
            csv_df = pd.read_csv(uploaded)
            required_cols = {"dt","amount","description"}
            if not required_cols.issubset(set(csv_df.columns.str.lower())):
                st.error("CSV must contain dt, amount, description columns")
            else:
                csv_df.columns = [c.lower() for c in csv_df.columns]
                inserted = 0
                for _, row in csv_df.iterrows():
                    try:
                        dt_val = row.get("dt")
                        amt = float(row.get("amount",0))
                        desc = str(row.get("description",""))
                        cat = row.get("category") if "category" in csv_df.columns else None
                        if pd.isna(cat) or not cat:
                            cat = auto_categorize(desc)
                        dt_parsed = parser.parse(dt_val).date().strftime("%Y-%m-%d")
                        if amt>0:
                            add_expense(dt_parsed, amt, desc, cat, st.session_state['user_id'])
                            inserted += 1
                    except Exception:
                        continue
                st.success(f"Imported {inserted} records successfully.")
        except Exception as e:
            st.error(f"Failed to import CSV: {e}")

# -----------------------
# Admin / Clear Data
# -----------------------
elif choice == "Admin":
    st.subheader("⚠️ Admin / Data Management")

    # Clear all data
    st.markdown("### Clear All Expenses")
    if st.button("Clear ALL Expenses"):
        confirm = st.checkbox("Confirm deletion")
        if confirm:
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM expenses WHERE user_id=:uid"), {"uid": st.session_state['user_id']})
            st.success("All your expense records cleared.")
        else:
            st.info("Check the box to confirm deletion.")

    # Clear by date range
    st.markdown("### Delete Expenses by Date Range")
    start_del = st.date_input("Start date", key="start_del")
    end_del = st.date_input("End date", key="end_del")
    if st.button("Delete Selected Range"):
        if start_del > end_del:
            st.error("Start date cannot be after end date.")
        else:
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM expenses WHERE user_id=:uid AND date(dt) BETWEEN :start AND :end"),
                    {"uid": st.session_state['user_id'], "start": start_del.strftime("%Y-%m-%d"), "end": end_del.strftime("%Y-%m-%d")}
                )
            st.success(f"Your expenses from {start_del} to {end_del} deleted.")
