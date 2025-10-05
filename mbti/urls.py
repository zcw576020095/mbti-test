from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('test/', views.test_view, name='test'),
    path('save-progress/', views.save_progress_view, name='save_progress'),
    path('submit/', views.submit_view, name='submit'),
    path('result/', views.result_view, name='result'),
    path('result/pdf/', views.result_pdf_view, name='result_pdf'),
]