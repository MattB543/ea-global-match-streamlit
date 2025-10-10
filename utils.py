"""
File: utils.py
Purpose: Reusable functions for EA Global meeting matcher (Streamlit version)
Extracted from match_person.py
"""

import os
import asyncio
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from rapidfuzz import fuzz, process
from markdown_to_mrkdwn import SlackMarkdownConverter


def get_export_url(sheet_url):
    """Convert Google Sheets URL to CSV export URL."""
    sheet_id = sheet_url.split('/d/')[1].split('/')[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def calculate_row_length(row):
    """Calculate total character length of all values in a row."""
    return sum(len(str(val)) for val in row if pd.notna(val))


def load_csv_from_url(csv_url):
    """
    Load CSV directly from Google Sheets URL (no local caching).

    Args:
        csv_url: Google Sheets URL or export URL

    Returns:
        Tuple of (DataFrame, status_message)
    """
    export_url = get_export_url(csv_url) if '/d/' in csv_url else csv_url
    df = pd.read_csv(export_url, skiprows=4)
    return df, f"Downloaded {len(df)} attendees from Google Sheets"


def load_csv(csv_path, csv_url):
    """
    Load the CSV with proper skiprows.

    Args:
        csv_path: Local CSV file path
        csv_url: Google Sheets export URL

    Returns:
        DataFrame with attendees
    """
    # Check if local CSV exists
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, skiprows=4)
        return df, f"Loaded {len(df)} attendees from local file"

    # Download if not found locally
    export_url = get_export_url(csv_url)
    df = pd.read_csv(export_url, skiprows=4)

    # Save for next time
    df_with_header = pd.read_csv(export_url)
    df_with_header.to_csv(csv_path, index=False)

    return df, f"Downloaded and saved {len(df)} attendees from Google Sheets"


def generate_output_md_content(csv_url, min_chars=300):
    """
    Generate output.md content dynamically from CSV URL.
    Filters rows to keep only those with >= min_chars total characters.

    Args:
        csv_url: Google Sheets URL
        min_chars: Minimum character count to include row (default 300)

    Returns:
        Tuple of (markdown_content, original_count, filtered_count)
    """
    # Download CSV
    export_url = get_export_url(csv_url) if '/d/' in csv_url else csv_url
    df = pd.read_csv(export_url, skiprows=4)
    original_count = len(df)

    # Filter rows by character length
    df['_row_length'] = df.apply(calculate_row_length, axis=1)
    df_filtered = df[df['_row_length'] >= min_chars].drop('_row_length', axis=1)
    filtered_count = len(df_filtered)

    # Convert to pipe-delimited markdown
    import io
    output = io.StringIO()
    df_filtered.to_csv(output, sep='|', index=False)
    content = output.getvalue()

    return content, original_count, filtered_count


def find_matches(df, name, limit=5):
    """
    Find person by name using fuzzy matching.

    Args:
        df: DataFrame with attendee data
        name: Name to search for
        limit: Number of matches to return

    Returns:
        List of tuples: [(matched_name, score, idx), ...]
    """
    # Create full names for matching
    df['full_name'] = df['First Name'].fillna('') + ' ' + df['Last Name'].fillna('')
    full_names = df['full_name'].tolist()

    # Fuzzy match
    matches = process.extract(name, full_names, scorer=fuzz.ratio, limit=limit)

    return matches if matches else []


def format_row_as_pipe_delimited(row):
    """Format a DataFrame row as pipe-delimited string."""
    return '|'.join(str(val) if pd.notna(val) else '' for val in row.values)


def format_profile_display(row):
    """Format a DataFrame row for nice display."""
    fields = []
    for col, val in row.items():
        if pd.notna(val) and str(val).strip():
            fields.append(f"**{col}:**\n{val}")
    return "\n\n".join(fields)


def load_output_md(output_md_path):
    """Load the full output.md file."""
    if not os.path.exists(output_md_path):
        raise FileNotFoundError(f"{output_md_path} not found. Please upload or ensure it exists.")

    with open(output_md_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def create_prompt(full_name, user_row, full_output, additional_context=None):
    """Create the prompt following claude/format.md structure."""
    profile_section = user_row
    if additional_context:
        profile_section = f"{user_row}\n\nAdditional context:\n{additional_context}"

    return f"""My name is {full_name}, I'll share my EA Global profile below. Please carefully read all of the other EA Global profiles below and tell me which 10 people I should book a meeting with given my details and my requests and everyone elses details and offers.

{profile_section}

---

{full_output}

---

Remember, this is me:

{profile_section}
"""


async def send_to_gemini_parallel(prompt, api_key, model="gemini-2.5-pro"):
    """
    Send prompt to Gemini with 3 different temperatures in parallel,
    then consolidate into one final response.

    Temperatures used: 0 (deterministic), 0.75 (balanced), 1.5 (creative)

    Returns:
        Tuple of (final_response, status_messages)
    """
    client = genai.Client(api_key=api_key)
    temps = [0, 0.75, 1.5]
    status_messages = []

    async def call_with_temp(temp):
        """Make a single API call with specified temperature."""
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temp)
        )
        return response.text

    # Make 3 parallel calls
    status_messages.append(f"Making 3 parallel calls (temps: {temps})...")
    try:
        results = await asyncio.gather(*[call_with_temp(t) for t in temps])
        status_messages.append("✓ Received all 3 responses")
    except Exception as e:
        status_messages.append(f"✗ Failed during parallel calls: {e}")
        raise

    # Create consolidation prompt
    consolidation_prompt = f"""Below are three lists of recommended EA Global meeting matches. Merge them into a single list by:
1. Removing duplicate names (same person should appear only once)
2. Selecting the best 10 unique people
3. Using the EXACT same format and structure as the lists below
(for each match, include their title and org if available, and include why the match is a good fit for the user)
4. No preamble or introduction - start directly with the recommendations

List 1:
{results[0]}

---

List 2:
{results[1]}

---

List 3:
{results[2]}

---

Output the consolidated top 10 unique recommendations now, using the exact format above:"""

    # Make final consolidation call (use temp=0 for consistency)
    status_messages.append("Consolidating 3 responses into final output...")
    try:
        final_response = await client.aio.models.generate_content(
            model=model,
            contents=consolidation_prompt,
            config=types.GenerateContentConfig(temperature=0)
        )
        status_messages.append("✓ Consolidation complete")
        return final_response.text, status_messages
    except Exception as e:
        status_messages.append(f"✗ Failed during consolidation: {e}")
        raise


def save_output(full_name, content, output_dir):
    """
    Save the output to timestamped .md and .txt (Slack format) files.

    Returns:
        Tuple of (md_filepath, txt_filepath)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Clean name for filename
    clean_name = full_name.lower().replace(' ', '_')
    base_filename = f"{timestamp}_{clean_name}_recommendations"

    # Save markdown version
    md_filepath = os.path.join(output_dir, f"{base_filename}.md")
    with open(md_filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    # Convert to Slack format and save .txt
    converter = SlackMarkdownConverter()
    slack_content = converter.convert(content)

    txt_filepath = os.path.join(output_dir, f"{base_filename}.txt")
    with open(txt_filepath, 'w', encoding='utf-8') as f:
        f.write(slack_content)

    return md_filepath, txt_filepath
