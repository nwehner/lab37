from __future__ import annotations

from pydantic import BeforeValidator

# Dashboard filter <select>s submit an empty string for their "All ..." option;
# treat that the same as the param being omitted rather than failing enum
# validation or matching on an empty value.
EmptyStrToNone = BeforeValidator(lambda v: v or None)
