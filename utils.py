"""
File: utils.py
Purpose: Reusable functions for EA Global meeting matcher (Streamlit version)
"""

import json
import os
import re
import asyncio
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from rapidfuzz import fuzz, process
from markdown_to_mrkdwn import SlackMarkdownConverter


class RateLimiter:
    """Token-bucket rate limiter for API calls."""

    def __init__(self, max_per_minute=25):
        self.max_per_minute = max_per_minute
        self.interval = 60.0 / max_per_minute  # seconds between requests
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def acquire(self):
        """Wait until we can make the next request."""
        async with self._lock:
            import time
            now = time.monotonic()
            wait_time = self._last_request_time + self.interval - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()


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


def filter_profiles(df, min_chars=300):
    """
    Filter profiles to keep only those with >= min_chars total characters.

    Args:
        df: DataFrame with attendee data
        min_chars: Minimum character count to include row (default 300)

    Returns:
        Tuple of (filtered_df, original_count, filtered_count)
    """
    original_count = len(df)
    row_lengths = df.apply(calculate_row_length, axis=1)
    df_filtered = df[row_lengths >= min_chars]
    return df_filtered, original_count, len(df_filtered)


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
    full_names = (df['First Name'].fillna('') + ' ' + df['Last Name'].fillna('')).tolist()
    matches = process.extract(name, full_names, scorer=fuzz.ratio, limit=limit)
    return matches if matches else []


def format_row_as_pipe_delimited(row):
    """Format a DataFrame row as pipe-delimited string."""
    return '|'.join(str(val) if pd.notna(val) else '' for val in row.values)


def format_profile_for_llm(row):
    """Format a DataFrame row as a labeled JSON object for LLM consumption."""
    profile = {}
    for col, val in row.items():
        if pd.notna(val) and str(val).strip():
            profile[col] = str(val).strip()
    return json.dumps(profile, ensure_ascii=False)


def format_profile_display(row):
    """Format a DataFrame row for nice display in Streamlit."""
    fields = []
    for col, val in row.items():
        if pd.notna(val) and str(val).strip():
            fields.append(f"**{col}:**\n{val}")
    return "\n\n".join(fields)


DIRECTION_SCORING = {
    "get_value": {
        "heading": "Score each person on how valuable a 1-on-1 meeting with them would be FOR ME.",
        "criteria": """Consider:
- How much I could learn from their expertise and experience
- Potential for collaboration on projects aligned with MY goals
- Access to their network, resources, or opportunities relevant to me
- Alignment between their work/interests and what I'm trying to achieve""",
    },
    "give_value": {
        "heading": "Score each person on how much VALUE I COULD PROVIDE TO THEM in a 1-on-1 meeting.",
        "criteria": """Consider:
- Their stated needs (especially "How Others Can Help Me") and whether my skills address them
- Whether my expertise, experience, or network could advance THEIR goals
- How my background uniquely positions me to help them specifically
- Alignment between what I offer and what they're seeking""",
    },
}

DIRECTION_FINAL = {
    "get_value": {
        "goal": "recommend the TOP 25 people I should prioritize meeting FOR MY OWN BENEFIT",
        "per_person": """1. Their name, title, and organization
2. What I stand to gain from this meeting (specific knowledge, collaboration, opportunities)
3. Concrete topics to discuss that would be most valuable FOR ME""",
    },
    "give_value": {
        "goal": "recommend the TOP 25 people I should prioritize meeting TO PROVIDE THEM THE MOST VALUE",
        "per_person": """1. Their name, title, and organization
2. What specific value I can provide to them based on their needs and my capabilities
3. Concrete ways I could help them or topics where my expertise would benefit them""",
    },
}


