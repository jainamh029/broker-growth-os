"""Synthetic fixtures for the AI demo and tests. All agencies and text here are invented."""

PROFILES = {
    "Ridgeline Risk Advisors": (
        "Ridgeline Risk Advisors is an independent agency in Austin, Texas with 14 licensed producers. We specialize in "
        "habitational and apartment portfolios, builders risk, and hard-to-place commercial property across Texas, "
        "Oklahoma and Louisiana. Our team also places umbrella and excess liability and general liability for contractors."),
    "Harborview Insurance Group": (
        "Harborview is a Boston, Massachusetts brokerage with a team of 6. Most of our book is restaurants, bars and "
        "hotels in Massachusetts and New York: liquor liability, general liability and cyber for the hospitality sector."),
    "Prairie Mutual Agency": (
        "Prairie Mutual Agency is a small family-run office serving our local community with auto and home policies."),
}

SUBMISSIONS = {
    "complete": (
        "Submission for Ridgeline Apartments LLC. Prior carrier: Acme Mutual (expiring $41,200). Loss runs attached, 5 years "
        "currently valued. Description of operations: 120-unit garden-style apartments. Building: 96,000 square feet, year built "
        "1998, construction type frame, TIV $14.2M. COIs attached for the landscaping subcontractor. Financial statements and revenue attached."),
    "missing_loss_runs_financials": (
        "Submission for Harborview Tavern Inc. Prior carrier: Northline Insurance. Description of operations: neighborhood bar and grill. "
        "Building 4,200 sq ft, year built 1975, occupancy restaurant. COIs attached. Loss runs not yet available. No financials provided."),
    "missing_property_prior_carrier": (
        "Submission for Delta Haulers LLC. Loss runs attached. Description of operations: regional trucking, 22 power units. "
        "Financial statements attached. COIs attached."),
    "empty": "Please quote this account ASAP.",
}
EXPECTED_MISSING = {
    "complete": [],
    "missing_loss_runs_financials": ["loss_runs", "financials"],
    "missing_property_prior_carrier": ["property_details", "prior_carrier"],
    "empty": ["loss_runs", "property_details", "risk_description", "financials", "prior_carrier", "cois"],
}
