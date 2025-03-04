from django import forms
from django.utils.safestring import mark_safe


class ReadOnlyURLWidget(forms.TextInput):
    """Custom widget to display the file field as a clickable URL."""

    def render(self, name, value, attrs=None, renderer=None):
        if value:
            return mark_safe(f'Currently : <a href=" {value}" target="_blank">{value}</a>')
        return super().render(name, value, attrs, renderer)
