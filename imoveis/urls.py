"""Função auxiliar para reutilizar a lógica de filtro."""
from django.urls import path
from django.views.generic import RedirectView
from .views import (
    favoritos_page_view,
    geocode_autocomplete_api,
    imoveis_geojson_view,
    imovel_standalone_detail_view,
    mapa_view,
    lista_imoveis_partial,
    imovel_detail_partial,
    salvar_busca_view,
    toggle_favorito_view
)

urlpatterns = [
    path('', RedirectView.as_view(
        pattern_name='mapa-imoveis', permanent=False), name='home'),
    path('mapa/', mapa_view, name='mapa-imoveis'),
    path('mapa/lista-imoveis/', lista_imoveis_partial,
         name='lista-imoveis-partial'),
    path('imovel-detalhe/<int:pk>/', imovel_detail_partial,
         name='imovel-detail-partial'),
    path('imovel/<int:pk>/toggle-favorito/',
         toggle_favorito_view, name='toggle-favorito'),
    path('favoritos/', favoritos_page_view, name='favoritos-page'),
    path('imovel/<int:pk>/', imovel_standalone_detail_view,
         name='imovel-detail-page'),
    path('salvar-busca/', salvar_busca_view, name='salvar-busca'),
    path('api/geocode-autocomplete/', geocode_autocomplete_api,
         name='geocode-autocomplete-api'),
    path('mapa/geojson/', imoveis_geojson_view, name='imoveis-geojson'),
]
