from app.domain.policy import PAISE_PER_RUPEE


def format_rupees(paise: int) -> str:
    """₹120, ₹120.50: for messages shown to people (never parsed back)."""
    rupees, remainder = divmod(paise, PAISE_PER_RUPEE)
    return f"₹{rupees:,}" if remainder == 0 else f"₹{rupees:,}.{remainder:02d}"
