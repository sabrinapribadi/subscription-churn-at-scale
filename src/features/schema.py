"""Feature schema shared by training and serving (no Spark import, so the serving image stays light)."""

CATEGORICAL = ["city", "gender", "registered_via", "last_payment_method"]
