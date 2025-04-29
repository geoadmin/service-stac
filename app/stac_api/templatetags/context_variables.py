from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def get_context_variable(context, name, default):
    """Retrieve a context variable from the template context, returning a default value if the
    variable is not defined.

    Accessing undefined variables will still render the template, but using this function prevents
    unnecessary stack traces in the logs.

    Use this tag in a template like this:

    {% get_context_variable '<name>' <default> as <name> %}
    {{ name }}

    """
    return context.get(name, default)
