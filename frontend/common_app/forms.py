from django import forms

class LoginForm(forms.Form):
    email = forms.CharField(label='Email or phone', max_length=254)
    password = forms.CharField(widget=forms.PasswordInput)

class RegisterForm(LoginForm):
    name = forms.CharField(max_length=120)
    phone = forms.CharField(max_length=30, required=False)
    password = forms.CharField(min_length=5,widget=forms.PasswordInput)

class ForgotForm(forms.Form):
    email = forms.EmailField()

class ResetForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    password = forms.CharField(min_length=5,widget=forms.PasswordInput)

class ProfileForm(forms.Form):
    email = forms.EmailField(required=False)
    name = forms.CharField(max_length=120)
    phone = forms.CharField(max_length=30,required=False)

class UploadForm(forms.Form):
    purpose = forms.ChoiceField(choices=[])
    entity_id = forms.IntegerField(required=False,help_text='Menu item or review ID, when applicable')
    file = forms.FileField(help_text='JPEG, PNG or WebP, up to 5 MB')

    def __init__(self,*args,role='customer',**kwargs):
        super().__init__(*args,**kwargs)
        purposes = {'customer':['profile','review'],'restaurant':['profile','menu','fssai','gst','license'],'driver':['profile','license','rc','id_proof']}[role]
        self.fields['purpose'].choices = [(p,p.replace('_',' ').title()) for p in purposes]

    def clean_file(self):
        value = self.cleaned_data['file']
        if value.size > 5*1024*1024:
            raise forms.ValidationError('Maximum file size is 5 MB')
        return value
