"""Personal Gmail Analysis Assistant - Local Streamlit Dashboard.

Run with:
  streamlit run app.py
"""

from datetime import datetime
from typing import List, Optional
import pandas as pd
import streamlit as st

from src.config import get_settings
from src.db import DatabaseManager
from src.models import JobEventType, ReviewStatus

# Page configuration with clean modern layout
st.set_page_config(
    page_title="Personal Gmail Analysis Assistant",
    page_icon="📬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern card aesthetics and badges
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; }
    .stMetric {
        background-color: #ffffff;
        padding: 18px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
    }
    .badge-review {
        background-color: #fef3c7;
        color: #92400e;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .badge-ok {
        background-color: #d1fae5;
        color: #065f46;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .badge-category {
        background-color: #e0e7ff;
        color: #3730a3;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .tx-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_db() -> DatabaseManager:
    """Retrieve shared DatabaseManager instance."""
    settings = get_settings()
    return DatabaseManager(db_path=settings.database_path)


def make_gmail_url(message_id: str) -> str:
    """Construct direct link to open the original message in Gmail web interface."""
    return f"https://mail.google.com/mail/u/0/#all/{message_id}"


def render_sidebar():
    """Render sidebar navigation and quick system summary."""
    st.sidebar.title("📬 Mail Assistant")
    st.sidebar.caption("Private & Read-Only Email Intelligence")

    view = st.sidebar.radio(
        "Navigation",
        ["💳 Transactions", "📊 Spending Reports", "💼 Jobs & Interviews", "⚙️ Accounts & Status"],
        index=0,
    )

    st.sidebar.divider()
    settings = get_settings()
    summary = settings.sanitized_summary()
    st.sidebar.markdown(f"**Groq Model:** `{summary['groq_model']}`")
    st.sidebar.markdown(f"**Accounts:** {summary['configured_accounts_count']}")

    return view


def render_transactions_view(db: DatabaseManager):
    """View 1: Transactions review, filtering, and inline category editing."""
    st.title("💳 Credit Card Transactions")
    st.caption("Review extracted bank and credit card alerts. Edit spending hints to update spending reports.")

    # Top Filter Row
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        review_filter = st.selectbox(
            "Review Status",
            ["All", "Needs Review", "Reviewed"],
            index=0,
        )
    with col2:
        accounts = db.list_accounts()
        acct_options = ["All"] + [a.account_id for a in accounts]
        account_filter = st.selectbox("Account", acct_options, index=0)

    categories = db.list_categories()
    with col3:
        cat_options = ["All"] + categories
        category_filter = st.selectbox("Category Hint", cat_options, index=0)

    with col4:
        search_query = st.text_input("Search Merchant", placeholder="e.g. Trader Joe's")

    # Fetch transactions from DB
    status_arg = None
    if review_filter == "Needs Review":
        status_arg = ReviewStatus.NEEDS_REVIEW
    elif review_filter == "Reviewed":
        status_arg = ReviewStatus.REVIEWED

    acct_arg = None if account_filter == "All" else account_filter
    cat_arg = None if category_filter == "All" else category_filter

    tx_list = db.list_transactions(
        account_id=acct_arg,
        review_status=status_arg,
        category_hint=cat_arg,
        limit=200,
    )

    # Apply search filter in memory
    if search_query:
        tx_list = [t for t in tx_list if search_query.lower() in (t.merchant or "").lower()]

    # Summary metrics row
    st.divider()
    m1, m2, m3 = st.columns(3)
    total_spend = sum(t.amount or 0.0 for t in tx_list)
    needs_review_count = sum(1 for t in tx_list if t.review_status == ReviewStatus.NEEDS_REVIEW)

    m1.metric("Visible Transactions", len(tx_list))
    m2.metric("Total Sum", f"${total_spend:,.2f}")
    m3.metric("Awaiting Review", needs_review_count)

    st.write("")

    if not tx_list:
        st.info("No transactions found matching the selected filters. Run a scan via `python scripts/run_scan.py` to ingest new emails.")
        return

    # Add custom category widget
    with st.expander("➕ Add New Custom Category"):
        new_cat_name = st.text_input("New category name:", placeholder="e.g. medical, textbooks, shared dinner")
        if st.button("Add Category", key="add_cat_btn"):
            if new_cat_name:
                if db.add_category(new_cat_name):
                    st.success(f"Added '{new_cat_name.lower().strip()}'!")
                    st.rerun()
                else:
                    st.warning("Category already exists or invalid.")

    # Render Transaction Cards with Inline Category Hint Editor
    for tx in tx_list:
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 3, 2])

            with c1:
                st.markdown(f"**{tx.merchant or 'Unknown Merchant'}**")
                date_str = tx.transaction_date or "Unknown Date"
                card_str = f"• Card ...{tx.card_last_four}" if tx.card_last_four else ""
                st.caption(f"📅 {date_str} {card_str}")
                if tx.uncertainty_notes:
                    st.caption(f"⚠️ *{tx.uncertainty_notes}*")

            with c2:
                amt_str = f"${tx.amount:,.2f}" if tx.amount is not None else "Unknown"
                st.markdown(f"### {amt_str}")
                st.caption(f"Type: {tx.transaction_type.value.capitalize()}")

            with c3:
                # Review Status Badge
                if tx.review_status == ReviewStatus.NEEDS_REVIEW:
                    st.markdown("<span class='badge-review'>⚠️ Needs Review</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='badge-ok'>✅ Reviewed</span>", unsafe_allow_html=True)
                st.caption(f"Confidence: {int((tx.confidence_score or 1.0) * 100)}%")

            with c4:
                # Category selector
                curr_cat = tx.category_hint if tx.category_hint in categories else "uncategorized"
                cat_idx = categories.index(curr_cat) if curr_cat in categories else 0
                new_cat = st.selectbox(
                    "Spending Hint:",
                    categories,
                    index=cat_idx,
                    key=f"cat_select_{tx.id}",
                )
                if new_cat != tx.category_hint:
                    db.update_transaction_category(tx.id, new_cat, mark_reviewed=True)
                    st.rerun()

            with c5:
                # Actions & Gmail Link
                st.markdown(f"[🔗 View in Gmail]({make_gmail_url(tx.message_id)})")
                if tx.review_status == ReviewStatus.NEEDS_REVIEW:
                    if st.button("Mark Reviewed", key=f"mark_rev_{tx.id}"):
                        db.update_transaction_review_status(tx.id, ReviewStatus.REVIEWED)
                        st.rerun()
                else:
                    if st.button("Flag Review", key=f"flag_rev_{tx.id}"):
                        db.update_transaction_review_status(tx.id, ReviewStatus.NEEDS_REVIEW)
                        st.rerun()

            st.divider()


