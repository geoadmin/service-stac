from django.forms.widgets import Widget
from django.utils.safestring import mark_safe


class LabelWidget(Widget):
    """Custom widget to display a label without input"""

    def render(self, name, value, attrs=None, renderer=None):
        return mark_safe(f'<div class="readonly" >{value}</div>')
