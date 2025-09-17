from datetime import date
from calendar import monthrange
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from xhtml2pdf import pisa
from io import BytesIO
from decimal import Decimal

from .models import User, Activite, RecapMensuel

def generer_recaps():
    """
    Génère automatiquement les PDF récapitulatifs pour tous les partenaires
    à la fin du mois (appelé par django-crontab).
    """

    today = date.today()
    year, month = today.year, today.month

    # On génère le récap du mois qui vient de se terminer
    if month == 1:
        year -= 1
        month = 12
    else:
        month -= 1

    debut_mois = date(year, month, 1)
    fin_mois = date(year, month, monthrange(year, month)[1])

    partenaires = User.objects.filter(is_partner=True)

    for partenaire in partenaires:
        # Vérifier si le récap existe déjà
        recap, created = RecapMensuel.objects.get_or_create(
            partenaire=partenaire,
            mois=debut_mois
        )

        if not created and recap.fichier_pdf:
            # Déjà généré → on saute
            continue

        # Activités du mois
        activites = Activite.objects.filter(
            partenaire=partenaire,
            date_operation__range=(debut_mois, fin_mois)
        ).exclude(cmouvmt__iexact="PREST").order_by('date_operation')

        activites_non_paye = activites.exclude(
            cmouvmt__iexact="PAYECH"
        ).exclude(
            cmouvmt__iexact="CREAT", article__istartswith="Terminal"
        )

        total_ht = sum(act.montant_ht for act in activites_non_paye)
        commission_totale = (Decimal(total_ht) * Decimal('0.04')).quantize(Decimal('0.01'))

        # Échange Payant
        nb_echange_payant = activites.filter(cmouvmt__iexact="PAYECH").count()

        # CREAT Terminal
        creat_terminal = activites.filter(
            cmouvmt__iexact="CREAT",
            article__istartswith="Terminal"
        )
        for ct in creat_terminal:
            ct.montant_ttc = abs(ct.montant_ttc)

        nb_terminal_1000 = sum(1 for t in creat_terminal if t.montant_ttc == 1000)
        nb_terminal_5000 = sum(1 for t in creat_terminal if t.montant_ttc == 5000)
        commission_terminal_1000 = nb_terminal_1000 * 1977
        commission_terminal_5000 = nb_terminal_5000 * 2260
        total_commission_terminal = commission_terminal_1000 + commission_terminal_5000

        context = {
            'partenaire': partenaire,
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
        }

        # Génération du PDF
        html = render_to_string('Recap/generate-pdf.html', context)
        buffer = BytesIO()
        pisa_status = pisa.CreatePDF(src=html, dest=buffer)

        if not pisa_status.err:
            pdf_content = buffer.getvalue()
            recap.fichier_pdf.save(
                f"recap_{partenaire.numdist}_{month}_{year}.pdf",
                ContentFile(pdf_content),
                save=True
            )

        buffer.close()