def render_spending_reports_view(db: DatabaseManager):
    """View 2: Spending Analytics, Monthly Trends, and Category Aggregations."""
    st.title("📊 Spending Reports & Analytics")
    st.caption("Summarized analytics driven by extracted transactions and your curated category hints.")

    summaries = db.get_spending_summaries()
    by_cat = summaries["by_category"]
    by_merch = summaries["by_merchant"]
    by_month = summaries["by_month"]

    if not by_cat and not by_merch and not by_month:
        st.info("No transaction data available to generate reports. Ingest emails first using `python scripts/run_scan.py`.")
        return

    # Total Overall Spend KPI
    total_amount = sum(c["total_amount"] or 0.0 for c in by_cat)
    total_tx_count = sum(c["count"] or 0 for c in by_cat)

    k1, k2, k3 = st.columns(3)
    k1.metric("Total Tracked Spending", f"${total_amount:,.2f}")
    k2.metric("Total Purchases / Debits", total_tx_count)
    k3.metric("Spending Categories Used", len(by_cat))

    st.divider()

    # Layout: Monthly Trends & Category Breakdown
    c_left, c_right = st.columns(2)

    with c_left:
        st.subheader("🗓️ Monthly Totals")
        if by_month:
            df_month = pd.DataFrame(by_month)
            df_month["total_amount"] = df_month["total_amount"].fillna(0.0)
            st.bar_chart(df_month.set_index("month")["total_amount"])
            st.dataframe(
                df_month.rename(columns={"month": "Month", "count": "Count", "total_amount": "Total ($)"}),
                use_container_width=True,
            )
        else:
            st.write("No monthly data available.")

    with c_right:
        st.subheader("🏷️ Spending by Category Hint")
        if by_cat:
            df_cat = pd.DataFrame(by_cat)
            df_cat["total_amount"] = df_cat["total_amount"].fillna(0.0)
            st.bar_chart(df_cat.set_index("category_hint")["total_amount"])
            st.dataframe(
                df_cat.rename(columns={"category_hint": "Category", "count": "Count", "total_amount": "Total ($)"}),
                use_container_width=True,
            )
        else:
            st.write("No category data available.")

    st.divider()

    # Top Merchants Table
    st.subheader("🏪 Top Merchants by Spend")
    if by_merch:
        df_merch = pd.DataFrame(by_merch)
        st.dataframe(
            df_merch.rename(columns={"merchant": "Merchant", "count": "Transactions", "total_amount": "Total Spent ($)"}),
            use_container_width=True,
        )


