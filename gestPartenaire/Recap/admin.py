from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import reverse, path
from django.contrib.admin import SimpleListFilter
from .models import User, Activite, RecapMensuel, FacturePartenaire, PaiementCommission
from .views import import_excel_view
from django.db import transaction

# 🔧 Utilisateur partenaire
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'nomdist', 'numdist', 'is_partner', 'is_staff')
    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {'fields': ('numdist', 'is_partner')}),
    )
    search_fields = ('username', 'first_name', 'numdist')
    list_filter = ('is_partner', 'is_staff')

# 📊 Activité
class ActiviteAdmin(admin.ModelAdmin):
    list_display = ('get_partenaire_nom', 'cmouvmt', 'article', 'montant_ht', 'date_operation')
    list_filter = ('partenaire__nomdist', 'date_operation')
    search_fields = ('partenaire__nomdist', 'cmouvmt', 'article')
    change_list_template = "admin/Recap/activite_changelist.html"  # template custom

    def get_partenaire_nom(self, obj):
        return f"{obj.partenaire.nomdist} ({obj.partenaire.numdist})"
    get_partenaire_nom.short_description = 'Partenaire'

    # Ajout URL personnalisée pour import Excel
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import-excel/", self.admin_site.admin_view(import_excel_view), name="import-excel"),
        ]
        return custom_urls + urls

# 📄 Récap mensuel
class RecapMensuelAdmin(admin.ModelAdmin):
    list_display = ('lien_partenaire', 'mois', 'fichier_pdf', 'date_genere', 'facture_status')
    list_filter = ('partenaire', 'mois')
    search_fields = ('partenaire__nomdist', 'partenaire__numdist')

    def lien_partenaire(self, obj):
        if obj.partenaire:
            url = f"/admin/Recap/user/{obj.partenaire.id}/change/"
            return format_html('<a href="{}">{}</a>', url, obj.partenaire.first_name)
        return "-"
    lien_partenaire.short_description = "Partenaire"

    def facture_status(self, obj):
        facture = FacturePartenaire.objects.filter(recap=obj).first()
        if facture:
            return format_html('<span style="color:green;">📄 Facture envoyée</span>')
        return format_html('<span style="color:red;">❌ Aucune facture</span>')
    facture_status.short_description = "Facture partenaire"

# 📥 Facture partenaire
class FacturePartenaireAdmin(admin.ModelAdmin):
    list_display = ('partenaire_lien', 'recap_lien', 'facture_pdf', 'date_envoi', 'statut_traitement')
    list_filter = ('partenaire',)
    search_fields = ('partenaire__nomdist', 'partenaire__numdist')

    def partenaire_lien(self, obj):
        url = reverse('admin:Recap_user_change', args=[obj.partenaire_id])
        return format_html('<a href="{}">{}</a>', url, f"{obj.partenaire.nomdist} ({obj.partenaire.numdist})")
    partenaire_lien.short_description = "Partenaire"

    def recap_lien(self, obj):
        url = reverse('admin:Recap_recapmensuel_change', args=[obj.recap_id])
        return format_html('<a href="{}">{}</a>', url, obj.recap.mois.strftime("%B %Y"))
    recap_lien.short_description = "Récap Mensuel"

    def statut_traitement(self, obj):
        # Vérifie si un paiement existe pour ce récap + cette facture
        paiement = PaiementCommission.objects.filter(recap=obj.recap, facture=obj).first()
        if paiement:
            change_url = reverse('admin:Recap_paiementcommission_change', args=[paiement.id])
            if paiement.statut == "effectue":
                return format_html('<a href="{}" style="color:green;">✅ Payé</a>', change_url)
            else:
                return format_html('<a href="{}" style="color:orange;">⏳ En attente</a>', change_url)
        else:
            create_url = reverse('admin:Recap_paiementcommission_add')
            create_url = f"{create_url}?recap={obj.recap.id}&facture={obj.id}"
            return format_html('<a href="{}" style="color:red;">➕ Créer Paiement</a>', create_url)
    statut_traitement.short_description = "Traitement"

# 🎯 Filtre custom pour PaiementCommission
class PartenairePaiementFilter(SimpleListFilter):
    title = "Partenaire"
    parameter_name = "partenaire"

    def lookups(self, request, model_admin):
        partenaires = User.objects.filter(is_partner=True)
        return [(p.id, p.first_name) for p in partenaires]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(recap__partenaire__id=self.value())
        return queryset

# 💰 Paiement Commission
class PaiementCommissionAdmin(admin.ModelAdmin):
    list_display = ('partenaire_nom', 'recap', 'facture', 'statut', 'moyen_paiement', 'message_admin', 'date_validation')
    list_filter = (PartenairePaiementFilter, 'statut', 'moyen_paiement')
    search_fields = ('recap__partenaire__nomdist', 'facture__id')

    def partenaire_nom(self, obj):
        return obj.recap.partenaire.first_name
    partenaire_nom.short_description = "Nom du partenaire"

    # Actions rapides
    actions = ['marquer_en_attente', 'marquer_effectue']

    @admin.action(description="🔄 Marquer sélectionné(s) en attente")
    def marquer_en_attente(self, request, queryset):
        updated = queryset.update(statut="en_attente")
        self.message_user(request, f"{updated} paiement(s) marqué(s) en attente.", messages.WARNING)

    @admin.action(description="✅ Marquer sélectionné(s) comme effectué")
    def marquer_effectue(self, request, queryset):
        updated = queryset.update(statut="effectue")
        self.message_user(request, f"{updated} paiement(s) validé(s).", messages.SUCCESS)

# ✅ Enregistrement
admin.site.register(User, UserAdmin)
admin.site.register(Activite, ActiviteAdmin)
admin.site.register(RecapMensuel, RecapMensuelAdmin)
admin.site.register(FacturePartenaire, FacturePartenaireAdmin)
admin.site.register(PaiementCommission, PaiementCommissionAdmin)
