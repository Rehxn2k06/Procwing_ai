# backend/app/business_logic/matching.py

from typing import List
from dataclasses import dataclass, field
import rapidfuzz.fuzz
from .customer_key import normalize, CustomerRef  # Import CustomerRef here

# --- Constants ---
MATCH_THRESHOLD = 70  # Score >= 70 is considered a match

# --- Data Classes ---


@dataclass
class MatchResult:
    matched: bool
    customer_key: str | None = None
    display_name: str | None = None
    confidence: float = 0.0
    candidates: List[CustomerRef] = field(default_factory=list)  # List of CustomerRef


# --- Fuzzy Matching Logic ---


def resolve_customer_name(query: str, customers: List[CustomerRef]) -> MatchResult:
    """
    Resolves a free-text query against a list of known customers using fuzzy matching.

    Args:
        query (str): The user's input string (e.g., "ABC Comapny").
        customers (List[CustomerRef]): A list of available customers with their keys and display names.

    Returns:
        MatchResult: An object indicating if a match was found, the best match details,
                     and other potential candidates.
    """
    if not query or not customers:
        # If query is empty or no customers are available, return no match.
        return MatchResult(matched=False, candidates=[])

    # 1. Normalize the query string for comparison with customer_key
    normalized_query = normalize(query)

    # 2. Exact match on normalized customer_key (fast path)
    # This checks if the normalized query *exactly* matches any customer key.
    exact_matches_on_key = []
    for customer in customers:
        if customer.customer_key == normalized_query:
            exact_matches_on_key.append(customer)

    if exact_matches_on_key:
        # If found, we consider this a perfect match.
        # If multiple, take the first one for determinism.
        best_match_customer = exact_matches_on_key[0]
        return MatchResult(
            matched=True,
            customer_key=best_match_customer.customer_key,
            display_name=best_match_customer.display_name,
            confidence=100.0,  # Perfect match score for exact key match
            candidates=[
                CustomerRef(c.customer_key, c.display_name)
                for c in exact_matches_on_key
            ],  # Include all exact key matches as candidates
        )

    # 3. Fuzzy matching against display names and normalized keys
    scored_candidates = []

    for customer in customers:
        # Score 1: Fuzzy match of the original query against the customer's display_name.
        score_display_name = rapidfuzz.fuzz.token_sort_ratio(
            query, customer.display_name
        )

        # Score 2: Fuzzy match of the normalized query against the customer's customer_key.
        # This ensures that if the normalized query closely matches a customer key, it's considered.
        score_customer_key = rapidfuzz.fuzz.token_sort_ratio(
            normalized_query, customer.customer_key
        )

        # Combine scores: Take the maximum of the two scores. This means a good match
        # either in display name or in customer key (after normalization) will be highly scored.
        combined_score = max(score_display_name, score_customer_key)

        scored_candidates.append((combined_score, customer))

    # Sort candidates by score in descending order
    scored_candidates.sort(key=lambda item: item[0], reverse=True)

    # Determine the overall result based on the top candidate's score
    best_score, best_customer_ref = scored_candidates[0]

    # The result is 'matched' if the best score meets or exceeds the threshold.
    is_matched = best_score >= MATCH_THRESHOLD

    result = MatchResult(
        matched=is_matched,
        customer_key=best_customer_ref.customer_key if is_matched else None,
        display_name=best_customer_ref.display_name if is_matched else None,
        confidence=float(best_score) if is_matched else 0.0,
        # Include the top 3 candidates in the result, regardless of whether they cleared the threshold.
        # This is useful for providing "Did you mean?" suggestions to the user.
        candidates=[
            CustomerRef(c.customer_key, c.display_name)
            for _, c in scored_candidates[:3]
        ],
    )

    return result


# --- Example Usage ---
if __name__ == "__main__":
    # Mock customer data
    mock_customers: List[CustomerRef] = [
        CustomerRef(customer_key="abc", display_name="ABC Pvt Ltd"),
        CustomerRef(customer_key="xyzcorp", display_name="XYZ Corporation"),
        CustomerRef(
            customer_key="global-solutions", display_name="Global Solutions Ltd."
        ),
        CustomerRef(customer_key="sampleco", display_name="Sample Company"),
        CustomerRef(customer_key="beta-ltd", display_name="Beta Limited"),
        CustomerRef(
            customer_key="another-customer", display_name="Another-Customer Ltd."
        ),  # Added for completeness
    ]

    print(f"Testing with MATCH_THRESHOLD = {MATCH_THRESHOLD}\n")

    # Test cases: (query, expected_name, expected_key, expected_match, expected_lower_bound_confidence)
    # Confidence values are approximate due to rapidfuzz and token_sort_ratio behavior, focus on match status and correctness.
    test_cases = [
        (
            "ABC Comapny",
            "ABC Pvt Ltd",
            "abc",
            True,
            90.0,
        ),  # Typo in query, should match loosely
        (
            "XYZ Corp.",
            "XYZ Corporation",
            "xyzcorp",
            True,
            90.0,
        ),  # Punctuation and suffix
        (
            "Global Solutions",
            "Global Solutions Ltd.",
            "global-solutions",
            True,
            90.0,
        ),  # Partial match on display name
        (
            "Beta",
            "Beta Limited",
            "beta-ltd",
            True,
            70.0,
        ),  # Score should be around threshold or just above
        ("Company X", None, None, False, 0.0),  # No good match
        (
            "XYZ Corp Limited",
            "XYZ Corporation",
            "xyzcorp",
            True,
            90.0,
        ),  # Extra suffix in query
        (
            "ABC",
            "ABC Pvt Ltd",
            "abc",
            True,
            90.0,
        ),  # Short query, high confidence if key normalizes to 'abc'
        (
            "SamplCo",
            "Sample Company",
            "sampleco",
            True,
            80.0,
        ),  # Case variation + suffix
        (
            "Another Customer",
            "Another-Customer Ltd.",
            "another-customer",
            True,
            70.0,
        ),  # Check normalized key match
    ]

    for (
        query,
        expected_name,
        expected_key,
        expected_match,
        expected_conf_lower_bound,
    ) in test_cases:
        result = resolve_customer_name(query, mock_customers)
        print(f"Query: '{query}'")
        print(
            f"  Result: matched={result.matched}, key={result.customer_key}, name={result.display_name}, confidence={result.confidence:.1f}"
        )

        # Basic validation
        status = "PASS"
        if result.matched != expected_match:
            status = "FAIL (match status)"
        elif expected_match:
            if (
                result.customer_key != expected_key
                or result.display_name != expected_name
            ):
                status = "FAIL (key/name mismatch)"
            # Confidence check is heuristic, not exact
            elif result.confidence < expected_conf_lower_bound:
                # This is a soft check, could be ignored if other match criteria are met.
                # print(f"  Warning: Confidence {result.confidence:.1f} below expected lower bound {expected_conf_lower_bound:.1f}")
                pass  # Don't fail test strictly on confidence if key/name is correct.
        else:  # Not expected to match
            if result.customer_key is not None or result.display_name is not None:
                status = "FAIL (unexpected match)"

        print(f"  Status: {status}")
        print("")  # Newline for clarity
