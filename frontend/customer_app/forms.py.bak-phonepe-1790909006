from django import forms

class AddressForm(forms.Form):
    label = forms.CharField(max_length=80)
    details = forms.CharField(max_length=500, label='Selected address', widget=forms.TextInput(attrs={'readonly': True}))
    place_id = forms.CharField(required=False, max_length=255, widget=forms.HiddenInput)
    is_default = forms.BooleanField(required=False, label='Set as my default address')

    def clean(self):
        data = super().clean()
        if not data.get('place_id') and (not self.initial.get('details') or data.get('details') != self.initial.get('details')):
            self.add_error('details', 'Choose an address from the Google Maps suggestions.')
        return data


class CheckoutForm(forms.Form):
    mode = forms.ChoiceField(choices=[('delivery','Delivery (+ $30)'),('pickup','Pickup')])
    address_id = forms.TypedChoiceField(coerce=int,required=False,empty_value=None)
    promo_code = forms.CharField(required=False, max_length=40, label='Promo code')
    tip = forms.DecimalField(required=False, min_value=0, max_value=1000, decimal_places=2, initial=0)
    request_key = forms.CharField(widget=forms.HiddenInput)

class ReviewForm(forms.Form):
    restaurant = forms.IntegerField(min_value=1,max_value=5)
    driver = forms.IntegerField(min_value=1,max_value=5,required=False)
    text = forms.CharField(max_length=2000,widget=forms.Textarea)
