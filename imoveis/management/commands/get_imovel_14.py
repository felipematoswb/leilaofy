import re
import time
import random
import requests
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from django.utils import timezone
from django.core.management.base import BaseCommand
from imoveis.models import Imovel
from retrying import retry
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Suppress only the single InsecureRequestWarning from urllib3 needed for this script
warnings.filterwarnings('ignore', category=InsecureRequestWarning)


def parse_numero(text):
    '''Parse number from text.'''
    if not text:
        return None
    # Clean the text to keep only digits, comma, and period
    cleaned_text = re.sub(r'[^\d,.]', '', text)
    # Handle Brazilian format (e.g., 1.234,56) by removing periods and replacing comma
    if ',' in cleaned_text and '.' in cleaned_text:
        cleaned_text = cleaned_text.replace('.', '')
    cleaned_text = cleaned_text.replace(',', '.')
    match = re.search(r'(\d+\.?\d*)', cleaned_text)
    return float(match.group(1)) if match else None


def parse_data_leilao(text):
    '''Parse date from text, trying multiple formats.'''
    if not text:
        return None
    formats = [
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y - %Hh%M',
    ]
    for fmt in formats:
        try:
            naive_dt = datetime.strptime(text, fmt)
            # Make the datetime timezone-aware
            return timezone.make_aware(naive_dt)
        except ValueError:
            continue
    print(f"Erro ao parsear data: {text}, formatos tentados: {formats}")
    return None


@retry(stop_max_attempt_number=3, wait_exponential_multiplier=1000, wait_exponential_max=10000)
def make_request(session, url, method='post', **kwargs):
    '''Make HTTP request with a retry mechanism.'''
    # Disable SSL verification and pass other arguments
    response = session.request(method, url, verify=False, **kwargs)
    response.raise_for_status()  # Raise an exception for bad status codes
    return response


