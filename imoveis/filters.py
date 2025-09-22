# imoveis/filters.py
import django_filters
from .models import Imovel

# Filtro customizado para Bounding Box


class BoundingBoxFilter(django_filters.Filter):
    def filter(self, qs, value):
        if value:
            # Espera um valor como "min_lon,min_lat,max_lon,max_lat"
            try:
                min_lon, min_lat, max_lon, max_lat = [
                    float(v) for v in value.split(',')]
                # Aplica o filtro usando os índices do banco de dados
                return qs.filter(
                    longitude__gte=min_lon,
                    longitude__lte=max_lon,
                    latitude__gte=min_lat,
                    latitude__lte=max_lat,
                )
            except (ValueError, IndexError):
                # Ignora o filtro se o valor do bbox for inválido
                return qs
        return qs


class ImovelFilter(django_filters.FilterSet):
    # Filtros para os campos do formulário
    min_amount = django_filters.NumberFilter(
        field_name="amount", lookup_expr='gte')
    max_amount = django_filters.NumberFilter(
        field_name="amount", lookup_expr='lte')
    min_area_total = django_filters.NumberFilter(
        field_name="area_total", lookup_expr='gte')
    max_area_total = django_filters.NumberFilter(
        field_name="area_total", lookup_expr='lte')
    quartos = django_filters.NumberFilter(
        field_name="quartos", lookup_expr='gte')
    garagem = django_filters.NumberFilter(
        field_name="garagem", lookup_expr='gte')

    comarca = django_filters.CharFilter(
        field_name='comarca', lookup_expr='iexact')

    # Filtro especial para o mapa
    bbox = BoundingBoxFilter()

    class Meta:
        model = Imovel
        fields = ['tipo_imovel', 'modalidade', 'min_amount', 'max_amount',
                  'min_area_total', 'max_area_total', 'quartos', 'garagem', 'bbox', 'comarca']
