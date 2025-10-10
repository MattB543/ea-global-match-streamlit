"""
File: app.py
Purpose: Streamlit web app for EA Global meeting matcher
Mobile-friendly UI for generating personalized meeting recommendations
"""

import os
import sys
import asyncio
import streamlit as st
import pandas as pd

# Add parent directory to path to import utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    load_csv_from_url,
    find_matches,
    format_row_as_pipe_delimited,
    format_profile_display,
    create_prompt,
    send_to_gemini_parallel,
    save_output,
    generate_output_md_content
)

# Page config - mobile-friendly
st.set_page_config(
    page_title="EA Global Meeting Matcher",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Configuration
OUTPUT_DIR = "outputs/matches"
LLM_MODEL = "gemini-2.5-pro"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_config():
    """Get configuration from secrets or environment."""
    try:
        csv_url = st.secrets.get("CSV_URL", "")
        app_password = st.secrets.get("APP_PASSWORD", "")
        gemini_api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
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
if 'output_md_content' not in st.session_state:
    st.session_state.output_md_content = None
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'slack_recommendations' not in st.session_state:
    st.session_state.slack_recommendations = None


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

    # Generate output.md content (cached in session state)
    if st.session_state.output_md_content is None:
        with st.spinner("🔄 Generating filtered profiles (>= 300 chars)..."):
            try:
                content, original_count, filtered_count = generate_output_md_content(csv_url, min_chars=300)
                st.session_state.output_md_content = content
                st.success(f"Filtered profiles: {filtered_count} of {original_count} attendees")
            except Exception as e:
                st.error(f"Failed to generate profiles: {e}")
                st.stop()

    output_md_content = st.session_state.output_md_content

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
                'score': score
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
            # Use cached output.md content
            full_output = output_md_content
            st.info(f"📊 Using {len(full_output):,} characters of profile data")

            # Prepare user profile
            if match_data['type'] == 'custom':
                user_profile = match_data['profile']
            else:
                user_profile = format_row_as_pipe_delimited(match_data['row'])

            # Create prompt
            with st.spinner("Creating prompt..."):
                prompt = create_prompt(
                    match_data['name'],
                    user_profile,
                    full_output,
                    additional_context if additional_context.strip() else None
                )
                st.success(f"Prompt created ({len(prompt):,} characters)")

            # Call Gemini API
            status_container = st.empty()
            with st.spinner("Generating recommendations (this takes ~30-60 seconds)..."):
                try:
                    # Run async function
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    response, status_messages = loop.run_until_complete(
                        send_to_gemini_parallel(prompt, api_key, LLM_MODEL)
                    )
                    loop.close()

                    # Show status messages
                    with status_container.expander("📊 Generation details", expanded=False):
                        for msg in status_messages:
                            st.text(msg)

                    st.session_state.recommendations = response

                    # Save to files
                    with st.spinner("Saving results..."):
                        md_path, txt_path = save_output(
                            match_data['name'],
                            response,
                            OUTPUT_DIR
                        )

                    # Load slack version for display
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        st.session_state.slack_recommendations = f.read()

                    st.success("✅ Recommendations generated successfully!")

                except Exception as e:
                    st.error(f"❌ Failed to generate recommendations: {e}")
                    st.stop()

    # Step 5: Display results
    if st.session_state.recommendations:
        st.header("5️⃣ Your Meeting Recommendations")

        tab1, tab2 = st.tabs(["📱 Slack Format (Mobile-Friendly)", "📝 Markdown Format"])

        with tab1:
            st.text_area(
                "Slack/Text Version (ready to copy):",
                value=st.session_state.slack_recommendations,
                height=400
            )
            st.download_button(
                label="⬇️ Download Slack Version",
                data=st.session_state.slack_recommendations,
                file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_recommendations.txt",
                mime="text/plain",
                use_container_width=True
            )

        with tab2:
            st.markdown(st.session_state.recommendations)
            st.download_button(
                label="⬇️ Download Markdown Version",
                data=st.session_state.recommendations,
                file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_recommendations.md",
                mime="text/markdown",
                use_container_width=True
            )

        # Reset button
        st.divider()
        if st.button("🔄 Start New Search", use_container_width=True):
            st.session_state.search_performed = False
            st.session_state.matches = []
            st.session_state.selected_match = None
            st.session_state.recommendations = None
            st.session_state.slack_recommendations = None
            st.rerun()

    # Footer
    st.divider()
    st.caption("Powered by Gemini 2.5 Pro | EA Global Meeting Matcher")


if __name__ == "__main__":
    main()
