from django import forms
from django.utils.safestring import mark_safe


class LabelWidget(forms.TextInput):
    """Custom widget to display a label without input"""

    def render(self, name, value, attrs=None, renderer=None):
        if value:
            return mark_safe(f'{value}')
        return super().render(name, value, attrs, renderer)
