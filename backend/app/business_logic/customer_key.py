# backend/app/business_logic/customer_key.py

import re
from dataclasses import dataclass

# --- Normalization Suffixes ---
# Lowercased, stripped of trailing punctuation, and trimmed for matching.
# These are exact tokens to be removed from the end of a customer name.
# Order matters: more specific suffixes should come before general ones.
NORMALIZATION_SUFFIXES = [
    "pvt ltd",
    "private limited",
    "- customer",
    "ltd",
    "limited",
    "inc",
    "llp",
]

# --- Punctuation to remove and collapse ---
# Any character in this set will be replaced by a space.
PUNCTUATION_TO_REMOVE = re.compile(r"[.,&-]")


# --- Customer Reference for Matching ---
# Data structure used when resolving customer names.
@dataclass
class CustomerRef:
    customer_key: str
    display_name: str


# --- Normalization Function ---


def normalize(customer_raw: str) -> str:
    """
    Normalizes a raw customer name string into a consistent `customer_key`.

    Process:
    1. Convert to lowercase.
    2. Remove specified punctuation, replacing with spaces.
    3. Remove extra whitespace, leaving single spaces.
    4. Trim leading/trailing whitespace.
    5. Remove known trailing suffixes (case-insensitive, full token match).
    6. Trim whitespace again after suffix removal.
    """
    if not customer_raw:
        return ""

    # 1. Convert to lowercase
    normalized = customer_raw.lower()

    # 2. Remove punctuation, replace with spaces, collapse whitespace
    normalized = PUNCTUATION_TO_REMOVE.sub(" ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # 5. Remove known trailing suffixes
    for suffix in NORMALIZATION_SUFFIXES:
        # Construct a regex to match the suffix potentially preceded by whitespace at the end of the string.
        # example: "some company pvt ltd" -> remove " pvt ltd"
        # Make sure it matches as a whole word by anchoring.
        suffix_pattern = r"[\s]*" + re.escape(suffix) + r"$"

        # Repeatedly try to remove the suffix if it matches. This handles cases like "XYZ Ltd Ltd."
        # though typically one suffix is sufficient.
        while re.search(
            suffix_pattern, normalized, re.IGNORECASE
        ):  # Use IGNORECASE for robustness, though already lowercased
            normalized = re.sub(
                suffix_pattern, "", normalized, flags=re.IGNORECASE
            ).strip()
            normalized = re.sub(
                r"\s+", " ", normalized
            ).strip()  # Collapse spaces after removal

    # 6. Trim whitespace again
    return normalized.strip()


# Example usage (for testing purposes)
if __name__ == "__main__":
    test_cases = [
        ("ABC Pvt Ltd", "abc"),
        ("XYZ Corporation, Inc.", "xyz corporation"),
        ("Sample Company Limited", "sample company"),
        ("  Another-Customer Ltd.  ", "another customer"),
        ("Global Solutions LLP", "global solutions"),
        ("Exact Match", "exact match"),
        ("No Suffix", "no suffix"),
        ("Customer With Extra Spaces   ", "customer with extra spaces"),
        ("Special & Co.", "special co"),  # Removed & and collapsed space
        ("Test", "test"),  # No changes
        ("", ""),  # Empty string
        ("ABC Pvt. Ltd.", "abc"),  # Punctuation in suffix
        ("XYZ Corp LTD", "xyz corp"),  # Case and suffix variation
    ]

    for raw_name, expected_key in test_cases:
        actual_key = normalize(raw_name)
        print(
            f"Raw: '{raw_name}' -> Normalized: '{actual_key}' (Expected: '{expected_key}') - {'PASS' if actual_key == expected_key else 'FAIL'}"
        )
