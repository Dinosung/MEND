<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Reporting helpers with pandas, please. Write `target.py` with `monthly_revenue(sales)` that
takes a DataFrame with a datetime `date` column and an `amount` column and returns total
amount per calendar month as a Series indexed by month-end date, and `hourly_counts(events)`
that takes a DataFrame with a datetime `ts` column and returns the number of events per hour
as a Series.
