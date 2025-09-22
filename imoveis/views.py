""" Função auxiliar para reutilizar a lógica de filtro. """
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
import requests

from imoveis.filters import ImovelFilter
from .models import BuscaSalva, Imovel, Favorito


def mapa_view(request):
    """Renderiza a página principal do mapa com o formulário."""
    return render(request, 'imoveis/mapa.html')


def lista_imoveis_partial(request):
    """
    Retorna a lista de imóveis em HTML para a barra lateral,
    incluindo o status de favorito de cada um.
    """
    imovel_filter = ImovelFilter(request.GET, queryset=Imovel.objects.all())
    imoveis_filtrados = imovel_filter.qs[:100]

    # --- EFFICIENT FAVORITE CHECKING ----
    favorited_ids = set()
    # Only run the query if the user is logged in
    if request.user.is_authenticated:
        favorited_ids = set(Favorito.objects.filter(
            usuario=request.user
        ).values_list('imovel_id', flat=True))

    # Add a new attribute to each property object
    for imovel in imoveis_filtrados:
        imovel.is_favorited = imovel.id in favorited_ids
    # --- END OF FAVORITE CHECKING ---

    context = {
        'imoveis': imoveis_filtrados,
    }
    return render(request, 'imoveis/partials/lista_imoveis.html', context)


def imoveis_geojson_view(request):
    """
    Retorna os dados dos imóveis em formato GeoJSON para o mapa.
    Esta é a "API" para o Leaflet.
    """
    # Reutilizamos o mesmo ImovelFilter para garantir que o mapa e a lista fiquem em sincronia
    imovel_filter = ImovelFilter(request.GET, queryset=Imovel.objects.all())

    # Limite de segurança para não enviar dados demais para o mapa
    imoveis_no_mapa = imovel_filter.qs.exclude(
        latitude__isnull=True, longitude__isnull=True)[:500]

    # Monta a estrutura GeoJSON
    features = []
    for imovel in imoveis_no_mapa:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [imovel.longitude, imovel.latitude]
            },
            "properties": {
                "id": imovel.id,
                "title": imovel.title,
                "price": imovel.amount,
                "image_url": imovel.image_url,
                "detail_url": imovel.source_url
            }
        })

    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }

    return JsonResponse(geojson_data)


@login_required
def toggle_favorito_view(request, pk):
    """Adiciona ou remove um imóvel dos favoritos via HTMX."""
    imovel = get_object_or_404(Imovel, pk=pk)
    favorito, created = Favorito.objects.get_or_create(
        usuario=request.user, imovel=imovel)

    if not created:
        favorito.delete()
        is_favorited = False
    else:
        is_favorited = True

    context = {'imovel': imovel, 'is_favorited': is_favorited}
    return render(request, 'imoveis/partials/favorito_icon.html', context)


@login_required  # Garante que apenas usuários logados possam ver esta página
def favoritos_page_view(request):
    """Renderiza a página com a lista de imóveis favoritados pelo usuário."""
    favoritos = Favorito.objects.filter(
        usuario=request.user).select_related('imovel')
    # Pega apenas os objetos Imovel da lista de favoritos
    imoveis_favoritados = [fav.imovel for fav in favoritos]

    context = {
        'imoveis': imoveis_favoritados,
        'page_title': 'Meus Favoritos'
    }
    return render(request, 'imoveis/meus_favoritos.html', context)


def imovel_standalone_detail_view(request, pk):
    """
    Renderiza a página de detalhes completa para um único imóvel.
    """
    imovel = get_object_or_404(Imovel, pk=pk)

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = Favorito.objects.filter(
            usuario=request.user, imovel=imovel).exists()

    context = {
        'imovel': imovel,
        'is_favorited': is_favorited,
    }
    return render(request, 'imoveis/imovel_detail_page.html', context)


def imovel_detail_partial(request, pk):
    """View que retorna o HTML parcial com os detalhes de um único imóvel."""
    imovel = get_object_or_404(Imovel, pk=pk)
    return render(request, 'imoveis/partials/detalhe_imovel.html', {'imovel': imovel})


@login_required
def salvar_busca_view(request):
    ''' salva_busca_view '''
    if request.method == 'POST':
        nome_busca = request.POST.get('nome_da_busca', 'Minha Busca')

        # Coleta todos os parâmetros de filtro da requisição
        filtros = {
            key: value for key, value in request.POST.items()
            if key not in ['csrfmiddlewaretoken', 'nome_da_busca'] and value
        }

        BuscaSalva.objects.create(
            usuario=request.user,
            nome_da_busca=nome_busca,
            filtros=filtros
        )

        # Retorna uma mensagem de sucesso para o HTMX
        return HttpResponse("<span class='text-success'>Alerta criado com sucesso!</span>")
    return HttpResponse("Método não permitido", status=405)


def geocode_autocomplete_api(request):
    """
    Endpoint de API que fornece sugestões de preenchimento automático para locais
    usando o serviço Geoapify.
    """
    query = request.GET.get('text', '')

    if not query or len(query) < 3:
        return JsonResponse([], safe=False)

    try:
        api_key = getattr(settings, 'GEOAPIFY_API_KEY')
        if not api_key:
            return JsonResponse({'error': 'API Key não configurada'}, status=500)

        url = "https://api.geoapify.com/v1/geocode/autocomplete"
        params = {
            'text': query,
            'apiKey': api_key,
            'lang': 'pt',
            'limit': 5,
            'filter': 'countrycode:br'
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        suggestions = []
        if data.get('features'):
            for feature in data['features']:
                properties = feature['properties']
                bbox = feature.get('bbox')

                # <-- MUDANÇA AQUI: Adicionamos os campos que o frontend precisa
                suggestions.append({
                    'text': properties.get('formatted'),
                    'bbox': bbox,
                    'city': properties.get('city'),
                    'state_code': properties.get('state_code')
                })

        return JsonResponse(suggestions, safe=False)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Erro de rede: {e}'}, status=500)
    except Exception as e:
        return JsonResponse({'error': f'Ocorreu um erro inesperado: {e}'}, status=500)