def create_scoring_prompt(user_profile, numbered_profiles, batch_size, total_count, direction="get_value"):
    """Create the scoring prompt for a batch of profiles."""
    d = DIRECTION_SCORING[direction]

    return f"""You are helping match attendees at EA Global, a conference for people in the Effective Altruism community.

Below is MY profile, followed by a batch of {batch_size} attendee profiles (out of ~{total_count} total attendees at the conference).

{d["heading"]}

{d["criteria"]}

IMPORTANT SCORING CONTEXT:
- You are seeing {batch_size} of ~{total_count} total attendees. Do NOT force a bell curve or distribution within this batch.
- Score each person INDEPENDENTLY based on match quality.
- It is completely valid for many or all people in a batch to score high (or low).
- A score of 10 does not mean "best in this batch" — it means "exceptional match regardless of who else exists."

SCORING SCALE:
- 9-10: Exceptional match for the criteria above
- 7-8: Strong match
- 5-6: Moderate match
- 3-4: Mild match
- 1-2: Weak match

MY PROFILE:
{user_profile}

---

ATTENDEE PROFILES TO SCORE:

{numbered_profiles}

---

Return a JSON object mapping each profile number to its integer score.
Example: {{"1": 7, "2": 9, "3": 4}}
Score all {batch_size} profiles. Return ONLY valid JSON, nothing else."""


def create_final_prompt(user_name, user_profile, scored_profiles_text, top_count, total_count,
                        direction="get_value", additional_context=None):
    """Create the final recommendation prompt for top-scored profiles."""
    d = DIRECTION_FINAL[direction]
    context_section = ""
    if additional_context:
        context_section = f"\nAdditional context about me:\n{additional_context}\n"

    return f"""You are helping me ({user_name}) decide who to meet at EA Global. I pre-screened ~{total_count} attendees using AI-assisted scoring and narrowed it down to the {top_count} strongest matches below (all scored 8+ out of 10).

Your job: {d["goal"]}, with compelling explanations for each.

MY PROFILE:
{user_profile}
{context_section}
---

TOP MATCHED PROFILES (with their pre-screening scores):
{scored_profiles_text}

---

For each of your top 25 recommendations, include:
{d["per_person"]}

Rank from #1 (strongest) to #25. Start directly with the recommendations, no preamble or introduction."""


