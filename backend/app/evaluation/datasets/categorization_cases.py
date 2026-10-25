"""Evaluation dataset for transaction categorization (AI-12C).

Every case describes one transaction and pins the *expected pipeline
behaviour* — never a wishful category.  The labels follow the application's
existing taxonomy (:data:`app.services.categorization.categories.
ALLOWED_CATEGORIES`) and the rule engine in
:mod:`app.services.categorization.rules`.

Labeling rules
--------------
``expected_behavior`` is the ground truth, and it must be consistent with
the evidence the transaction carries:

* ``rule_classify`` — an obvious merchant/keyword match the deterministic
  engine is expected to win confidently.  Must carry ``expected_category``
  and ``is_ambiguous`` must be False.
* ``provider_required`` — input lacks enough evidence for a confident
  deterministic label (unknown merchants, garbled codes, ambiguous contexts).
  The safe offline outcome is *uncertainty*, i.e. ``Uncategorized``; if a
  provider is configured it may resolve the case.  These cases never carry
  ``expected_category``: guessing would create a confident label out of
  nothing, so they are scored on ambiguity safety, not on a category hit.
* ``never_classify`` — empty / whitespace-only input; must always end
  ``Uncategorized`` via the fallback path in every mode.
* ``user_correction`` — a confirmed correction for this merchant exists; it
  must take precedence over the rule engine (and any provider).
* ``custom_category`` — same precedence, but the corrected label is a user
  category outside the system taxonomy and must be preserved verbatim.

Ambiguity handle: ``is_ambiguous=True`` cases must NOT be confidently
guessed by the rules-only engine — a lucky guess must not buy a pass.

Corrections are scoped per merchant: ``user_context`` holds exactly one
``confirmed_correction`` entry, whose merchant must be unique across the
whole dataset (see the dataset self-check in tests) so a preference never
bleeds into neighbouring cases.

Provider involvement is tested via injected offline stubs (see the runner /
tests); this file needs no credentials and no network.
"""

ALLOWED_BEHAVIORS = (
    "rule_classify",
    "provider_required",
    "never_classify",
    "user_correction",
    "custom_category",
)

# Deterministic noise builders for the long-input cases.
_NOISE_TOKEN = "q7z shipmentnote "
_TAIL_A = " restock run kitchen ledger "
_TAIL_B = " nothing actionable in this shipment record "


