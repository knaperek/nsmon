from django import forms

class CronFormField(forms.CharField):
    # default_validators = [_validate_CRON_string]
    def __init__(self, *args, **kwargs):  # required, label, initial, widget, help_text
        defaults = {'widget': CronWidget}
        kwargs.update(defaults)
        return super(CronFormField, self).__init__(*args, **kwargs)

    def validate(self, value):
        super(CronFormField, self).validate(value)
        # _validate_CRON_string(value)


class CronWidget(forms.TextInput):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'CrontabField'}
        if attrs is not None:
            final_attrs.update(attrs)
        super(CronWidget, self).__init__(attrs=final_attrs)

    class Media:
        css = {
            'all': ('cronfield/crontab_widget.css',)
        }
        js = ('jquery.js', 'cronfield/crontab_widget.js')

    # def render(self, name, value, attrs=None):
    #     widget_html = '<div>foo bar</div>'
    #     return super(CronWidget, self).render(name, value, attrs) + widget_html
