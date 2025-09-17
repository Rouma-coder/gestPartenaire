from django.urls import path
from . import views
from .views import upload_last_facture_view, upload_facture_view
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy



urlpatterns = [
      # Page de connexion (racine)
    path('', views.connexion_view, name='login'),

    # Déconnexion → redirige vers la page de connexion
    path( 'logout/',
        auth_views.LogoutView.as_view(next_page=reverse_lazy('login')),
        name='logout'),

    # Tableau de bord
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Import Excel
    # Génération PDF
    path('generate-pdf/<int:year>/<int:month>/', views.generate_pdf_view, name='generate_pdf_with_date'),

    # Voir et uploader des factures
    path('upload-facture/<int:recap_id>/', views.upload_facture_view, name='upload_facture'),
    path('facture/', upload_last_facture_view, name='facture'),

    # Mes récapitulatifs
    path('mes-recaps/', views.mes_recaps_view, name='mes_recaps'),
    path('recap/<int:recap_id>/', views.voir_recap_view, name='voir_recap'),

    # 🔑 Modification du mot de passe
    path("password_change/", 
         auth_views.PasswordChangeView.as_view(template_name="Recap/password_change.html"), 
         name="password_change"),
         
    path("password_change/done/", 
         auth_views.PasswordChangeDoneView.as_view(template_name="Recap/password_change_done.html"), 
         name="password_change_done"),
]