def _long_description(keyword: str | None, length: int = 900) -> str:
    """Deterministic long description with an optional embedded keyword."""
    noise = _NOISE_TOKEN * (length // len(_NOISE_TOKEN) + 1)
    core = keyword or ""
    return f"{noise.strip()} {_TAIL_A}{core}{_TAIL_B}".strip()


def correction(merchant: str, category: str) -> dict:
    """Build the ``user_context`` payload for one confirmed correction."""
    return {"confirmed_correction": {"merchant": merchant, "category": category}}


EVALUATION_CASES = [
    # ------------------------------------------------ clear_merchant: obvious
    # rule_classify — merchant name is the strong signal.
    {"id": "cat_merchant_netflix",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Netflix", "description": "MONTHLY SUBSCRIPTION AUTO-DEBIT",
     "expected_category": "Subscription"},

    {"id": "cat_merchant_spotify",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Spotify", "description": "PREMIUM FAMILY PLAN",
     "expected_category": "Subscription"},

    {"id": "cat_merchant_youtube_premium",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "YouTube Premium", "description": "MONTHLY PLAN",
     "expected_category": "Subscription"},

    {"id": "cat_merchant_amazon_prime",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Amazon Prime", "description": "MEMBERSHIP RENEWAL",
     "expected_category": "Subscription"},

    {"id": "cat_merchant_foodpanda",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Foodpanda", "description": "ORDER FP-DHAKA-2210",
     "expected_category": "Food"},

    {"id": "cat_merchant_kfc",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "KFC Dhanmondi", "description": "IN-STORE BUY",
     "expected_category": "Food"},

    {"id": "cat_merchant_pizza_hut",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Pizza Hut", "description": "WEEKEND ORDER",
     "expected_category": "Food"},

    {"id": "cat_merchant_starbucks",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Starbucks Gulshan", "description": "CAFE BILL",
     "expected_category": "Food"},

    {"id": "cat_merchant_uber",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Uber", "description": "RIDE FARE BANANI",
     "expected_category": "Transport"},

    {"id": "cat_merchant_obhai",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Obhai", "description": "BIKE FARE",
     "expected_category": "Transport"},

    {"id": "cat_merchant_shohoz",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Shohoz", "description": "TICKET DESK FARE",
     "expected_category": "Transport"},

    {"id": "cat_merchant_agora",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Agora", "description": "GULSHAN OUTLET BILL",
     "expected_category": "Groceries"},

    {"id": "cat_merchant_meena_bazar",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Meena Bazar", "description": "WEEKLY STOCK",
     "expected_category": "Groceries"},

    {"id": "cat_merchant_unimart",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Unimart", "description": "HOUSEHOLD BUY",
     "expected_category": "Groceries"},

    {"id": "cat_merchant_daraz",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Daraz", "description": "ONLINE PARCEL ORDER",
     "expected_category": "Shopping"},

    {"id": "cat_merchant_desco",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "DESCO", "description": "METER BILL MARCH",
     "expected_category": "Bills"},

    {"id": "cat_merchant_grameenphone",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Grameenphone", "description": "POSTPAID CHARGES",
     "expected_category": "Bills"},

    {"id": "cat_merchant_salary_deposit",
     "group": "clear_merchant", "expected_behavior": "rule_classify",
     "merchant": "Employer Ltd", "description": "MONTHLY SALARY CREDIT",
     "expected_category": "Salary"},

    # ------------------------------------------- clear_description: word-level
    # rule_classify — the description text carries the strong signal.
    {"id": "cat_desc_restaurant_dinner",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Local Eats", "description": "dinner at the restaurant",
     "expected_category": "Food"},

    {"id": "cat_desc_lunch_office",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Office Canteen", "description": "lunch bill",
     "expected_category": "Food"},

    {"id": "cat_desc_groceries_weekly",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Neighbourhood Store", "description": "groceries restock",
     "expected_category": "Groceries"},

    {"id": "cat_desc_supermarket_run",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Card Swipe 4412", "description": "supermarket weekly run",
     "expected_category": "Groceries"},

    {"id": "cat_desc_internet_bill",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Fiber ISP", "description": "monthly internet bill",
     "expected_category": "Bills"},

    {"id": "cat_desc_electricity_bill",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Meter Agent", "description": "electricity bill payment",
     "expected_category": "Bills"},

    {"id": "cat_desc_send_money",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Wallet Top-Up Desk", "description": "send money to elder brother",
     "expected_category": "Transfer"},

    {"id": "cat_desc_npsb",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Mobile App", "description": "NPSB transfer slip",
     "expected_category": "Transfer"},

    {"id": "cat_desc_bkash_cash_out",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "bKash Agent", "description": "cash out at the counter",
     "expected_category": "Transfer"},

    {"id": "cat_desc_house_rent",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Landlord Reza", "description": "house rent for April",
     "expected_category": "Housing"},

    {"id": "cat_desc_pharmacy",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Corner Store", "description": "pharmacy purchase",
     "expected_category": "Healthcare"},

    {"id": "cat_desc_clinic_visit",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Local Center", "description": "clinic consultation fee",
     "expected_category": "Healthcare"},

    {"id": "cat_desc_tuition",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Accounts Desk", "description": "tuition installment one",
     "expected_category": "Education"},

    {"id": "cat_desc_school_fee",
     "group": "clear_description", "expected_behavior": "rule_classify",
     "merchant": "Accounts Desk", "description": "school fee payment slip",
     "expected_category": "Education"},

    # ---------------------------------------------- similar_outcome: ordering
    # rule_classify — near-identical texts that must land in different
    # categories; each pins rule ordering and word-boundary logic.
    {"id": "cat_pair_pathao_food",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Pathao", "description": "PATHAO FOOD dinner delivery",
     "expected_category": "Food"},

    {"id": "cat_pair_pathao_ride",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Pathao", "description": "pathao bike ride to office",
     "expected_category": "Transport"},

    {"id": "cat_pair_pathao_ride_food_promo",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Pathao", "description": "RIDE FOOD promo checkout",
     "expected_category": "Food"},

    {"id": "cat_pair_amazon_prime",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Amazon", "description": "PRIME renewal charge",
     "expected_category": "Subscription"},

    {"id": "cat_pair_amazon_marketplace",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Amazon", "description": "kitchen appliance order",
     "expected_category": "Shopping"},

    {"id": "cat_pair_bkash_transfer",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "bKash", "description": "bkash transfer to savings wallet",
     "expected_category": "Transfer"},

    {"id": "cat_pair_bkash_supershop",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "bKash", "description": "payment at supershop counter",
     "expected_category": "Groceries"},

    {"id": "cat_pair_school_fee",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Accounts Desk", "description": "school fee for term two",
     "expected_category": "Education"},

    {"id": "cat_pair_school_supplies",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Pickaboo", "description": "stationery and bags order",
     "expected_category": "Shopping"},

    {"id": "cat_pair_house_rent",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Rent Collection", "description": "rent settled for March",
     "expected_category": "Housing"},

    {"id": "cat_pair_landlord_ref",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Payment Desk", "description": "landlord confirmation slip",
     "expected_category": "Housing"},

    {"id": "cat_pair_university_tuition",
     "group": "similar_outcome", "expected_behavior": "rule_classify",
     "merchant": "Campus Bursar", "description": "tuition spring semester",
     "expected_category": "Education"},

    # ---------------------------------------------------- language: Bangla
    {"id": "cat_bangla_chaldal",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "চালডাল থেকে মাসিক বাজার নেওয়া হয়েছে",
     "expected_category": "Groceries"},

    {"id": "cat_bangla_foodpanda",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "ফুডপান্ডা অর্ডার কনফার্মড",
     "expected_category": "Food"},

    {"id": "cat_bangla_electricity",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "বিদ্যুৎ বিল পরিশোধ করা হয়েছে",
     "expected_category": "Bills"},

    {"id": "cat_bangla_salary",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "মাসিক বেতন প্রাপ্তি হয়েছে",
     "expected_category": "Salary"},

    {"id": "cat_bangla_rickshaw",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "রিকশা ভাড়া দিয়েছি",
     "expected_category": "Transport"},

    {"id": "cat_bangla_house_rent",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "মাসিক বাসা ভাড়া জমা দিয়েছি",
     "expected_category": "Housing"},

    {"id": "cat_bangla_medicine",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "ওষুধ কেনা হয়েছে",
     "expected_category": "Healthcare"},

    {"id": "cat_bangla_school_fee",
     "group": "language_bangla", "expected_behavior": "rule_classify",
     "merchant": None, "description": "স্কুল ফি পরিশোধ",
     "expected_category": "Education"},

    {"id": "cat_bangla_ambiguous_split",
     "group": "language_bangla", "expected_behavior": "provider_required",
     "merchant": None, "description": "মাসিক খরচ ভাগ করে নেওয়া হয়েছে",
     "is_ambiguous": True},

    {"id": "cat_bangla_ambiguous_household",
     "group": "language_bangla", "expected_behavior": "provider_required",
     "merchant": None, "description": "বাড়িতে লোক ডেকেছিল কাজের জন্য",
     "is_ambiguous": True},

    {"id": "cat_bangla_ambiguous_decoration",
     "group": "language_bangla", "expected_behavior": "provider_required",
     "merchant": None, "description": "সাজসজ্জার জিনিস কেনা হয়েছে",
     "is_ambiguous": True},

    {"id": "cat_bangla_ambiguous_deposit",
     "group": "language_bangla", "expected_behavior": "provider_required",
     "merchant": None, "description": "অনলাইনে টাকা পাঠানো হয়েছে",
     "is_ambiguous": True},

    # ------------------------------------------------------ language: mixed
    {"id": "cat_mixed_chaldal",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": "Chaldal", "description": "চালডাল থেকে অর্ডার নম্বর SEVEN",
     "expected_category": "Groceries"},

    {"id": "cat_mixed_house_rent",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": None, "description": "বাসা ভাড়া + maintenance part for March",
     "expected_category": "Housing"},

    {"id": "cat_mixed_uber",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": "Uber", "description": "রাতের trip ভাড়া",
     "expected_category": "Transport"},

    {"id": "cat_mixed_daraz",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": "Daraz", "description": "টিফিন বক্স অর্ডার",
     "expected_category": "Shopping"},

    {"id": "cat_mixed_send_money",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": "Cell Wallet", "description": "Send money করা হয়েছে",
     "expected_category": "Transfer"},

    {"id": "cat_mixed_supermarket",
     "group": "language_mixed", "expected_behavior": "rule_classify",
     "is_mixed_language": True,
     "merchant": "Shwapno", "description": "মাসিক স্টক আপ করা হলো",
     "expected_category": "Groceries"},

    {"id": "cat_mixed_ambiguous_team_cost",
     "group": "language_mixed", "expected_behavior": "provider_required",
     "is_mixed_language": True, "is_ambiguous": True,
     "merchant": None, "description": "Team খরচ ভাগ করা হয়েছে"},

    {"id": "cat_mixed_ambiguous_payment",
     "group": "language_mixed", "expected_behavior": "provider_required",
     "is_mixed_language": True, "is_ambiguous": True,
     "merchant": None, "description": "Payment সম্পন্ন অফিস সংক্রান্ত"},

    {"id": "cat_mixed_ambiguous_gift",
     "group": "language_mixed", "expected_behavior": "provider_required",
     "is_mixed_language": True, "is_ambiguous": True,
     "merchant": None, "description": "কাজের মানুষকে অতিরিক্ত amount দেওয়া হলো"},

    {"id": "cat_mixed_ambiguous_deposit",
     "group": "language_mixed", "expected_behavior": "provider_required",
     "is_mixed_language": True, "is_ambiguous": True,
     "merchant": None, "description": "অতিরিক্ত টাকা জমা wallet App এ"},

    # ------------------------------------------------------ unknown_merchant
    # Garbled codes, unmatched merchants, no usable evidence.
    {"id": "cat_unknown_pos_code",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "GNP*BD0171202026", "description": "POS TRANSACTION REF 4412"},

    {"id": "cat_unknown_card_swipe",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "XYZ Trading House", "description": "CARD PURCHASE 8815"},

    {"id": "cat_unknown_service_fee",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Therap BD", "description": "SERVICE FEE"},

    {"id": "cat_unknown_adjustment",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "cssoffice01", "description": "ADJUSTMENT ENTRY"},

    {"id": "cat_unknown_courier",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Despatch Courier", "description": "cash on delivery charge"},

    {"id": "cat_unknown_work_order",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Creative IT Limited", "description": "WORK ORDER MARCH"},

    {"id": "cat_unknown_dry_clean",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Sunlit Cleaners", "description": "FABRIC CARE BILL"},

    {"id": "cat_unknown_router",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "RouterBD Retail", "description": "WIFI ROUTER FIRMWARE BUNDLE"},

    {"id": "cat_unknown_grocer_wallet",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Grocer Points Wallet", "description": "MONTHLY CREDIT PACK"},

    {"id": "cat_unknown_promo_credits",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Freebie Zone", "description": "PROMOTIONAL CREDITS"},

    {"id": "cat_unknown_ngo",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "এনজিও কর্মসূচির সদস্য ফি জমা"},

    {"id": "cat_unknown_garbled",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "\x07\x1e receipt fragment malformed"},

    {"id": "cat_unknown_vendor_recon",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Vendor Recon Desk", "description": "STATEMENT LINE MATCH"},

    {"id": "cat_unknown_ledger_entry",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Ledger Sync Service", "description": "AUTO-RECONCILED ROW"},

    {"id": "cat_unknown_holder_fee",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Card Holder Services", "description": "ANNUAL FEE WAIVER"},

    {"id": "cat_unknown_counter_sale",
     "group": "unknown_merchant", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Reusable Mart", "description": "COUNTER SALE NO RECEIPT"},

    # ---------------------------------------------------- ambiguous_context
    # Realistic snippets where the purpose is genuinely under-specified.
    {"id": "cat_ambig_vendor_payment",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "vendor payment adjustment"},

    {"id": "cat_ambig_reimbursement",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "reimbursement pending approval"},

    {"id": "cat_ambig_remittance",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "overseas remittance split entry"},

    {"id": "cat_ambig_contribution",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "contribution collected for team gift"},

    {"id": "cat_ambig_utility_word",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "utility service settlement pending"},

    {"id": "cat_ambig_brokerage",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "stock market brokerage fee"},

    {"id": "cat_ambig_purpose_unstated",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "purpose not stated on the wallet debit"},

    {"id": "cat_ambig_maintenance",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "monthly household maintenance share"},

    {"id": "cat_ambig_refund_correction",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "refund correction entry posted"},

    {"id": "cat_ambig_flexiload",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "mobile flexiload done for a friend"},

    {"id": "cat_ambig_resold_box",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "box delivery unopened and resold"},

    {"id": "cat_ambig_shared_bill",
     "group": "ambiguous_context", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "shared bill settle-up among flatmates"},

    # ------------------------------------------------ misleading_keywords
    # Decoy words whose harm depends on rule ordering; each asserts the
    # ordering the engine is expected to keep.
    {"id": "cat_decoy_grocery_shopping",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "monthly grocery shopping list – supershop run",
     "expected_category": "Groceries",
     "notes": "The word 'shopping' is a decoy; the groceries rule must win."},

    {"id": "cat_decoy_taxi_dinner",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "taxi fare to the dinner reservation",
     "expected_category": "Transport",
     "notes": "Transit term comes before the food rule; fare is the purpose."},

    {"id": "cat_decoy_lunch_deli",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "lunch catering ordered from the grocery deli",
     "expected_category": "Food",
     "notes": "lunch appears before the groceries rule; the meal is the purpose."},

    {"id": "cat_decoy_bank_autodebit",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "electricity bill auto-debit set up at the bank",
     "expected_category": "Bills",
     "notes": "'bank' is not 'bank transfer'; the utility bill phrase wins."},

    {"id": "cat_decoy_hospital_uber",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "uber ride to the hospital visit",
     "expected_category": "Transport",
     "notes": "The fare is the transaction; the hospital mention is context."},

    {"id": "cat_decoy_pharmacy_amazon",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "amazon order placed for pharmacy items",
     "expected_category": "Shopping",
     "notes": "Marketplace order dominates; the items list is category-suggestive only."},

    {"id": "cat_decoy_restaurant_desco",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": "Meter Office", "description": "receipt printed next to the restaurant desk – wasa note",
     "expected_category": "Food",
     "notes": "restaurant appears before the utility terms."},

    {"id": "cat_decoy_school_transfer",
     "group": "misleading_keywords", "expected_behavior": "rule_classify",
     "merchant": None, "description": "school fee booked via bank transfer",
     "expected_category": "Transfer",
     "notes": "Transfer instrument rule precedes the education keyword."},

    {"id": "cat_decoy_gym_subscription",
     "group": "misleading_keywords", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Fitness First? (unmatched)", "description": "gym subscription renewal untracked by rules",
     "notes": "'subscription' here is prose, not the brand keywords; rules must not bite."},

    {"id": "cat_decoy_insurance_premium",
     "group": "misleading_keywords", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": None, "description": "insurance premium annual renewal"},

    {"id": "cat_decoy_wedding_deposit",
     "group": "misleading_keywords", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Pearly Banquet? (unmatched)", "description": "hall booking deposit for the ceremony"},

    # ------------------------------------------------ --------- long input
    {"id": "cat_long_supershop_embedded",
     "group": "long_input", "expected_behavior": "rule_classify",
     "merchant": "Bulk Fulfilment", "description": _long_description("supershop"),
     "expected_category": "Groceries",
     "notes": "Keyword buried deep in an unusually long description."},

    {"id": "cat_long_noise_only",
     "group": "long_input", "expected_behavior": "provider_required",
     "is_ambiguous": True,
     "merchant": "Log Collector", "description": _long_description(None),
     "notes": "Very long text with no evidence at all."},

    # ------------------------------------------------------ malformed_input
    {"id": "cat_empty_all_fields",
     "group": "malformed_input", "expected_behavior": "never_classify",
     "merchant": None, "description": None},

    {"id": "cat_empty_whitespace_only",
     "group": "malformed_input", "expected_behavior": "never_classify",
     "merchant": "   ", "description": " \t\n "},

    {"id": "cat_empty_tab_merchant",
     "group": "malformed_input", "expected_behavior": "never_classify",
     "merchant": "\t", "description": "\n"},

    {"id": "cat_empty_mixed_whitespace",
     "group": "malformed_input", "expected_behavior": "never_classify",
     "merchant": " \x0b ", "description": "\x0c"},

    {"id": "cat_empty_amount_only",
     "group": "malformed_input", "expected_behavior": "never_classify",
     "merchant": None, "description": None,
     "user_context": {"amount": "-123.00"},
     "notes": "An amount without text gives the engine nothing to classify."},

    # ---------------------------------------------- user-confirmed corrections
    {"id": "cat_correction_foodpanda_mart",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "Foodpanda Mart", "description": "MONTHLY GROCERY BASKET",
     "user_context": correction("Foodpanda Mart", "Groceries"),
     "notes": "Correction conflicts with the Foodpanda → Food rule."},

    {"id": "cat_correction_starbucks_reserve",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "Starbucks Reserve", "description": "WEEKLY VISIT",
     "user_context": correction("Starbucks Reserve", "Coffee"),
     "notes": "Correction uses an allowed legacy label over the Food rule."},

    {"id": "cat_correction_uber_fleet",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "Uber Fleet", "description": "MONTHLY PLAN PAYMENT",
     "user_context": correction("Uber Fleet", "Business"),
     "notes": "Correction conflicts with the Uber → Transport rule."},

    {"id": "cat_correction_rooftop_restaurant",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "Rooftop Restaurant Deal", "description": "TEAM DINING NIGHT",
     "user_context": correction("Rooftop Restaurant Deal", "Entertainment"),
     "notes": "Budgeted as entertainment by the user; conflicts with the Food rule."},

    {"id": "cat_correction_ride_share_family",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "RideShare Family Plan", "description": "ELDER CARE RIDES",
     "user_context": correction("RideShare Family Plan", "Healthcare"),
     "notes": "User context (elder-care transport) overrides the Transport rule."},

    {"id": "cat_correction_star_local_store",
     "group": "corrected_categories", "expected_behavior": "user_correction",
     "merchant": "Star Local Store", "description": "VILLAGE PURCHASE",
     "user_context": correction("Star Local Store", "Groceries"),
     "notes": "Plain correction for a merchant no rule would have matched."},

    # -------------------------------------------------------- custom categories
    {"id": "cat_custom_family_support",
     "group": "custom_categories", "expected_behavior": "custom_category",
     "merchant": "Mama's Shop", "description": "MONTHLY SUPPLY SHARE",
     "user_context": correction("Mama's Shop", "Family support"),
     "notes": "Custom label outside ALLOWED_CATEGORIES must be preserved verbatim."},

    {"id": "cat_custom_domestic_help",
     "group": "custom_categories", "expected_behavior": "custom_category",
     "merchant": "Rina (home help)", "description": "STIPEND TRANSFERRED",
     "user_context": correction("Rina (home help)", "Domestic help")},

    {"id": "cat_custom_charity",
     "group": "custom_categories", "expected_behavior": "custom_category",
     "merchant": "Sabuj Chhaya", "description": "DONATION DRIVE SUPPORT",
     "user_context": correction("Sabuj Chhaya", "Donation")},

    {"id": "cat_custom_land_lease",
     "group": "custom_categories", "expected_behavior": "custom_category",
     "merchant": "Bilash Farm Lease", "description": "SEASONAL PLOT PAYMENT",
     "user_context": correction("Bilash Farm Lease", "Land lease")},

    {"id": "cat_custom_tuition_support",
     "group": "custom_categories", "expected_behavior": "custom_category",
     "merchant": "Dhaka Grammar Desk", "description": "STIPEND FOR STUDIES",
     "user_context": correction("Dhaka Grammar Desk", "Tuition support")},
]

CATEGORIZATION_EVALUATION_CASES = EVALUATION_CASES
