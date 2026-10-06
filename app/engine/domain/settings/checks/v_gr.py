from ..types import Settings


def check_v_gr(st: Settings) -> list:
    """В-Гр1: у каждого сотрудника ровно одна группа; В-Гр2: группа существует в Т-Группы."""
    empty = [("V_GR1", {"employee_id": e}) for e, g in st.employee_groups.items() if not g]
    unknown = [("V_GR2", {"employee_id": e, "group": g}) for e, g in st.employee_groups.items()
               if g and g not in st.groups]
    return empty + unknown
