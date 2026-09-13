from django import forms

class AvailabilityForm(forms.Form):
    online = forms.BooleanField(required=False,label='Available for deliveries')
    vehicle_type = forms.CharField(max_length=80,required=False)
    vehicle_number = forms.CharField(max_length=80,required=False)