class Command(BaseCommand):
    '''Script to get imoveis from Caixa.'''
    help = 'Executa o processo completo de scraping (lista e detalhes) dos imóveis da Caixa.'

    def handle(self, *args, **options):
        estados_brasil = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
                          'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO']

        self.stdout.write(self.style.SUCCESS(
            'Iniciando processo unificado de scraping...'))
        base_url = "https://venda-imoveis.caixa.gov.br"
        search_url = f"{base_url}/sistema/carregaPesquisaImoveis.asp"
        detail_url = f"{base_url}/sistema/detalhe-imovel.asp"

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        })

        for estado in estados_brasil:
            self.stdout.write(self.style.SUCCESS(
                f'Iniciando Busca no: {estado.upper()}...'))
            # Note: hdn_tp_venda=14 corresponds to 'Leilão SFI - Edital Único'
            params = {'hdn_estado': estado, 'hdn_cidade': '',
                      'hdn_quartos': '', 'hdn_tp_venda': 14}

            try:
                self.stdout.write('Etapa 1: Buscando lista completa de IDs...')
                response = make_request(
                    session, search_url, data=params, timeout=60)
                soup = BeautifulSoup(response.text, 'html.parser')

                all_ids_raw = []
                imovel_inputs = soup.find_all(
                    'input', id=re.compile(r'^hdnImov\d+'))
                for input_tag in imovel_inputs:
                    if value := input_tag.get('value'):
                        all_ids_raw.extend(value.split('||'))

                all_ids = sorted(list(set(filter(None, all_ids_raw))))
                if not all_ids:
                    self.stdout.write(self.style.WARNING(
                        f'Nenhum ID de imóvel encontrado para o estado {estado}.'))
                    continue
                self.stdout.write(self.style.SUCCESS(
                    f'Etapa 1 concluída. {len(all_ids)} IDs únicos encontrados.'))

                imoveis_criados_total, imoveis_atualizados_total = 0, 0
                chunk_size = 10

                for i in range(0, len(all_ids), chunk_size):
                    chunk = all_ids[i:i + chunk_size]
                    self.stdout.write(self.style.HTTP_INFO(
                        f'\n--- Processando lote {i // chunk_size + 1} ({len(chunk)} imóveis) de {len(all_ids)} ---'
                    ))

                    imoveis_str_chunk = '||'.join(chunk)
                    list_response = make_request(session, f"{base_url}/sistema/carregaListaImoveis.asp",
                                                 data={
                                                     'hdnImov': imoveis_str_chunk},
                                                 headers={'Referer': search_url}, timeout=60)
                    list_soup = BeautifulSoup(
                        list_response.text, 'html.parser')

                    for item in list_soup.find_all('li', class_='group-block-item'):
                        numero_imovel_raw = None
                        try:
                            desc_block_raw = item.find_all(
                                'li', class_='form-row clearfix')[1].get_text(strip=False)
                            numero_imovel_match = re.search(
                                r"Número do imóvel: ([\d-]+)", desc_block_raw, re.I)
                            if not numero_imovel_match:
                                continue
                            numero_imovel_raw = numero_imovel_match.group(1)

                            self.stdout.write(
                                f"Processando imóvel ID: {numero_imovel_raw}")
                            time.sleep(random.uniform(0.5, 1.0))

                            imovel_id_numeric = re.sub(
                                r'\D', '', numero_imovel_raw)
                            detail_response = make_request(session, detail_url, data={
                                                           'hdnImovel': imovel_id_numeric}, timeout=30)
                            detail_soup = BeautifulSoup(
                                detail_response.text, 'html.parser')

                            dados_imovel_div = detail_soup.find(
                                'div', id='dadosImovel')
                            if not dados_imovel_div:
                                self.stdout.write(self.style.WARNING(
                                    f"Div 'dadosImovel' não encontrada para o ID {numero_imovel_raw}."))
                                continue

                            # --- Helper function for safe regex extraction ---
                            def safe_extract(pattern, text):
                                if not text:
                                    return None
                                match = re.search(
                                    pattern, text, re.I | re.DOTALL)
                                return match.group(1).strip() if match else None

                            defaults = {'numero_imovel': numero_imovel_raw}

                            defaults['title'] = dados_imovel_div.find('h5').get_text(
                                strip=True) if dados_imovel_div.find('h5') else 'Título não encontrado'
                            defaults['modalidade'] = 'Leilão SFI - Edital Único'

                            if p_prices := dados_imovel_div.find('p', style="font-size:14pt"):
                                text_prices = p_prices.get_text()
                                defaults['valor_avaliacao'] = parse_numero(safe_extract(
                                    r"Valor de avaliação: R\$ ([\d,.]+)", text_prices))
                                defaults['valor_venda_leilao_1'] = parse_numero(safe_extract(
                                    r"Valor mínimo de venda 1º Leilão: R\$ ([\d,.]+)", text_prices))
                                defaults['valor_venda_leilao_2'] = parse_numero(safe_extract(
                                    r"Valor mínimo de venda 2º Leilão: R\$ ([\d,.]+)", text_prices))
                                defaults['amount'] = defaults.get('valor_venda_leilao_1') or defaults.get('valor_venda_leilao_2') or parse_numero(
                                    item.find_all('li', class_='form-row')[0].get_text(strip=True))

                            if content_div := dados_imovel_div.find('div', class_='content'):
                                content_text = content_div.get_text(
                                    separator=' ')
                                for span in content_div.find_all('span'):
                                    text = span.get_text(strip=True)
                                    key, *value = text.split(':', 1)
                                    value = value[0].strip() if value else ''
                                    strong_value = span.find('strong').get_text(
                                        strip=True) if span.find('strong') else value

                                    if 'Tipo de imóvel' in key:
                                        defaults['tipo_imovel'] = strong_value
                                    elif 'Quartos' in key:
                                        defaults['quartos'] = int(
                                            re.sub(r'\D', '', strong_value)) if strong_value.isdigit() else None
                                    elif 'Garagem' in key:
                                        defaults['garagem'] = int(
                                            re.sub(r'\D', '', strong_value)) if strong_value.isdigit() else None
                                    elif 'Matrícula(s)' in key:
                                        defaults['matricula'] = strong_value
                                    elif 'Comarca' in key:
                                        defaults['comarca'] = strong_value
                                    elif 'Ofício' in key:
                                        defaults['oficio'] = strong_value
                                    elif 'Inscrição imobiliária' in key:
                                        defaults['inscricao_imobiliaria'] = strong_value
                                    elif 'Averbação dos leilões negativos' in key:
                                        defaults['averbacao_leiloes_negativos'] = strong_value.strip(
                                        )

                                defaults['area_total'] = parse_numero(safe_extract(
                                    r'Área total\s*=\s*([\d,.]+)m2', content_text))
                                defaults['area_privativa'] = parse_numero(safe_extract(
                                    r'Área privativa\s*=\s*([\d,.]+)m2', content_text))
                                defaults['area_terreno'] = parse_numero(safe_extract(
                                    r'Área do terreno\s*=\s*([\d,.]+)m2', content_text))

                            # Robust situation extraction (including from HTML comments)
                            situacao_match = re.search(
                                r"Situação:.*?<strong>(.*?)</strong>", detail_response.text.replace('', ''), re.I | re.DOTALL)
                            if situacao_match:
                                defaults['situacao'] = situacao_match.group(
                                    1).strip()

                            if related_box := dados_imovel_div.find('div', class_='related-box'):
                                related_text_lines = related_box.get_text(
                                    separator='\n', strip=True)
                                related_text_full = related_box.get_text(
                                    separator=' ', strip=True)

                                defaults['edital'] = safe_extract(
                                    r"Edital: (.*?)\n", related_text_lines)
                                defaults['numero_item'] = safe_extract(
                                    r"Número do item: (\d+)", related_text_lines)
                                defaults['leiloeiro'] = safe_extract(
                                    r"Leiloeiro\(a\): (.*?)\n", related_text_lines)
                                defaults['data_leilao_1'] = parse_data_leilao(
                                    safe_extract(r"Data do 1º Leilão - (.*?)\n", related_text_lines))
                                defaults['data_leilao_2'] = parse_data_leilao(
                                    safe_extract(r"Data do 2º Leilão - (.*?)\n", related_text_lines))
                                defaults['data_publicacao_edital'] = parse_data_leilao(safe_extract(
                                    r"publicado em: (\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})", related_text_full))

                                defaults['formas_pagamento'] = safe_extract(
                                    r"FORMAS DE PAGAMENTO ACEITAS: (.*?)(?:REGRAS PARA PAGAMENTO|$)", related_text_full)
                                defaults['regras_despesas'] = safe_extract(
                                    r"REGRAS PARA PAGAMENTO DAS DESPESAS.*?:\s(.*?)(?:FORMAS DE PAGAMENTO|$)", related_text_full)

                                if desc_tag := related_box.find('strong', string=re.compile("Descrição:")):
                                    if hasattr(desc_tag.next_sibling, 'next_sibling') and (desc_text := desc_tag.next_sibling.next_sibling.strip()):
                                        defaults['descricao_detalhada'] = desc_text if desc_text != '.' else None

                                if addr_tag := related_box.find('strong', string=re.compile("Endereço:")):
                                    if hasattr(addr_tag.next_sibling, 'next_sibling') and (full_addr := addr_tag.next_sibling.next_sibling.strip()):
                                        defaults['address'] = full_addr
                                        defaults['cep'] = safe_extract(
                                            r"CEP: ([\d-]+)", full_addr)

                            if hdn_imovel := dados_imovel_div.find('input', id='hdnimovel'):
                                defaults['hdn_imovel_id'] = hdn_imovel.get(
                                    'value')

                            if link_matricula_tag := detail_soup.find('a', onclick=re.compile("ExibeDoc.*matricula")):
                                defaults['link_matricula'] = f"{base_url}{safe_extract(r"ExibeDoc\('(.*?)'\)", link_matricula_tag['onclick'])}"

                            if link_edital_tag := detail_soup.find('a', onclick=re.compile("ExibeDoc.*PDF")):
                                defaults['link_edital'] = f"{base_url}{safe_extract(r"ExibeDoc\('(.*?)'\)", link_edital_tag['onclick'])}"

                            if leiloeiro_button := detail_soup.find('button', onclick=re.compile("SiteLeiloeiro")):
                                if domain := safe_extract(r"SiteLeiloeiro\(\"(.*?)\"\)", leiloeiro_button['onclick']):
                                    defaults['site_leiloeiro'] = f"http://{domain}"

                            if galeria := detail_soup.find('div', id='galeria-imagens'):
                                defaults['fotos'] = [f"{base_url}{img.get('src')}" for img in galeria.find_all(
                                    'img') if img.get('src')]

                            defaults['description'] = desc_block_raw.strip().split('\n')[
                                0].strip()
                            if img_tag := item.find('div', class_='fotoimovel-col1').find('img'):
                                defaults['image_url'] = f"{base_url}{img_tag.get('src')}"
                            defaults['source_url'] = f"{detail_url}?hdnImovel={imovel_id_numeric}"

                            # Remove keys with None values before saving
                            final_defaults = {
                                k: v for k, v in defaults.items() if v is not None}
                            slug = Imovel.create_slug(defaults.get('title'), defaults.get(
                                'description'), defaults.get('amount'))

                            obj, created = Imovel.objects.update_or_create(
                                slug=slug, defaults=final_defaults)
                            if created:
                                imoveis_criados_total += 1
                            else:
                                imoveis_atualizados_total += 1

                        except Exception as e:
                            self.stdout.write(self.style.ERROR(
                                f'Erro ao processar o imóvel ID {numero_imovel_raw}: {e}'))

                    self.stdout.write(
                        'Fim do lote. Pausando por 2 segundos...')
                    time.sleep(2)

                self.stdout.write(self.style.SUCCESS(
                    f'\nScraping para {estado} concluído! Criados: {imoveis_criados_total}. Atualizados: {imoveis_atualizados_total}.'
                ))

            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(
                    f'Erro fatal de rede ao processar {estado}: {e}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f'Um erro inesperado ocorreu em {estado}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            '\nProcesso de scraping unificado concluído para todos os estados!'))
