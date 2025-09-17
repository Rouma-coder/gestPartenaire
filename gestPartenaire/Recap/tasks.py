# 📌 Recap/tasks.py
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events, register_job
from django.conf import settings
from datetime import date
from calendar import monthrange
from io import BytesIO
from xhtml2pdf import pisa
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from decimal import Decimal

from .models import User, Activite, RecapMensuel


def generate_monthly_recap(partenaire, year, month):
    """ Génère le PDF récapitulatif pour un partenaire donné et un mois précis """

    debut_mois = date(year, month, 1)
    fin_mois = date(year, month, monthrange(year, month)[1])

    # ✅ Récupérer activités du mois
    activites = Activite.objects.filter(
        partenaire=partenaire,
        date_operation__range=(debut_mois, fin_mois)
    ).exclude(cmouvmt__iexact="PREST").order_by("date_operation")

    # ✅ Activités prises en compte pour HT & commission
    activites_non_paye = activites.exclude(cmouvmt__iexact="PAYECH").exclude(
        cmouvmt__iexact="CREAT", article__istartswith="Terminal"
    )

    total_ht = sum(act.montant_ht for act in activites_non_paye)
    commission_totale = (Decimal(total_ht) * Decimal("0.04")).quantize(Decimal("0.01"))

    # ✅ Echange payant
    nb_echange_payant = activites.filter(cmouvmt__iexact="PAYECH").count()

    # ✅ CREAT Terminal
    creat_terminal = activites.filter(cmouvmt__iexact="CREAT", article__istartswith="Terminal")
    for ct in creat_terminal:
        ct.montant_ttc = abs(ct.montant_ttc)

    nb_terminal_1000 = sum(1 for t in creat_terminal if t.montant_ttc == 1000)
    nb_terminal_5000 = sum(1 for t in creat_terminal if t.montant_ttc == 5000)
    commission_terminal_1000 = nb_terminal_1000 * 1977
    commission_terminal_5000 = nb_terminal_5000 * 2260
    total_commission_terminal = commission_terminal_1000 + commission_terminal_5000

    # ✅ Contexte pour le template
    context = {
        "partenaire": partenaire,
        "mois": debut_mois.strftime("%B %Y"),
        "total_ht": total_ht,
        "commission_totale": commission_totale,
        "nb_echange_payant": nb_echange_payant,
        "nb_terminal_1000": nb_terminal_1000,
        "nb_terminal_5000": nb_terminal_5000,
        "commission_terminal_1000": commission_terminal_1000,
        "commission_terminal_5000": commission_terminal_5000,
        "total_creat_terminal": len(creat_terminal),
        "total_commission_terminal": total_commission_terminal,
        "total_commission": commission_totale + total_commission_terminal,
        "date_gen": date.today(),
    }

    # ✅ Génération du PDF
    html = render_to_string("Recap/generate-pdf.html", context)
    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=buffer)

    if pisa_status.err:
        print(f"❌ Erreur génération PDF pour {partenaire.nomdist}")
        return None

    pdf_content = buffer.getvalue()
    buffer.close()

    # ✅ Sauvegarde dans RecapMensuel
    recap, _ = RecapMensuel.objects.get_or_create(partenaire=partenaire, mois=debut_mois)
    recap.fichier_pdf.save(
        f"recap_{partenaire.numdist}_{month}_{year}.pdf",
        ContentFile(pdf_content),
        save=True,
    )

    print(f"✅ PDF généré pour {partenaire.nomdist} ({month}/{year})")
    return recap


def monthly_generate_pdfs():
    """ Génère automatiquement les PDF du mois précédent pour tous les partenaires """

    today = date.today()
    # ➡️ Récupérer le mois précédent
    if today.month == 1:
        year = today.year - 1
        month = 12
    else:
        year = today.year
        month = today.month - 1

    print(f"📌 Génération des récapitulatifs pour {month}/{year}")

    partenaires = User.objects.filter(is_partner=True)
    for partenaire in partenaires:
        generate_monthly_recap(partenaire, year, month)


# 🚀 Scheduler APScheduler
scheduler = BackgroundScheduler()
scheduler.add_jobstore(DjangoJobStore(), "default")


# 📅 Tâche planifiée → le 1er de chaque mois à 00h10
@register_job(scheduler, "cron", day=1, hour=0, minute=10, replace_existing=True)
def scheduled_generate_pdfs():
    monthly_generate_pdfs()


def start():
    """ Démarre le scheduler """
    if settings.DEBUG:  # On évite de lancer plusieurs fois en dev
        try:
            scheduler.start()
            register_events(scheduler)
            print("✅ Scheduler lancé avec succès")
        except Exception as e:
            print("❌ Erreur lancement scheduler :", e)

