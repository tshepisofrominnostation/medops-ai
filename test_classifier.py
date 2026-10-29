
"""Basic tests for the ticket classifier."""

from app.classifier import classify


# Each message should match a distinctive keyword in its category.
test_cases = [
    ("I need assistance updating my employee details.", "HR"),
    ("The hospital network is disconnected.", "IT & Medical Tech"),
    ("We have an outstanding invoice to pay.", "Finance"),
    ("There is a water leak in the ward.", "Operations"),
]

# Check each expected category against the classifier's output.
for message, expected_category in test_cases:
    actual_category, confidence = classify(message)

    print(f"\nMessage: {message}")
    print(f"Expected: {expected_category}")
    print(f"Actual:   {actual_category}")
    print(f"Confidence: {confidence}")

    # Fail the test if the predicted category is incorrect.
    assert actual_category == expected_category, (
        f"Expected {expected_category}, got {actual_category}"
    )

print("\nAll classifier tests passed.")