async def run_matching_pipeline(df_filtered, user_name, user_profile, api_key, model,
                                chunk_size=50, min_score=8, additional_context=None,
                                direction="get_value", user_idx=None, rate_limiter=None):
    """
    Run the matching pipeline for a single direction:
    1. Score all profiles in batches (in parallel, rate-limited)
    2. Filter to profiles scoring >= min_score
    3. Generate final top-25 recommendations

    Args:
        direction: "get_value" (who benefits me) or "give_value" (who I can help)
        user_idx: DataFrame index of the user's own profile to exclude from scoring
        rate_limiter: RateLimiter instance for rate limiting API calls (shared across pipelines)

    Returns:
        Tuple of (recommendations_text, all_scores_dict, status_messages)
    """
    client = genai.Client(api_key=api_key)
    if rate_limiter is None:
        rate_limiter = RateLimiter(max_per_minute=25)
    status_messages = []
    direction_label = "GET value" if direction == "get_value" else "GIVE value"
    status_messages.append(f"=== {direction_label} ===")

    # Filter out the user's own profile
    indices = df_filtered.index.tolist()
    if user_idx is not None and user_idx in indices:
        indices = [i for i in indices if i != user_idx]
        status_messages.append(f"Excluded own profile (index {user_idx})")

    total_count = len(indices)

    # Create batches
    batches = []
    for i in range(0, len(indices), chunk_size):
        batches.append(indices[i:i + chunk_size])

    num_batches = len(batches)
    status_messages.append(f"Scoring {total_count} profiles in {num_batches} batches of ~{chunk_size}...")

    async def score_one_batch(batch_indices, batch_num):
        """Score a single batch of profiles with retries on failure."""
        numbered_lines = []
        for j, idx in enumerate(batch_indices, 1):
            row = df_filtered.loc[idx]
            profile_json = format_profile_for_llm(row)
            numbered_lines.append(f"Profile {j}: {profile_json}")

        numbered_text = "\n".join(numbered_lines)
        prompt = create_scoring_prompt(
            user_profile, numbered_text, len(batch_indices), total_count, direction
        )

        backoff_delays = [5, 10, 20]
        for attempt in range(3):
            await rate_limiter.acquire()
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=1,
                        response_mime_type="application/json"
                    )
                )

                if not response.text:
                    raise ValueError(f"Empty response for batch {batch_num}")

                scores = json.loads(response.text)

                # Map profile numbers back to df indices
                result = {}
                for j, idx in enumerate(batch_indices, 1):
                    score = scores.get(str(j), scores.get(j, 0))
                    result[idx] = score

                return result, batch_num

            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(backoff_delays[attempt])
                else:
                    raise ValueError(f"Batch {batch_num} failed after {attempt + 1} attempts: {e}")

    # Run all batches in parallel
    try:
        results = await asyncio.gather(*[score_one_batch(b, i + 1) for i, b in enumerate(batches)])
        status_messages.append(f"All {num_batches} batches scored")
    except Exception as e:
        status_messages.append(f"Scoring failed: {e}")
        raise

    # Collect all scores
    all_scores = {}
    for batch_scores, _ in results:
        all_scores.update(batch_scores)

    # Score distribution stats
    for score_val in range(10, 0, -1):
        count = sum(1 for s in all_scores.values() if s == score_val)
        if count > 0:
            status_messages.append(f"  Score {score_val}: {count} profiles")

    # Filter to min_score+
    top_items = [
        (idx, score) for idx, score
        in sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        if score >= min_score
    ]
    status_messages.append(f"{len(top_items)} profiles scored {min_score}+ (sending to final round)")

    if not top_items:
        raise ValueError(f"No profiles scored {min_score}+. Try lowering the threshold.")

    # Format top profiles with their scores for the final prompt
    scored_lines = []
    for idx, score in top_items:
        row = df_filtered.loc[idx]
        profile_json = format_profile_for_llm(row)
        scored_lines.append(f"[Score: {score}] {profile_json}")
    scored_text = "\n".join(scored_lines)

    # Final recommendation call
    status_messages.append(f"Generating final top 25 from {len(top_items)} candidates...")
    final_prompt = create_final_prompt(
        user_name, user_profile, scored_text, len(top_items),
        total_count, direction, additional_context
    )

    backoff_delays = [5, 10, 20]
    for attempt in range(3):
        await rate_limiter.acquire()
        try:
            final_response = await client.aio.models.generate_content(
                model=model,
                contents=final_prompt,
                config=types.GenerateContentConfig(temperature=1)
            )
            if not final_response.text:
                raise ValueError("Empty response from final recommendation call")
            status_messages.append("Final recommendations generated")
            return final_response.text, all_scores, status_messages
        except Exception as e:
            if attempt < 2:
                status_messages.append(f"Final call failed, retrying in {backoff_delays[attempt]}s...")
                await asyncio.sleep(backoff_delays[attempt])
            else:
                status_messages.append(f"Final recommendation failed: {e}")
                raise


async def run_dual_matching_pipeline(df_filtered, user_name, user_profile, api_key, model,
                                     chunk_size=50, min_score=8, additional_context=None,
                                     user_idx=None):
    """
    Run both get_value and give_value pipelines in parallel.

    Returns:
        Tuple of (get_result, give_result)
        where each result is (recommendations_text, all_scores_dict, status_messages)
    """
    # Shared rate limiter to stay under Gemini's 25 RPM rate limit
    rate_limiter = RateLimiter(max_per_minute=22)  # slightly under 25 to leave headroom

    get_task = run_matching_pipeline(
        df_filtered, user_name, user_profile, api_key, model,
        chunk_size=chunk_size, min_score=min_score, additional_context=additional_context,
        direction="get_value", user_idx=user_idx, rate_limiter=rate_limiter
    )
    give_task = run_matching_pipeline(
        df_filtered, user_name, user_profile, api_key, model,
        chunk_size=chunk_size, min_score=min_score, additional_context=additional_context,
        direction="give_value", user_idx=user_idx, rate_limiter=rate_limiter
    )
    return await asyncio.gather(get_task, give_task)


def save_output(full_name, content, output_dir, suffix=""):
    """
    Save the output to timestamped .md and .txt (Slack format) files.

    Args:
        suffix: Optional suffix for filename (e.g., "_get_value")

    Returns:
        Tuple of (md_filepath, txt_filepath)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = re.sub(r'[^\w]', '_', full_name.lower())
    base_filename = f"{timestamp}_{clean_name}_recommendations{suffix}"

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
