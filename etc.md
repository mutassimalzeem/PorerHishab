FIN-02 architecture
We're going to build:

                 Transactions
                      │
                      ▼
              Analytics Service
                      │
                      ▼
             Forecasting Service
                 /           \
                /             \
       Monthly baseline     Recent velocity
                \             /
                 \           /
                  ▼           ▼
               Forecast Engine
                      │
                      ▼
              Budget Forecast
                      │
                      ▼
              /forecast/budget


              The first version will answer:
"Based on my spending history, how much am I likely to spend next month?"

And eventually:
"Will I run out of money?"

"How much should I budget for food?"

"Can I save Tk 5,000 this month?"


3. Why we're doing this instead of jumping to Prophet
This is important for your portfolio.

Don't write:
"I used Prophet to forecast expenses."

That's easy.

Instead, Zyra will have a progression:


V1
Explainable statistical baseline
        ↓
V2
Trend + seasonality
        ↓
V3
Category-level forecasting
        ↓
V4
Cash depletion prediction
        ↓
V5
Eid/Ramadan/salary-cycle effects