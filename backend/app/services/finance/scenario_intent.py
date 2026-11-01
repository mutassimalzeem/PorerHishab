"""Small deterministic intent extractor; ambiguous language never becomes a run."""
import re
from decimal import Decimal

def parse_scenario_intent(question):
    q=question.strip().lower().rstrip("?.")
    prefix=r"what if (?:my )?"
    patterns=[
        (prefix+r"(?:rent|recurring expense) (?:goes up|increases) by ([0-9]+(?:\.[0-9]{1,2})?)(?: (?:bdt|per month))?", "recurring_expense_adjustment", 1, False),
        (prefix+r"(?:rent|recurring expense) (?:goes down|decreases) by ([0-9]+(?:\.[0-9]{1,2})?)(?: (?:bdt|per month))?", "recurring_expense_adjustment", -1, False),
        (prefix+r"(?:salary|income) (?:drops|decreases) ([0-9]+(?:\.[0-9]{1,2})?)%", "income_adjustment", -1, True),
        (prefix+r"(?:salary|income) (?:increases|rises) by ([0-9]+(?:\.[0-9]{1,2})?)(?: (?:bdt|per month))?", "income_adjustment", 1, False),
    ]
    for pattern,kind,sign,percent in patterns:
        match=re.fullmatch(pattern,q)
        if match:
            value=Decimal(match.group(1))*sign
            if percent and value < -100:break
            return {"status":"needs_confirmation","intent":"scenario","changes":[{"change_type":kind,"percentage" if percent else "amount":str(value),"currency":"BDT","frequency":"monthly","description":question}],"clarification":"Confirm the effective date and horizon in the scenario workspace before running."}
    save=re.fullmatch(prefix+r"(?:i )?save ([0-9]+(?:\.[0-9]{1,2})?) per month",q)
    if save:
        return {"status":"clarification_required","intent":"scenario","requested_monthly_savings":save.group(1),"changes":[],"clarification":"Is this your total monthly savings or an additional monthly contribution? Confirm the goal and effective date."}
    return {"status":"clarification_required","intent":"scenario","changes":[],"clarification":"Specify one change, its BDT amount or income percentage, effective date, and horizon. Use the workspace for purchases and goal changes."}
