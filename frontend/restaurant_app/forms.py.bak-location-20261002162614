from django import forms

class RestaurantForm(forms.Form):
    name = forms.CharField(max_length=120)
    description = forms.CharField(max_length=1000,required=False,widget=forms.Textarea)
    cuisine = forms.CharField(max_length=80)
    kind = forms.ChoiceField(choices=[('restaurant','Restaurant'),('store','Store')])
    address = forms.CharField(max_length=500)
    is_open = forms.BooleanField(required=False)
    opening = forms.RegexField(regex=r'^(?:[01]\d|2[0-3]):[0-5]\d$',initial='09:00')
    closing = forms.RegexField(regex=r'^(?:[01]\d|2[0-3]):[0-5]\d$',initial='22:00')
    delivery_minutes = forms.IntegerField(min_value=5,max_value=240,initial=30)

class MenuForm(forms.Form):
    name = forms.CharField(max_length=120)
    description = forms.CharField(max_length=1000,required=False,widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Short description for customers'}))
    category = forms.CharField(max_length=80,required=False,initial='General')
    price = forms.DecimalField(min_value=0.01,max_value=100000,decimal_places=2)
    veg = forms.BooleanField(required=False,initial=True)
    available = forms.BooleanField(required=False,initial=True)
    photo = forms.ImageField(required=False)
