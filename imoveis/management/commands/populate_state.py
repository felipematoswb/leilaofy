# imoveis/management/commands/populate_states.py

import re
from django.core.management.base import BaseCommand
from imoveis.models import Imovel

# Mapeamento de nomes de estado para siglas
STATE_MAP = {
    'ACRE': 'AC', 'ALAGOAS': 'AL', 'AMAPA': 'AP', 'AMAZONAS': 'AM',
    'BAHIA': 'BA', 'CEARA': 'CE', 'DISTRITO FEDERAL': 'DF', 'ESPIRITO SANTO': 'ES',
    'GOIAS': 'GO', 'MARANHAO': 'MA', 'MATO GROSSO': 'MT', 'MATO GROSSO DO SUL': 'MS',
    'MINAS GERAIS': 'MG', 'PARA': 'PA', 'PARAIBA': 'PB', 'PARANA': 'PR',
    'PERNAMBUCO': 'PE', 'PIAUI': 'PI', 'RIO DE JANEIRO': 'RJ', 'RIO GRANDE DO NORTE': 'RN',
    'RIO GRANDE DO SUL': 'RS', 'RONDONIA': 'RO', 'RORAIMA': 'RR', 'SANTA CATARINA': 'SC',
    'SAO PAULO': 'SP', 'SERGIPE': 'SE', 'TOCANTINS': 'TO'
}


class Command(BaseCommand):
    help = 'Populates the estado field for existing properties based on the address field.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(
            'Starting state population process...'))

        # Busca apenas imóveis onde o campo estado ainda não foi preenchido
        imoveis_to_update = Imovel.objects.filter(estado__isnull=True)

        updated_count = 0
        not_found_count = 0

        # Usamos um iterador para não carregar todos os imóveis na memória de uma vez
        for imovel in imoveis_to_update.iterator():
            if not imovel.address:
                continue

            # Tenta extrair a última parte da string após o último '-'
            # Ex: "... - JAPARATUBA - SERGIPE" -> " SERGIPE"
            match = re.search(
                r'-\s*([A-Z\sÁÉÍÓÚÂÊÔÇÃÕ]+)$', imovel.address.upper())

            if match:
                state_name = match.group(1).strip()
                state_abbr = STATE_MAP.get(state_name)

                if state_abbr:
                    imovel.estado = state_abbr
                    imovel.save(update_fields=['estado'])
                    updated_count += 1
                else:
                    self.stdout.write(self.style.WARNING(
                        f'State not mapped for address: "{imovel.address}" (Found: {state_name})'))
                    not_found_count += 1
            else:
                self.stdout.write(self.style.WARNING(
                    f'Could not extract state from address: "{imovel.address}"'))
                not_found_count += 1

        self.stdout.write(self.style.SUCCESS(f'Process finished!'))
        self.stdout.write(self.style.SUCCESS(
            f'{updated_count} properties updated.'))
        if not_found_count > 0:
            self.stdout.write(self.style.ERROR(
                f'{not_found_count} properties could not be updated.'))
