from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.urls import reverse_lazy
from datetime import datetime, date
from calendar import monthrange
from decimal import Decimal
import pandas as pd
from io import BytesIO
from xhtml2pdf import pisa
from django.db import transaction

from .models import User, Activite, RecapMensuel, FacturePartenaire, PaiementCommission
from .forms import ImportExcelForm, FactureUploadForm

# ---------------------
# Admin check decorator
# ---------------------
def admin_required(view_func):
    return user_passes_test(lambda u: u.is_staff)(view_func)

# ---------------------
# Connexion personnalisée
# ---------------------
def connexion_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard') if user.is_partner else redirect('admin:index')
    else:
        form = AuthenticationForm()
    return render(request, 'Recap/login.html', {'form': form})


# ---------------------
# Changement mot de passe
# ---------------------
class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'Recap/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

class CustomPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'Recap/password_change_done.html'

# ---------------------
# Import Excel Admin
# ---------------------
import os
def import_excel_view(request):
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')

        if not excel_file:
            messages.error(request, "Aucun fichier sélectionné.")
            return render(request, "Recap/import_excel.html")

        try:
            extension = os.path.splitext(excel_file.name)[1].lower()
            if extension not in ['.xls', '.xlsx']:
                messages.error(request, "Fichier non pris en charge (.xls ou .xlsx uniquement).")
                return render(request, "Recap/import_excel.html")

            # 🔍 Lecture brute
            if extension == '.xls':
                df = pd.read_excel(excel_file, engine='xlrd', header=None)
            else:
                df = pd.read_excel(excel_file, engine='openpyxl', header=None)

            colonnes_necessaires = ['NUMDIST', 'NOMDIST', 'CMOUVMT',
                                    'MONTANT_TTC', 'DATE', 'LARTICLE']
            header_row_index = None
            for i in range(min(10, len(df))):
                row_values = df.iloc[i].astype(str).str.strip().str.upper().tolist()
                if all(col in row_values for col in colonnes_necessaires):
                    header_row_index = i
                    break

            if header_row_index is None:
                messages.error(request, "Impossible de détecter les colonnes dans le fichier Excel.")
                return render(request, "Recap/import_excel.html")

            # 🔄 Relire proprement
            df = pd.read_excel(
                excel_file,
                header=header_row_index,
                engine='openpyxl' if extension == '.xlsx' else 'xlrd'
            )
            df.columns = df.columns.str.strip().str.upper()
            df = df[colonnes_necessaires]

            # Nettoyage colonnes string
            for col in ['NUMDIST', 'NOMDIST', 'CMOUVMT', 'LARTICLE']:
                df[col] = df[col].astype(str).str.strip()

            # ✅ Correction NUMDIST (supprime ".0")
            df["NUMDIST"] = df["NUMDIST"].str.replace(r"\.0$", "", regex=True)

            # Conversion TTC → numérique
            df["MONTANT_TTC"] = (
                df["MONTANT_TTC"]
                .astype(str)
                .str.replace(r"[^\d,.\-]", "", regex=True)
                .str.replace(",", ".", regex=False)
            )
            df["MONTANT_TTC"] = pd.to_numeric(df["MONTANT_TTC"], errors="coerce").fillna(0)

            # Calcul HT
            df["MONTANT_HT"] = (df["MONTANT_TTC"] / 1.18).round(2)

            # Conversion DATE
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

            # Supprimer lignes invalides
            df_clean = df.dropna(subset=["DATE", "NUMDIST", "NOMDIST", "MONTANT_TTC"])

            # Préparer utilisateurs
            numdists_existants = {
                u.username: u for u in User.objects.filter(username__in=df_clean['NUMDIST'].unique())
            }
            utilisateurs_a_creer = []
            utilisateurs_a_sauver = []

            for numdist_unique in df_clean['NUMDIST'].unique():
                if not numdist_unique.strip():
                    continue  # ⚡ évite utilisateurs vides

                # 🚨 Empêcher collision avec les admins
                if User.objects.filter(username=numdist_unique, is_staff=True).exists():
                    print(f"⚠️ NUMDIST '{numdist_unique}' correspond déjà à un admin, ignoré.")
                    continue

                user = numdists_existants.get(numdist_unique)
                nomdist_unique = df_clean.loc[df_clean['NUMDIST'] == numdist_unique, 'NOMDIST'].iloc[0]

                if not user:
                    user = User(
                        username=numdist_unique,
                        numdist=numdist_unique,
                        nomdist=nomdist_unique,
                        first_name=nomdist_unique,
                        is_partner=True,
                        is_staff=False,
                        is_active=True,
                    )
                    user.set_password(numdist_unique)
                    utilisateurs_a_creer.append(user)
                    numdists_existants[numdist_unique] = user
                elif user.nomdist != nomdist_unique:
                    user.nomdist = nomdist_unique
                    utilisateurs_a_sauver.append(user)

            lignes_ignoreres_manque_info = 0
            lignes_ignoreres_erreur = 0
            lignes_importees = 0
            activites_to_create = []

            with transaction.atomic():
                if utilisateurs_a_creer:
                    User.objects.bulk_create(utilisateurs_a_creer)
                if utilisateurs_a_sauver:
                    User.objects.bulk_update(utilisateurs_a_sauver, ['nomdist'])

                numdists_existants = {
                    u.username: u for u in User.objects.filter(username__in=df_clean['NUMDIST'].unique())
                }

                for idx, row in df_clean.iterrows():
                    try:
                        numdist = str(row.NUMDIST).strip()
                        nomdist = str(row.NOMDIST).strip()
                        cmouvmt = str(row.CMOUVMT).strip().upper()
                        montant_ht = row.MONTANT_HT
                        montant_ttc = row.MONTANT_TTC
                        date_op = row.DATE
                        article = str(row.LARTICLE).strip()

                        if not numdist or not nomdist or not cmouvmt or pd.isna(date_op) or pd.isna(montant_ttc):
                            lignes_ignoreres_manque_info += 1
                            continue

                        # ✅ Transformation MODART → CREAT si Terminal + montant 1000 ou 5000
                        if cmouvmt == "MODART" and article.startswith("Terminal") and montant_ttc in [1000, 5000]:
                            cmouvmt = "CREAT"

                        user = numdists_existants.get(numdist)
                        if not user:
                            lignes_ignoreres_manque_info += 1
                            continue

                        activite = Activite(
                            partenaire=user,
                            cmouvmt=cmouvmt,
                            montant_ttc=montant_ttc,
                            montant_ht=montant_ht,
                            date_operation=date_op.date(),
                            article=article
                        )
                        activites_to_create.append(activite)
                        lignes_importees += 1

                    except Exception as e:
                        print(f"Erreur à la ligne {idx} : {e}")
                        lignes_ignoreres_erreur += 1
                        continue

                # Sauvegarde en batch
                batch_size = 1000
                for i in range(0, len(activites_to_create), batch_size):
                    Activite.objects.bulk_create(activites_to_create[i:i + batch_size])

            messages.success(
                request,
                f"Importation terminée : {lignes_importees} lignes importées, "
                f"{lignes_ignoreres_manque_info} ignorées (infos manquantes), {lignes_ignoreres_erreur} erreurs."
            )

        except Exception as e:
            messages.error(request, f"Erreur lors de l'importation : {e}")

    return render(request, "Recap/import_excel.html")
