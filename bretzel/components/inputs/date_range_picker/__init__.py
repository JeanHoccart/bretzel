"""Re-export the :class:`DateRangePicker` component."""

from bretzel.components.inputs.date_range_picker.date_range_picker import (
    DateRangePicker,
)
from bretzel.components.inputs.date_range_picker.theme import (
    DATE_RANGE_PICKER_THEME,
)

__all__ = ["DATE_RANGE_PICKER_THEME", "DateRangePicker"]
