from django import forms
from .models import FacturePartenaire
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

# ?? Formulaire d'importation du fichier Excel (admin uniquement)
class ImportExcelForm(forms.Form):
    fichier_excel = forms.FileField(label="Fichier Excel")

# ?? Formulaire pour téléverser une facture partenaire (PDF)
class FactureUploadForm(forms.ModelForm):
    class Meta:
        model = FacturePartenaire
        fields = ['facture_pdf']
        widgets = {
            'facture_pdf': forms.ClearableFileInput(attrs={'accept': '.pdf'})
        }

# ?? Formulaire de connexion personnalisé si je veux personnaliser plus tard
class ConnexionForm(AuthenticationForm):
    username = forms.CharField(label="Identifiant", max_length=100)
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)


# Recap/forms.py

from django import forms
from .models import FacturePartenaire

class FactureUploadForm(forms.ModelForm):
    class Meta:
        model = FacturePartenaire
        fields = ['facture_pdf']
        widgets = {
            'facture_pdf': forms.ClearableFileInput(
                attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.png'}
            ),
        }