# ---------------------
# Dashboard partenaire
# ---------------------
@login_required
def dashboard_view(request):
    utilisateur = request.user
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    activites = Activite.objects.filter(partenaire=utilisateur).exclude(cmouvmt__iexact="PREST").order_by('date_operation')

    if date_debut_str and date_fin_str:
        try:
            date_debut = datetime.strptime(date_debut_str, "%Y-%m-%d").date()
            date_fin = datetime.strptime(date_fin_str, "%Y-%m-%d").date()
            activites = activites.filter(date_operation__range=(date_debut, date_fin))
        except:
            date_debut = date_fin = date.today()
            activites = activites.filter(date_operation=date_debut)
    else:
        date_debut = date_fin = date.today()
        activites = activites.filter(date_operation=date_debut)

    activites_non_paye = activites.exclude(cmouvmt__iexact="PAYECH").exclude(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    total_ttc = activites_non_paye.aggregate(Sum('montant_ttc'))['montant_ttc__sum'] or 0
    total_ht = (Decimal(total_ttc)/Decimal('1.18')).quantize(Decimal('0.01'))
    commission_totale = (total_ht*Decimal('0.04')).quantize(Decimal('0.01'))

    activites_par_jour = {}
    for act in activites_non_paye:
        activites_par_jour.setdefault(act.date_operation, []).append(act)

    periode_titre = f"du {date_debut.strftime('%d/%m/%Y')}" if date_debut==date_fin else f"du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"

    echange_payant_activites = activites.filter(cmouvmt__iexact="PAYECH")
    nb_echange_payant = echange_payant_activites.count()

    creat_terminal = activites.filter(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    for ct in creat_terminal:
        ct.montant_ttc = abs(ct.montant_ttc)
    nb_terminal_1000 = sum(1 for t in creat_terminal if t.montant_ttc==1000)
    nb_terminal_5000 = sum(1 for t in creat_terminal if t.montant_ttc==5000)
    commission_terminal_1000 = nb_terminal_1000*1977
    commission_terminal_5000 = nb_terminal_5000*2260
    total_commission_terminal = commission_terminal_1000 + commission_terminal_5000

    context = {
        'activites_par_jour': dict(sorted(activites_par_jour.items())),
        'total_ttc': total_ttc,
        'total_ht': total_ht,
        'commission_totale': commission_totale,
        'nom': utilisateur.nomdist,
        'numero': utilisateur.numdist,
        'date_debut': date_debut.strftime("%Y-%m-%d"),
        'date_fin': date_fin.strftime("%Y-%m-%d"),
        'periode_titre': periode_titre,
        'nb_echange_payant': nb_echange_payant,
        'echange_payant_activites': echange_payant_activites,
        'nb_terminal_1000': nb_terminal_1000,
        'nb_terminal_5000': nb_terminal_5000,
        'commission_terminal_1000': commission_terminal_1000,
        'commission_terminal_5000': commission_terminal_5000,
        'total_creat_terminal': len(creat_terminal),
        'creat_terminal_list': creat_terminal,
        'total_commission_terminal': total_commission_terminal,
        'total_commission': commission_totale+total_commission_terminal,
    }
    return render(request, 'Recap/dashboard.html', context)

# ---------------------
# PDF récapitulatif
# ---------------------
@login_required
def generate_pdf_view(request, year=None, month=None):
    today = date.today()
    year = year or today.year
    month = month or today.month
    utilisateur = request.user
    debut_mois = date(year, month, 1)
    fin_mois = date(year, month, monthrange(year, month)[1])
    activites = Activite.objects.filter(partenaire=utilisateur, date_operation__range=(debut_mois, fin_mois)).exclude(cmouvmt__iexact="PREST").order_by('date_operation')
    activites_non_paye = activites.exclude(cmouvmt__iexact="PAYECH").exclude(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    total_ht = sum(act.montant_ht for act in activites_non_paye)
    commission_totale = (Decimal(total_ht)*Decimal('0.04')).quantize(Decimal('0.01'))

    echange_payant_activites = activites.filter(cmouvmt__iexact="PAYECH")
    nb_echange_payant = echange_payant_activites.count()

    creat_terminal = activites.filter(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    for ct in creat_terminal:
        ct.montant_ttc = abs(ct.montant_ttc)
    nb_terminal_1000 = sum(1 for t in creat_terminal if t.montant_ttc==1000)
    nb_terminal_5000 = sum(1 for t in creat_terminal if t.montant_ttc==5000)
    commission_terminal_1000 = nb_terminal_1000*1977
    commission_terminal_5000 = nb_terminal_5000*2260
    total_commission_terminal = commission_terminal_1000 + commission_terminal_5000

    context = {
        'partenaire': utilisateur,
        'mois': debut_mois.strftime('%B %Y'),
        'total_ht': total_ht,
        'commission_totale': commission_totale,
        'nb_echange_payant': nb_echange_payant,
        'nb_terminal_1000': nb_terminal_1000,
        'nb_terminal_5000': nb_terminal_5000,
        'commission_terminal_1000': commission_terminal_1000,
        'commission_terminal_5000': commission_terminal_5000,
        'total_creat_terminal': len(creat_terminal),
        'total_commission_terminal': total_commission_terminal,
        'total_commission': commission_totale + total_commission_terminal,
        'date_gen': today,

        # 🔹 Ajout infos entreprise
        'entreprise_nom': "FADCO",
        'entreprise_adresse': "BOULEVARD DES ARMEES",
        'entreprise_ifu': "3201641478415",
        'entreprise_bp': "072 BP 297 / COTONOU",
        'entreprise_tel': "0197485193",
    }

    html = render_to_string('Recap/generate-pdf.html', context)
    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=buffer)
    if pisa_status.err:
        return HttpResponse('Erreur génération PDF', status=500)
    pdf_content = buffer.getvalue()
    buffer.close()

    recap, _ = RecapMensuel.objects.get_or_create(partenaire=utilisateur, mois=debut_mois)
    recap.fichier_pdf.save(f"recap_{utilisateur.numdist}_{month}_{year}.pdf", ContentFile(pdf_content), save=True)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="recap_{year}_{month}.pdf"'
    response.write(pdf_content)
    return response

# ---------------------
# Liste des recaps
# ---------------------
@login_required
def mes_recaps_view(request):
    recaps = RecapMensuel.objects.filter(partenaire=request.user).order_by('-mois')
    return render(request, 'Recap/mes_recaps.html', {'recaps': recaps})

# ---------------------
# Voir un recap
# ---------------------
@login_required
def voir_recap_view(request, recap_id):
    recap = get_object_or_404(RecapMensuel, id=recap_id, partenaire=request.user)
    activites = Activite.objects.filter(partenaire=request.user,
                                        date_operation__year=recap.mois.year,
                                        date_operation__month=recap.mois.month
                                        ).exclude(cmouvmt__iexact="PREST").order_by('date_operation')
    activites_non_paye = activites.exclude(cmouvmt__iexact="PAYECH").exclude(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    total_ht = sum(act.montant_ht for act in activites_non_paye)
    commission_totale = (Decimal(total_ht)*Decimal('0.04')).quantize(Decimal('0.01'))
    nb_echange_payant = activites.filter(cmouvmt__iexact="PAYECH").count()
    creat_terminal = activites.filter(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    nb_terminal_1000 = sum(1 for t in creat_terminal if abs(t.montant_ttc)==1000)
    nb_terminal_5000 = sum(1 for t in creat_terminal if abs(t.montant_ttc)==5000)
    commission_terminal_1000 = nb_terminal_1000*1977
    commission_terminal_5000 = nb_terminal_5000*2260
    total_commission_terminal = commission_terminal_1000 + commission_terminal_5000
    total_commission = commission_totale + total_commission_terminal

    context = {
        'recap': recap,
        'partenaire': recap.partenaire,
        'mois': recap.mois,
        'date_gen': recap.date_genere,
        'total_ht': total_ht,
        'commission_totale': commission_totale,
        'nb_echange_payant': nb_echange_payant,
        'nb_terminal_1000': nb_terminal_1000,
        'nb_terminal_5000': nb_terminal_5000,
        'commission_terminal_1000': commission_terminal_1000,
        'commission_terminal_5000': commission_terminal_5000,
        'total_commission_terminal': total_commission_terminal,
        'total_commission': total_commission,
    }
    return render(request, 'Recap/voir_recap.html', context)

# ---------------------
# Upload facture
# ---------------------
@login_required
def upload_facture_view(request, recap_id):
    recap = get_object_or_404(RecapMensuel, id=recap_id, partenaire=request.user)
    if FacturePartenaire.objects.filter(recap=recap, partenaire=request.user).exists():
        messages.warning(request, "Vous avez déjà envoyé une facture pour ce récapitulatif.")
        return redirect('mes_recaps')

    if request.method == 'POST':
        form = FactureUploadForm(request.POST, request.FILES)
        if form.is_valid():
            facture = form.save(commit=False)
            facture.partenaire = request.user
            facture.recap = recap
            facture.save()
            PaiementCommission.objects.create(recap=recap, facture=facture, statut="en_attente")
            messages.success(request, "Facture envoyée avec succès.")
            return redirect('mes_recaps')
        else:
            messages.error(request, "Corrigez les erreurs ci-dessous.")
    else:
        form = FactureUploadForm()
    return render(request, 'Recap/upload_facture.html', {'form': form, 'recap': recap})

@login_required
def upload_last_facture_view(request):
    dernier_recap = RecapMensuel.objects.filter(partenaire=request.user).order_by('-mois').first()
    if not dernier_recap:
        messages.warning(request, "Aucun récapitulatif disponible.")
        return redirect('mes_recaps')
    return redirect('upload_facture', recap_id=dernier_recap.id)

