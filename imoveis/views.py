""" Função auxiliar para reutilizar a lógica de filtro. """
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
import requests

from imoveis.filters import ImovelFilter
from .models import BuscaSalva, Imovel, Favorito


def mapa_view(request):
    """Renderiza a página principal do mapa."""
    # A view agora só precisa passar os filtros para o template, se houver
    context = {
        'filter_form_data': request.GET
    }
    return render(request, 'imoveis/mapa.html', context)


def lista_imoveis_partial(request):
    """View que retorna APENAS o HTML da lista de imóveis para o HTMX."""
    imovel_filter = ImovelFilter(
        request.GET, queryset=Imovel.objects.filter(
            latitude__isnull=False, longitude__isnull=False)
    )

    favorited_ids = set()
    if request.user.is_authenticated:
        favorited_ids = set(Favorito.objects.filter(
            usuario=request.user).values_list('imovel_id', flat=True))

    imoveis_filtrados = imovel_filter.qs
    for imovel in imoveis_filtrados:
        imovel.is_favorited = imovel.id in favorited_ids

    context = {
        'imoveis': imoveis_filtrados,
    }
    return render(request, 'imoveis/partials/lista_imoveis.html', context)


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

    # Não busca se o texto for muito curto
    if not query or len(query) < 3:
        return JsonResponse([], safe=False)

    try:
        api_key = getattr(settings, 'GEOAPIFY_API_KEY')
        if not api_key:
            return JsonResponse({'error': 'API Key não configurada'}, status=500)

        # Endpoint da API de Autocomplete da Geoapify
        url = "https://api.geoapify.com/v1/geocode/autocomplete"

        params = {
            'text': query,
            'apiKey': api_key,
            'lang': 'pt',
            'limit': 5,
            'filter': 'countrycode:br'
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()  # Lança um erro para status HTTP ruins

        data = response.json()

        # Formata os dados para uma estrutura mais simples para o frontend
        suggestions = []
        if data.get('features'):
            for feature in data['features']:
                properties = feature['properties']
                # A 'bbox' (bounding box) é crucial para centralizar o mapa
                bbox = feature.get('bbox')

                suggestions.append({
                    'text': properties.get('formatted'),
                    'bbox': bbox
                })

        return JsonResponse(suggestions, safe=False)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Erro de rede: {e}'}, status=500)
    except Exception as e:
        return JsonResponse({'error': f'Ocorreu um erro inesperado: {e}'}, status=500)
