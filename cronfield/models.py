import re
from django.db import models
from django.core.exceptions import ValidationError


def _validate_CRON_string(value):
    """ Validation routine for CRON string in TestingPlan """

    if value.strip() != value:
        raise ValidationError('Leading nor trailing spaces are allowed')
    columns = value.split()
    if columns != value.split(' '):
        raise ValidationError('Use only a single space as a column separator')

    if len(columns) != 5:
        raise ValidationError('Entry has to consist of exactly 5 columns')

    pattern = r'^(\*|\d+(-\d+)?(,\d+(-\d+)?)*)(/\d+)?$'
    p = re.compile(pattern)
    for i, c in enumerate(columns):
        if not p.match(c):
            raise ValidationError("Incorrect value {} in column {}".format(c, i+1))


class CronField(models.CharField):
    """ Model field implementing CRONTAB format checking and defining appropriate default widget. """
    description = "CRONTAB field"
    # default_validators = [_validate_CRON_string]

    def __init__(self, *args, **kwargs):
        # kwargs['validators'] = [_validate_CRON_string]
        defaults = {
            'help_text': 'Minute Hour Day Month Weekday',
            'default': '* * * * *',
            'max_length': 100,
        }
        defaults.update(kwargs)
        return super(CronField, self).__init__(*args, **defaults)

    def formfield(self, **kwargs):
        defaults = {'form_class': CronFormField}
        defaults.update(kwargs)
        return super(CronField, self).formfield(**defaults)

    def validate(self, value, model_instance):
        super(CronField, self).validate(value, model_instance)
        if self.editable:  # Skip validation for non-editable fields.
            _validate_CRON_string(value)
            

# TODO: move this to file forms.py and rename the CronFormField class to CronField (same as model class)
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



class TestModel(models.Model):
    name = models.CharField(max_length=50)
    CRON_string = CronField()
    dalsi = CronField()
    treti = CronField()

    def __unicode__(self):
        return self.name
    