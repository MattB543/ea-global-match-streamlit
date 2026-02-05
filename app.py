"""
File: app.py
Purpose: Streamlit web app for EA Global meeting matcher
Mobile-friendly UI for generating personalized meeting recommendations
"""

import os
import asyncio
import re
import streamlit as st
import pandas as pd

from utils import (
    load_csv_from_url,
    find_matches,
    format_row_as_pipe_delimited,
    format_profile_for_llm,
    format_profile_display,
    filter_profiles,
    run_dual_matching_pipeline,
    save_output,
)

# Page config - mobile-friendly
st.set_page_config(
    page_title="EA Global Meeting Matcher",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Constrain max width and fix line break rendering
st.markdown("""
<style>
    .block-container { max-width: 1100px; }
    .stMarkdown p { white-space: pre-wrap; }
</style>
""", unsafe_allow_html=True)

# Configuration
OUTPUT_DIR = "outputs/matches"
# Gemini 3 Pro Preview just launched - upgrading from gemini-2.5-pro
LLM_MODEL = "gemini-3-pro-preview"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_config():
    """Get configuration from secrets or environment."""
    try:
        csv_url = st.secrets.get("CSV_URL", "")
        app_password = st.secrets.get("APP_PASSWORD", "")
        gemini_api_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        csv_url = os.environ.get("CSV_URL", "")
        app_password = os.environ.get("APP_PASSWORD", "")
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")

    return csv_url, app_password, gemini_api_key

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'search_performed' not in st.session_state:
    st.session_state.search_performed = False
if 'matches' not in st.session_state:
    st.session_state.matches = []
if 'selected_match' not in st.session_state:
    st.session_state.selected_match = None
if 'df' not in st.session_state:
    st.session_state.df = None
if 'df_filtered' not in st.session_state:
    st.session_state.df_filtered = None
if 'recommendations_get' not in st.session_state:
    st.session_state.recommendations_get = None
if 'slack_recommendations_get' not in st.session_state:
    st.session_state.slack_recommendations_get = None
if 'recommendations_give' not in st.session_state:
    st.session_state.recommendations_give = None
if 'slack_recommendations_give' not in st.session_state:
    st.session_state.slack_recommendations_give = None
if 'scoring_status_get' not in st.session_state:
    st.session_state.scoring_status_get = None
if 'scoring_status_give' not in st.session_state:
    st.session_state.scoring_status_give = None


def check_password(csv_url, app_password, gemini_api_key):
    """Show password input and check if correct."""
    # Check if all required configs are set
    if not csv_url or not app_password or not gemini_api_key:
        st.error("⚠️ Missing configuration. Please set CSV_URL, APP_PASSWORD, and GEMINI_API_KEY in secrets.")
        st.stop()

    st.title("🔒 EA Global Meeting Matcher")
    st.markdown("This app is password protected. Please enter the password to continue.")

    password_input = st.text_input("Password:", type="password", key="password_input")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🔓 Unlock", use_container_width=True):
            if password_input == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password")

    st.stop()


def main():
    # Get configuration
    csv_url, app_password, api_key = get_config()

    # Check password first
    if not st.session_state.authenticated:
        check_password(csv_url, app_password, api_key)

    st.title("🤝 EA Global Meeting Matcher")
    st.markdown("Find the best people to meet at EA Global based on your profile")

    # Load CSV from URL (cached in session state)
    if st.session_state.df is None:
        with st.spinner("📥 Downloading latest attendee data from Google Sheets..."):
            try:
                st.session_state.df, load_msg = load_csv_from_url(csv_url)
                st.success(load_msg)
            except Exception as e:
                st.error(f"Failed to load CSV: {e}")
                st.stop()

    df = st.session_state.df

    # Filter profiles (cached in session state)
    if st.session_state.df_filtered is None:
        with st.spinner("🔄 Filtering profiles (>= 300 chars)..."):
            try:
                df_filtered, original_count, filtered_count = filter_profiles(df, min_chars=300)
                st.session_state.df_filtered = df_filtered
                st.success(f"Filtered profiles: {filtered_count} of {original_count} attendees")
            except Exception as e:
                st.error(f"Failed to filter profiles: {e}")
                st.stop()

    df_filtered = st.session_state.df_filtered

    # Step 1: Name search
    st.header("1️⃣ Find Your Profile")

    col1, col2 = st.columns([3, 1])
    with col1:
        name = st.text_input(
            "Enter your name:",
            placeholder="e.g., John Smith",
            help="We'll use fuzzy matching to find your profile"
        )
    with col2:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        search_button = st.button("🔍 Search", type="primary", use_container_width=True)

    if search_button and name:
        with st.spinner(f"Searching for '{name}'..."):
            matches = find_matches(df, name, limit=5)
            if matches:
                st.session_state.matches = matches
                st.session_state.search_performed = True
                st.session_state.selected_match = None
                st.success(f"Found {len(matches)} potential matches")
            else:
                st.warning("No matches found. Try a different name or spelling.")
                st.session_state.search_performed = False

    # Step 2: Select match
    if st.session_state.search_performed and st.session_state.matches:
        st.header("2️⃣ Select Your Profile")

        # Create options for selectbox
        match_options = [
            f"{match_name} (match: {score:.0f}%)"
            for match_name, score, idx in st.session_state.matches
        ]
        match_options.append("➕ Custom Profile (paste your own)")

        selected_option = st.selectbox(
            "Which profile is yours?",
            options=match_options,
            index=0
        )

        # Handle selection
        if selected_option == "➕ Custom Profile (paste your own)":
            st.subheader("Paste Your Custom Profile")
            custom_profile = st.text_area(
                "Enter your profile information:",
                height=200,
                placeholder="Paste your EA Global profile text here..."
            )
            if custom_profile.strip():
                st.session_state.selected_match = {
                    'type': 'custom',
                    'profile': custom_profile,
                    'name': '[Custom Profile]'
                }
        else:
            # Find the selected match
            selected_idx = match_options.index(selected_option)
            match_name, score, idx = st.session_state.matches[selected_idx]
            matched_row = df.iloc[idx]

            st.session_state.selected_match = {
                'type': 'csv',
                'row': matched_row,
                'name': match_name,
                'score': score,
                'idx': idx  # positional index in df
            }

    # Step 3: Display profile and get additional context
    if st.session_state.selected_match:
        st.header("3️⃣ Review Your Profile")

        match_data = st.session_state.selected_match

        if match_data['type'] == 'custom':
            st.info("**Using custom profile:**")
            st.text_area("Your profile:", value=match_data['profile'], height=200, disabled=True)
        else:
            matched_row = match_data['row']
            if match_data['score'] < 100:
                st.info(f"**Matched:** {match_data['name']} (confidence: {match_data['score']:.0f}%)")
            else:
                st.success(f"**Exact match:** {match_data['name']}")

            with st.expander("📋 View full profile", expanded=True):
                profile_display = format_profile_display(matched_row)
                st.markdown(profile_display)

        # Additional context
        st.subheader("Additional Context (Optional)")
        additional_context = st.text_area(
            "Add any extra info (e.g., from your Slack intro):",
            height=100,
            placeholder="Optional: Add any additional context about yourself or your goals...",
            help="This will be included in the analysis to improve match quality"
        )

        # Step 4: Generate recommendations
        st.header("4️⃣ Generate Recommendations")

        generate_button = st.button("🚀 Generate Meeting Recommendations", type="primary", use_container_width=True)

        if generate_button:
            # Prepare user profile
            if match_data['type'] == 'custom':
                user_profile = match_data['profile']
            else:
                user_profile = format_profile_for_llm(match_data['row'])

            st.info(f"📊 Running dual pipeline: scoring {len(df_filtered)} profiles for both GET and GIVE value, then selecting top 25 for each...")

            # Get user_idx for excluding from scoring
            user_idx = None
            if match_data['type'] == 'csv':
                user_idx = match_data['idx']

            # Run dual matching pipeline
            status_container = st.empty()
            with st.spinner("Running dual matching pipeline (this runs both directions in parallel)..."):
                try:
                    (get_result, give_result) = asyncio.run(
                        run_dual_matching_pipeline(
                            df_filtered,
                            match_data['name'],
                            user_profile,
                            api_key,
                            LLM_MODEL,
                            chunk_size=50,
                            min_score=8,
                            additional_context=additional_context.strip() if additional_context.strip() else None,
                            user_idx=user_idx
                        )
                    )

                    get_response, get_scores, get_status = get_result
                    give_response, give_scores, give_status = give_result

                    # Show scoring details as bar charts
                    def parse_score_distribution(status_msgs):
                        dist = {}
                        for msg in status_msgs:
                            m = re.match(r'\s*Score (\d+): (\d+) profiles', msg)
                            if m:
                                dist[int(m.group(1))] = int(m.group(2))
                        return dist

                    get_dist = parse_score_distribution(get_status)
                    give_dist = parse_score_distribution(give_status)

                    with status_container.expander("📊 Scoring details", expanded=True):
                        chart_col1, chart_col2 = st.columns(2)
                        with chart_col1:
                            st.caption("🎯 Get Value (for you)")
                            if get_dist:
                                chart_df = pd.DataFrame({
                                    "Score": range(1, 11),
                                    "Profiles": [get_dist.get(i, 0) for i in range(1, 11)]
                                }).set_index("Score")
                                st.bar_chart(chart_df)
                        with chart_col2:
                            st.caption("🎁 Give Value (for them)")
                            if give_dist:
                                chart_df = pd.DataFrame({
                                    "Score": range(1, 11),
                                    "Profiles": [give_dist.get(i, 0) for i in range(1, 11)]
                                }).set_index("Score")
                                st.bar_chart(chart_df)

                    # Save get_value results
                    md_path, txt_path = save_output(match_data['name'], get_response, OUTPUT_DIR, suffix="_get_value")
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        st.session_state.slack_recommendations_get = f.read()
                    st.session_state.recommendations_get = get_response
                    st.session_state.scoring_status_get = get_status

                    # Save give_value results
                    md_path, txt_path = save_output(match_data['name'], give_response, OUTPUT_DIR, suffix="_give_value")
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        st.session_state.slack_recommendations_give = f.read()
                    st.session_state.recommendations_give = give_response
                    st.session_state.scoring_status_give = give_status

                    st.success("✅ Recommendations generated successfully!")

                except Exception as e:
                    st.error(f"❌ Failed to generate recommendations: {e}")
                    st.stop()

    # Step 5: Display results
    if st.session_state.recommendations_get:
        st.header("5️⃣ Your Meeting Recommendations")

        main_tab1, main_tab2 = st.tabs(["🎯 Who to Meet FOR YOU", "🎁 Who to Meet TO HELP THEM"])

        with main_tab1:
            tab1, tab2 = st.tabs(["📝 Markdown", "📱 Slack Format"])
            with tab1:
                st.markdown(st.session_state.recommendations_get)
                st.download_button(
                    label="⬇️ Download Markdown Version",
                    data=st.session_state.recommendations_get,
                    file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_get_value.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="dl_get_md"
                )
            with tab2:
                st.text_area("Slack/Text Version:", value=st.session_state.slack_recommendations_get, height=400)
                st.download_button(
                    label="⬇️ Download Slack Version",
                    data=st.session_state.slack_recommendations_get,
                    file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_get_value.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="dl_get_slack"
                )

        with main_tab2:
            tab1, tab2 = st.tabs(["📝 Markdown", "📱 Slack Format"])
            with tab1:
                st.markdown(st.session_state.recommendations_give)
                st.download_button(
                    label="⬇️ Download Markdown Version",
                    data=st.session_state.recommendations_give,
                    file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_give_value.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="dl_give_md"
                )
            with tab2:
                st.text_area("Slack/Text Version:", value=st.session_state.slack_recommendations_give, height=400)
                st.download_button(
                    label="⬇️ Download Slack Version",
                    data=st.session_state.slack_recommendations_give,
                    file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_give_value.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="dl_give_slack"
                )

        # Reset button
        st.divider()
        if st.button("🔄 Start New Search", use_container_width=True):
            st.session_state.search_performed = False
            st.session_state.matches = []
            st.session_state.selected_match = None
            st.session_state.recommendations_get = None
            st.session_state.slack_recommendations_get = None
            st.session_state.recommendations_give = None
            st.session_state.slack_recommendations_give = None
            st.session_state.scoring_status_get = None
            st.session_state.scoring_status_give = None
            st.rerun()

    # Footer
    st.divider()
    st.caption("Powered by Gemini 3 Pro Preview | EA Global Meeting Matcher")


if __name__ == "__main__":
    main()
