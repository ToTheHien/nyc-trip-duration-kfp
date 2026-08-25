"""The months KFP component: start/end month strings -> the ordered month list."""

from kfp import dsl

from components import image_for


@dsl.component(base_image=image_for("months"))
def expand_months(start_month: str, end_month: str) -> list[str]:
    from lib.months import month_range

    return month_range(start_month, end_month)
