import django_filters
from .models import Imovel


class BoundingBoxFilter(django_filters.Filter):
    """
    Filtro customizado para o bounding box do mapa.
    Este filtro reduz a área de busca em 10% de cada lado para garantir
    que os resultados estejam bem dentro da área visível do mapa.
    """

    def filter(self, qs, value):
        if value:
            try:
                sw_lat, sw_lng, ne_lat, ne_lng = [
                    float(v.replace(',', '.')) for v in value.split(',')
                ]

                # --- LÓGICA PARA REDUZIR A ÁREA DE BUSCA ---

                # Calcula a altura e a largura da caixa delimitadora original
                height = ne_lat - sw_lat
                width = ne_lng - sw_lng

                # Define uma margem (ex: 10% de cada lado).
                # Você pode ajustar este valor (ex: 0.05 para 5%).
                margin_factor = 0.05
                lat_margin = height * margin_factor
                lng_margin = width * margin_factor

                # Aplica a margem para "encolher" a caixa:
                # Aumenta os mínimos e diminui os máximos.
                new_sw_lat = sw_lat + lat_margin
                new_sw_lng = sw_lng + lng_margin
                new_ne_lat = ne_lat - lat_margin
                new_ne_lng = ne_lng - lng_margin

                # Garante que a caixa não se inverta caso a margem seja muito grande
                # ou a área de busca seja muito pequena.
                if new_sw_lat >= new_ne_lat or new_sw_lng >= new_ne_lng:
                    # Se a caixa se inverter, usa os valores originais para evitar erros
                    return qs.filter(
                        latitude__gte=sw_lat, latitude__lte=ne_lat,
                        longitude__gte=sw_lng, longitude__lte=ne_lng
                    )

                # Usa os novos valores reduzidos para filtrar
                return qs.filter(
                    latitude__gte=new_sw_lat, latitude__lte=new_ne_lat,
                    longitude__gte=new_sw_lng, longitude__lte=new_ne_lng
                )
            except (ValueError, IndexError):
                # Se houver um erro nos valores, retorna o queryset original sem filtro
                return qs
        return qs


class ImovelFilter(django_filters.FilterSet):
    """ Classe principal que define todos os filtros disponíveis. """

    # Filtros por Intervalo (Range)
    min_amount = django_filters.NumberFilter(
        field_name="amount", lookup_expr='gte', label='Preço Mínimo')
    max_amount = django_filters.NumberFilter(
        field_name="amount", lookup_expr='lte', label='Preço Máximo')

    min_area_total = django_filters.NumberFilter(
        field_name="area_total", lookup_expr='gte', label='Área Total Mínima')
    max_area_total = django_filters.NumberFilter(
        field_name="area_total", lookup_expr='lte', label='Área Total Máxima')

    # Filtros por "maior ou igual a"
    quartos = django_filters.NumberFilter(
        field_name="quartos", lookup_expr='gte', label='Quartos (mínimo)')
    garagem = django_filters.NumberFilter(
        field_name="garagem", lookup_expr='gte', label='Vagas de Garagem (mínimo)')

    # Filtro de Bounding Box
    bbox = BoundingBoxFilter()

    class Meta:
        model = Imovel

        fields = {
            'modalidade': ['exact'],
            'tipo_imovel': ['exact'],
        }
