"""
File: app.py
Purpose: Streamlit web app for EA Global meeting matcher
Mobile-friendly UI for generating personalized meeting recommendations
"""

import hmac
import os
import asyncio
import re
import time
import streamlit as st
import pandas as pd

from rapidfuzz import fuzz

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


def build_swapcard_lookup(df):
    """Build a name -> Swapcard URL lookup from the DataFrame."""
    lookup = {}
    for _, row in df.iterrows():
        first = str(row.get('First Name', '')).strip()
        last = str(row.get('Last Name', '')).strip()
        url = str(row.get('Swapcard', '')).strip()
        if first and last and url and url.startswith('http'):
            full_name = f"{first} {last}"
            lookup[full_name.lower()] = url
    return lookup


def inject_swapcard_links(markdown_text, swapcard_lookup):
    """Replace names in ### headings with clickable Swapcard links."""
    def replace_heading(match):
        full_line = match.group(0)
        prefix = match.group(1)  # "### #1. "
        name = match.group(2)    # "First Last"
        rest = match.group(3)    # " — Role, Org"

        # Fuzzy match the name against the lookup
        name_lower = name.strip().lower()
        if name_lower in swapcard_lookup:
            url = swapcard_lookup[name_lower]
            return f"{prefix}[{name}]({url}){rest}"

        # Try fuzzy matching for slight name variations
        best_match = None
        best_score = 0
        for lookup_name, url in swapcard_lookup.items():
            score = fuzz.ratio(name_lower, lookup_name)
            if score > best_score:
                best_score = score
                best_match = (lookup_name, url)
        if best_match and best_score >= 80:
            url = best_match[1]
            return f"{prefix}[{name}]({url}){rest}"

        return full_line

    # Match "### #1. Name — Rest" or "### #1. Name - Rest"
    return re.sub(
        r'(###\s*#?\d+\.?\s*)([^—–\-\n]+)([\s]*[—–-].+)',
        replace_heading,
        markdown_text
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
    .stMarkdown h3 { font-size: 1.3rem; margin-top: 2.2rem; margin-bottom: 0.3rem; }
    .stMarkdown h4 { font-size: 1.15rem; margin-top: 1.8rem; margin-bottom: 0.3rem; }
    .stMarkdown hr { border: none; border-top: 1px solid rgba(128, 128, 128, 0.2); margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

# Configuration
OUTPUT_DIR = "outputs/matches"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_config():
    """Get configuration from secrets or environment."""
    def _get(key, default=""):
        try:
            return st.secrets.get(key, default)
        except Exception:
            return os.environ.get(key, default)

    return {
        "csv_url": _get("CSV_URL"),
        "app_password": _get("APP_PASSWORD"),
        "azure_api_key": _get("AZURE_API_KEY"),
        "azure_endpoint": _get("AZURE_OPENAI_ENDPOINT"),
        "azure_deployment": _get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2"),
        "azure_api_version": _get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    }

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
if 'recommendations_give' not in st.session_state:
    st.session_state.recommendations_give = None
if 'scoring_status_get' not in st.session_state:
    st.session_state.scoring_status_get = None
if 'scoring_status_give' not in st.session_state:
    st.session_state.scoring_status_give = None


def check_password(config):
    """Show password input and check if correct."""
    # Check if all required configs are set
    if not config["csv_url"] or not config["app_password"] or not config["azure_api_key"] or not config["azure_endpoint"]:
        st.error("⚠️ Missing configuration. Please set CSV_URL, APP_PASSWORD, AZURE_API_KEY, and AZURE_OPENAI_ENDPOINT in secrets.")
        st.stop()

    # Initialize failed attempts tracking
    if 'failed_attempts' not in st.session_state:
        st.session_state.failed_attempts = 0

    st.title("🔒 EA Global Meeting Matcher")
    st.markdown("This app is password protected. Please enter the password to continue.")

    # Show lockout message if too many failed attempts
    if st.session_state.failed_attempts >= 5:
        lockout_seconds = 2 ** st.session_state.failed_attempts
        st.error(f"⚠️ Too many failed attempts. Please wait ~{lockout_seconds}s before trying again.")

    password_input = st.text_input("Password:", type="password", key="password_input")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        unlock_button = st.button("🔓 Unlock", use_container_width=True)

    # Trigger on button click or Enter key (password value changed)
    password_submitted = password_input and password_input != st.session_state.get('last_password_attempt', '')
    if (unlock_button or password_submitted) and password_input:
        st.session_state.last_password_attempt = password_input
        if hmac.compare_digest(password_input, config["app_password"]):
            st.session_state.authenticated = True
            st.session_state.failed_attempts = 0
            st.rerun()
        else:
            st.session_state.failed_attempts += 1
            if st.session_state.failed_attempts >= 5:
                st.error(f"❌ Incorrect password. Too many attempts — please wait before retrying.")
            else:
                st.error(f"❌ Incorrect password ({5 - st.session_state.failed_attempts} attempts remaining)")

    st.stop()


def main():
    # Get configuration
    config = get_config()

    # Check password first
    if not st.session_state.authenticated:
        check_password(config)

    st.title("🤝 EA Global Meeting Matcher")
    st.markdown("Find the best people to meet at EA Global based on your profile")

    # Load CSV from URL (cached in session state)
    if st.session_state.df is None:
        with st.spinner("📥 Downloading latest attendee data from Google Sheets..."):
            try:
                st.session_state.df, load_msg = load_csv_from_url(config["csv_url"])
                st.success(load_msg)
            except Exception as e:
                st.error(f"Failed to load CSV: {e}")
                st.stop()

    df = st.session_state.df

    # Filter profiles (cached in session state)
    if st.session_state.df_filtered is None:
        with st.spinner("🔄 Filtering incomplete profiles..."):
            try:
                df_filtered, original_count, filtered_count = filter_profiles(df, min_chars=200)
                st.session_state.df_filtered = df_filtered
                excluded = original_count - filtered_count
                st.success(f"Scoring {filtered_count} of {original_count} attendees ({excluded} excluded for having fewer than 200 characters of profile info)")
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

    # Trigger search on button click OR when name changes (Enter key submits the text_input)
    name_changed = name and name != st.session_state.get('last_searched_name', '')
    if (search_button or name_changed) and name:
        st.session_state.last_searched_name = name
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

            # Run dual matching pipeline with progress tracking
            status_container = st.empty()
            progress_bar = st.progress(0)
            progress_text = st.empty()

            # Calculate total batches for progress tracking
            import math
            num_profiles = len(df_filtered) - (1 if user_idx is not None else 0)
            batches_per_direction = math.ceil(num_profiles / 60)
            total_batches = batches_per_direction * 2  # both directions

            progress_state = {"completed": 0, "start_time": time.time(), "generating_finals": False}
            FINAL_REPORT_SECONDS = 120  # estimated time for final report generation

            # Show initial state immediately
            progress_text.caption(f"Scored 0/{total_batches} batches across both pipelines — ~1m 30s remaining")

            def on_batch_complete(completed_in_direction, total_in_direction, direction):
                # Don't overwrite the "generating final reports" message
                if progress_state["generating_finals"]:
                    return
                progress_state["completed"] += 1
                done = progress_state["completed"]
                elapsed = time.time() - progress_state["start_time"]
                # Reserve last 10% of bar for final report generation
                pct = min(done / total_batches * 0.9, 0.9)
                progress_bar.progress(pct)

                if done >= 3:
                    avg_per_batch = elapsed / done
                    remaining = (total_batches - done) * avg_per_batch + FINAL_REPORT_SECONDS
                    mins, secs = divmod(int(remaining), 60)
                    eta = f"{mins}m {secs}s" if mins else f"{secs}s"
                else:
                    # Use 1m30s estimate until we have enough data
                    remaining = max(0, 90 - elapsed)
                    mins, secs = divmod(int(remaining), 60)
                    eta = f"{mins}m {secs}s" if mins else f"{secs}s"
                progress_text.caption(f"Scored {done}/{total_batches} batches across both pipelines — ~{eta} remaining")

            def on_final_start(direction):
                progress_state["generating_finals"] = True
                progress_bar.progress(0.92)
                progress_text.caption("Scoring complete! Generating final reports — ~2m remaining")

            try:
                (get_result, give_result) = asyncio.run(
                    run_dual_matching_pipeline(
                        df_filtered,
                        match_data['name'],
                        user_profile,
                        azure_api_key=config["azure_api_key"],
                        azure_endpoint=config["azure_endpoint"],
                        azure_deployment=config["azure_deployment"],
                        azure_api_version=config["azure_api_version"],
                        chunk_size=60,
                        min_score=8,
                        additional_context=additional_context.strip() if additional_context.strip() else None,
                        user_idx=user_idx,
                        progress_callback=on_batch_complete,
                        final_callback=on_final_start
                    )
                )

                progress_bar.progress(1.0)
                progress_text.caption("Done!")

                get_response, get_scores, get_status = get_result
                give_response, give_scores, give_status = give_result

                # Inject Swapcard links into names
                swapcard_lookup = build_swapcard_lookup(df)
                get_response = inject_swapcard_links(get_response, swapcard_lookup)
                give_response = inject_swapcard_links(give_response, swapcard_lookup)

                # Clear progress indicators
                progress_bar.empty()
                progress_text.empty()

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

                # Save results
                save_output(match_data['name'], get_response, OUTPUT_DIR, suffix="_get_value")
                save_output(match_data['name'], give_response, OUTPUT_DIR, suffix="_give_value")
                st.session_state.recommendations_get = get_response
                st.session_state.recommendations_give = give_response
                st.session_state.scoring_status_get = get_status
                st.session_state.scoring_status_give = give_status

                st.success("✅ Recommendations generated successfully!")

            except Exception as e:
                st.error(f"❌ Failed to generate recommendations: {e}")
                st.stop()

    # Step 5: Display results
    if st.session_state.recommendations_get:
        st.header("5️⃣ Your Meeting Recommendations")

        main_tab1, main_tab2, main_tab3 = st.tabs(["🎯 Who to Meet FOR YOU", "🎁 Who to Meet TO HELP THEM", "⭐ On Both Lists"])

        with main_tab1:
            st.markdown(st.session_state.recommendations_get)
            st.download_button(
                label="⬇️ Download",
                data=st.session_state.recommendations_get,
                file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_get_value.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_get_md"
            )

        with main_tab2:
            st.markdown(st.session_state.recommendations_give)
            st.download_button(
                label="⬇️ Download",
                data=st.session_state.recommendations_give,
                file_name=f"{st.session_state.selected_match['name'].replace(' ', '_')}_give_value.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_give_md"
            )

        with main_tab3:
            # Parse names and their sections from both reports
            def extract_entries(markdown_text):
                """Extract name -> full entry section from structured report."""
                entries = {}
                if not markdown_text:
                    return entries
                # Split on ### headings
                parts = re.split(r'(?=^### )', markdown_text, flags=re.MULTILINE)
                for part in parts:
                    part = part.strip()
                    if not part.startswith('###'):
                        continue
                    heading_line = part.split('\n')[0]
                    # Extract full heading after "### #1. "
                    heading_match = re.match(r'###\s*#?\d+\.?\s*(.+)', heading_line)
                    if heading_match:
                        full_heading = heading_match.group(1).strip()
                        # Get name: strip markdown link syntax [Name](url) if present
                        name_part = re.split(r'\s*[—–]\s*', full_heading)[0].strip()
                        link_match = re.match(r'\[([^\]]+)\]', name_part)
                        name = link_match.group(1) if link_match else name_part
                        # Get everything after the heading line
                        body_lines = part.split('\n')[1:]
                        body = '\n'.join(l for l in body_lines if l.strip() and l.strip() != '---')
                        entries[name.lower()] = {
                            'name': name,
                            'heading': full_heading,
                            'body': body.strip()
                        }
                return entries

            get_entries = extract_entries(st.session_state.recommendations_get)
            give_entries = extract_entries(st.session_state.recommendations_give)

            # Find overlapping names (exact match on lowercase)
            overlap_names = set(get_entries.keys()) & set(give_entries.keys())

            # Also try fuzzy matching for near-matches
            if len(overlap_names) < len(get_entries):
                for get_key in get_entries:
                    if get_key in overlap_names:
                        continue
                    for give_key in give_entries:
                        if give_key in overlap_names:
                            continue
                        if fuzz.ratio(get_key, give_key) >= 85:
                            overlap_names.add(get_key)
                            # Store the give_key mapping
                            get_entries[get_key]['_give_key'] = give_key
                            break

            if overlap_names:
                st.success(f"**{len(overlap_names)} people appear on both lists** — these are your highest-priority meetings!")
                st.markdown("")
                for name_key in overlap_names:
                    get_entry = get_entries[name_key]
                    give_key = get_entry.get('_give_key', name_key)
                    give_entry = give_entries.get(give_key, give_entries.get(name_key))
                    if not give_entry:
                        continue
                    st.markdown(f"### {get_entry['heading']}")
                    st.markdown(f"**🎯 Why meet them (for you):**")
                    st.markdown(get_entry['body'])
                    st.markdown(f"**🎁 Why meet them (for them):**")
                    st.markdown(give_entry['body'])
                    st.markdown("---")
            else:
                st.info("No overlapping names between the two lists. Each list recommends unique people.")

        # Reset button
        st.divider()
        if st.button("🔄 Start New Search", use_container_width=True):
            st.session_state.search_performed = False
            st.session_state.matches = []
            st.session_state.selected_match = None
            st.session_state.recommendations_get = None
            st.session_state.recommendations_give = None
            st.session_state.scoring_status_get = None
            st.session_state.scoring_status_give = None
            st.session_state.last_searched_name = ''
            st.rerun()

    # Footer
    st.divider()
    st.caption("Powered by Azure OpenAI | EA Global Meeting Matcher")


if __name__ == "__main__":
    main()
