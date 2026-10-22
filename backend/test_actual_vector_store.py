from app.services.rag.vector_store import add_transaction_documents, search_transactions

transactions = [
    {
        "page_content": "Transaction date: 2026-10-01. Type: expense. Amount: 500.00. Merchant: Foodpanda. Category: Food. Description: Dinner.",
        "metadata": {
            "transaction_id": 1,
            "user_id": 7,
            "date": "2026-10-01",
            "merchant": "Foodpanda",
            "category": "Food",
            "transaction_type": "expense",
            "amount": "-500.00",
        },
    },
    {
        "page_content": "Transaction date: 2026-10-02. Type: expense. Amount: 1500.00. Merchant: Daraz. Category: Shopping. Description: Electronics purchase.",
        "metadata": {
            "transaction_id": 2,
            "user_id": 7,
            "date": "2026-10-02",
            "merchant": "Daraz",
            "category": "Shopping",
            "transaction_type": "expense",
            "amount": "-1500.00",
        },
    },
]

ids = add_transaction_documents(transactions)

print(ids)

results = search_transactions(
    query="Where did I spend money on food?",
    user_id=7,
    k=2,
)

for result in results:
    print(result.page_content)
    print(result.metadata)
    print("---")