def render_jobs_view(db: DatabaseManager):
    """View 3: Job applications, interview schedule tracker, and status updates."""
    st.title("💼 Job Applications & Interview Schedule")
    st.caption("Structured tracking of job applications, interview invites, meeting links, and next steps.")

    # Filter by Event Type
    col1, col2 = st.columns([3, 2])
    with col1:
        event_types = ["All"] + [e.value for e in JobEventType if e != JobEventType.UNKNOWN]
        selected_type = st.selectbox("Event Type Filter", event_types, index=0)
    with col2:
        review_filter = st.selectbox("Status Filter", ["All", "Needs Review", "Reviewed"], index=0)

    type_arg = None
    if selected_type != "All":
        type_arg = JobEventType(selected_type)

    rev_arg = None
    if review_filter == "Needs Review":
        rev_arg = ReviewStatus.NEEDS_REVIEW
    elif review_filter == "Reviewed":
        rev_arg = ReviewStatus.REVIEWED

    job_events = db.list_job_events(event_type=type_arg, review_status=rev_arg, limit=100)

    # Metrics
    st.divider()
    j1, j2, j3 = st.columns(3)
    interview_count = sum(1 for j in job_events if j.event_type == JobEventType.INTERVIEW_INVITATION)
    offer_count = sum(1 for j in job_events if j.event_type == JobEventType.OFFER)

    j1.metric("Tracked Job Events", len(job_events))
    j2.metric("Interview Invitations", interview_count)
    j3.metric("Offers Received", offer_count)

    st.write("")

    if not job_events:
        st.info("No job events found matching filters. Run a scan on your job-hunting accounts to populate records.")
        return

    # Render Cards
    for job in job_events:
        with st.container():
            c1, c2, c3 = st.columns([4, 4, 3])

            with c1:
                st.markdown(f"### {job.company or 'Unknown Company'}")
                st.markdown(f"**Role:** {job.role_title or 'Unspecified Role'}")
                type_display = job.event_type.value.replace("_", " ").title()
                st.markdown(f"<span class='badge-category'>{type_display}</span>", unsafe_allow_html=True)

            with c2:
                if job.interview_datetime:
                    tz_str = f"({job.timezone})" if job.timezone else ""
                    st.markdown(f"⏰ **Interview:** `{job.interview_datetime} {tz_str}`")

                if job.meeting_link:
                    st.markdown(f"🎥 **Meeting Link:** [Join Call]({job.meeting_link})")

                if job.next_step:
                    st.markdown(f"👉 **Next Step:** {job.next_step}")

                if job.uncertainty_notes:
                    st.caption(f"⚠️ *{job.uncertainty_notes}*")

            with c3:
                # Review status and actions
                if job.review_status == ReviewStatus.NEEDS_REVIEW:
                    st.markdown("<span class='badge-review'>⚠️ Needs Review</span>", unsafe_allow_html=True)
                    if st.button("Confirm Details", key=f"conf_job_{job.id}"):
                        db.update_job_event_review_status(job.id, ReviewStatus.REVIEWED)
                        st.rerun()
                else:
                    st.markdown("<span class='badge-ok'>✅ Reviewed</span>", unsafe_allow_html=True)
                    if st.button("Flag for Review", key=f"flag_job_{job.id}"):
                        db.update_job_event_review_status(job.id, ReviewStatus.NEEDS_REVIEW)
                        st.rerun()

                st.markdown(f"[🔗 View in Gmail]({make_gmail_url(job.message_id)})")

            st.divider()


def render_accounts_view(db: DatabaseManager):
    """View 4: Connected accounts, checkpoints, and system configuration."""
    st.title("⚙️ Accounts & Ingestion Status")
    st.caption("Status of configured Gmail accounts, checkpoints, and safe operational parameters.")

    settings = get_settings()
    accounts = db.list_accounts()

    if not accounts:
        st.warning("No accounts found in the database. Run `python scripts/auth_and_test_gmail.py` to connect an account.")
    else:
        account_rows = []
        for a in accounts:
            account_rows.append({
                "Account ID": a.account_id,
                "Email": a.email,
                "Type": a.account_type.capitalize(),
                "Last Checkpoint": a.last_scan_timestamp or "Never scanned",
                "Last History ID": a.last_history_id or "N/A",
            })
        st.dataframe(pd.DataFrame(account_rows), use_container_width=True)

    st.divider()
    st.subheader("System Configuration")
    summary = settings.sanitized_summary()
    st.json(summary)


def main():
    db = get_db()
    current_view = render_sidebar()

    if current_view == "💳 Transactions":
        render_transactions_view(db)
    elif current_view == "📊 Spending Reports":
        render_spending_reports_view(db)
    elif current_view == "💼 Jobs & Interviews":
        render_jobs_view(db)
    elif current_view == "⚙️ Accounts & Status":
        render_accounts_view(db)


if __name__ == "__main__":
    main()
