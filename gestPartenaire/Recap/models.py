# Recap/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# 🧑‍💼 Modèle personnalisé pour l'utilisateur
class User(AbstractUser):
    numdist = models.CharField(max_length=50, unique=True, null=True, blank=True)  # identifiant unique partenaire
    nomdist = models.CharField(max_length=255)
    is_partner = models.BooleanField(default=False)  # différencie les partenaires des admins

    def __str__(self):
        return self.nomdist

# 📁 Activité réalisée par un partenaire (importée via Excel)
from decimal import Decimal, ROUND_HALF_UP

class Activite(models.Model):
    partenaire = models.ForeignKey(User, on_delete=models.CASCADE)
    cmouvmt = models.CharField(max_length=255)  # activité effectuée (ex: PAYECH)
    montant_ttc = models.DecimalField(max_digits=12, decimal_places=2)
    montant_ht = models.DecimalField(max_digits=12, decimal_places=2)
    date_operation = models.DateField()
    article = models.CharField(max_length=255, blank=True, null=True)  # ex: "Echange Payant"
    is_echange_payant = models.BooleanField(default=False)
    
    def commission(self):
        taux = Decimal('0.04')
        return (self.montant_ht * taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        # ✅ Marquer automatiquement comme "Echange Payant"
        self.is_echange_payant = self.cmouvmt.upper() == "PAYECH"

        # ✅ Forcer les montants à être positifs si c’est une opération CREAT
        if self.cmouvmt.upper() == "CREAT":
            self.montant_ht = abs(self.montant_ht)
            self.montant_ttc = abs(self.montant_ttc)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.partenaire.username} - {self.date_operation}"


# 📄 Fichier PDF récapitulatif mensuel généré automatiquement
class RecapMensuel(models.Model):
    partenaire = models.ForeignKey(User, on_delete=models.CASCADE)
    mois = models.DateField()  # stocke le 1er jour du mois (ex: 2025-07-01)
    fichier_pdf = models.FileField(upload_to='recaps/')
    date_genere = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('partenaire', 'mois')  # <-- ajout contrainte unique

    def __str__(self):
        return f"Récapitulatif - {self.partenaire.nomdist} - {self.mois.strftime('%B %Y')}"
    


# 📤 Facture PDF envoyée par le partenaire
class FacturePartenaire(models.Model):
    partenaire = models.ForeignKey(User, on_delete=models.CASCADE)
    recap = models.ForeignKey(RecapMensuel, on_delete=models.CASCADE)
    facture_pdf = models.FileField(upload_to='factures/')
    date_envoi = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Facture {self.partenaire.nomdist} - {self.recap.mois.strftime('%B %Y')}"

# ✅ Statut du paiement de la facture (visible par l’admin et le partenaire)
class PaiementCommission(models.Model):
    MOYENS_PAIEMENT = [
        ("momo", "Mobile Money"),
        ("reversement", "Reversement"),
    ]

    recap = models.OneToOneField(RecapMensuel, on_delete=models.CASCADE)
    facture = models.OneToOneField(FacturePartenaire, on_delete=models.CASCADE)
    statut = models.CharField(max_length=20, choices=[
        ("en_attente", "En attente"),
        ("effectue", "Effectué")
    ])
    moyen_paiement = models.CharField(
        max_length=20,
        choices=MOYENS_PAIEMENT,
        blank=True,
        null=True
    )
    message_admin = models.TextField(blank=True, null=True)
    date_validation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Paiement - {self.recap.partenaire.nomdist} - {self.get_statut_display()}"


