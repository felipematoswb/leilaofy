# imoveis/management/commands/geocode_imoveis.py
import re  # Importa a biblioteca de Expressões Regulares
import time
import requests
from urllib.parse import quote
from django.core.management.base import BaseCommand
from django.conf import settings
from imoveis.models import Imovel


# A função de formatação de endereço continua a mesma, pois é muito útil
def formatar_endereco_para_geocode(imovel):
    """
    Usa Regex para extrair as partes essenciais de um endereço bruto e
    formatá-lo no padrão ideal para geocodificação:
    LOGRADOURO - NÚMERO - CIDADE - ESTADO
    """
    endereco_bruto = imovel.address
    titulo = imovel.title

    if not endereco_bruto or not isinstance(endereco_bruto, str):
        return ""

    # Converte tudo para maiúsculas para padronizar
    s = endereco_bruto.upper()

    logradouro, numero, cidade, estado = None, None, None, None

    # 1. Tenta extrair Cidade e Estado do final da string. É o padrão mais confiável.
    # Ex: ", RIBEIRAO PRETO - SAO PAULO"
    match_cidade_estado = re.search(r',\s*([^,]+?)\s*-\s*([A-Z\s]+)$', s)
    if match_cidade_estado:
        cidade = match_cidade_estado.group(1).strip()
        estado = match_cidade_estado.group(2).strip()
        # Remove a parte da cidade/estado da string principal para facilitar as próximas buscas
        s = s[:match_cidade_estado.start()]

    # 2. Tenta extrair o número, procurando por padrões como "N.", "Nº" ou apenas a vírgula.
    # Ex: ",N. 4875", " Nº 123", ", 50"
    match_numero = re.search(r'(?:,?\s*N[º°\.]?\s*|,\s*)(\d+)', s)
    if match_numero:
        numero = match_numero.group(1).strip()
        # O logradouro é tudo que veio ANTES do padrão do número
        logradouro = s[:match_numero.start()].strip(', ')
    else:
        # Se não achar um padrão claro de número, o logradouro é tudo até a primeira vírgula.
        logradouro = s.split(',')[0].strip()

    # 3. Fallback: Se não encontrou cidade/estado no endereço, tenta pegar do título.
    # Ex: "ITABERABA - LOT JARDIM EUROPA" (onde Itaberaba é a cidade)
    if not cidade and titulo:
        partes_titulo = [p.strip() for p in titulo.upper().split('-')]
        if len(partes_titulo) > 0:
            cidade = partes_titulo[0]
        if len(partes_titulo) > 1:
            # Tenta usar a segunda parte como estado se não foi encontrado antes
            if not estado:
                estado = partes_titulo[1]

    # 4. Monta o endereço final apenas com as partes que foram encontradas.
    partes_finais = [
        logradouro,
        numero,
        cidade,
        estado
    ]

    # Filtra partes vazias e junta com o separador " - "
    endereco_formatado = " - ".join(filter(None, partes_finais))

    return endereco_formatado


class Command(BaseCommand):
    ''' geocode_imoveis.py '''
    help = 'Geocodifica os endereços dos imóveis usando a API da Geoapify.'

    def handle(self, *args, **options):
        # --- ETAPA 1: CONFIGURAR A API GEOAPIFY ---
        try:
            # Recomendo mover esta chave para settings.py como GEOAPIFY_API_KEY
            # Você pode obter sua chave em: https://www.geoapify.com/
            api_key = getattr(settings, 'GEOAPIFY_API_KEY')
            if not api_key:
                self.stderr.write(self.style.ERROR(
                    "A chave da API da Geoapify não foi encontrada. Defina GEOAPIFY_API_KEY em seu settings.py."))
                return
        except AttributeError:
            self.stderr.write(self.style.ERROR(
                "Defina GEOAPIFY_API_KEY em seu arquivo settings.py."))
            return

        # --- ETAPA 2: BUSCAR IMÓVEIS E PROCESSAR ---
        imoveis_para_geocodificar = Imovel.objects.filter(
            latitude__isnull=True)
        total_imoveis = imoveis_para_geocodificar.count()

        if total_imoveis == 0:
            self.stdout.write(self.style.SUCCESS(
                "Nenhum imóvel novo para geocodificar."))
            return

        self.stdout.write(
            f"Encontrados {total_imoveis} imóveis para geocodificar usando a Geoapify...")

        for i, imovel in enumerate(imoveis_para_geocodificar):

            # --- USA A FUNÇÃO DE FORMATAÇÃO ---
            endereco_formatado = formatar_endereco_para_geocode(imovel)

            if not endereco_formatado:
                self.stderr.write(self.style.ERROR(
                    f"({i+1}/{total_imoveis}) Imóvel ID {imovel.id} com dados de endereço insuficientes. Pulando."))
                continue

            self.stdout.write(
                f"({i+1}/{total_imoveis}) Processando endereço formatado: '{endereco_formatado}'")

            # --- ETAPA 3: CHAMAR A API DE GEOCODIFICAÇÃO GEOAPIFY ---
            url = f"https://api.geoapify.com/v1/geocode/search?text={quote(endereco_formatado)}&apiKey={api_key}"
            headers = {"Accept": "application/json"}

            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # A resposta da Geoapify tem os dados dentro de uma lista "features"
                    if data and data.get('features'):
                        # Pega o primeiro e mais relevante resultado
                        result = data['features'][0]
                        imovel.latitude = float(result['properties']['lat'])
                        imovel.longitude = float(result['properties']['lon'])
                        imovel.save()
                        self.stdout.write(self.style.SUCCESS(
                            f"  -> Sucesso! Coordenadas para '{imovel.title}': ({imovel.latitude}, {imovel.longitude})"))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"  -> Endereço não encontrado pelo serviço da Geoapify."))
                else:
                    self.stderr.write(self.style.ERROR(
                        f"  -> Erro na API Geoapify. Status: {response.status_code}. Resposta: {response.text}"))

            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(
                    f"  -> Erro de conexão ao chamar a API: {e}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  -> Ocorreu um erro inesperado: {e}"))

            # Pausa para respeitar os limites de uso da API
            # A Geoapify permite 5 req/seg no plano gratuito. 0.5s é uma pausa segura.
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS("Geocodificação concluída!"))
