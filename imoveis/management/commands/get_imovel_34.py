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


def parse_numero(text):
    '''Parse number from text.'''
    if not text:
        return None
    cleaned_text = re.sub(r'[^\d,.]', '', text)
    if ',' in cleaned_text and '.' in cleaned_text:
        cleaned_text = cleaned_text.replace('.', '')
    cleaned_text = cleaned_text.replace(',', '.')
    match = re.search(r'(\d+\.?\d*)', cleaned_text)
    return float(match.group(1)) if match else None


def parse_data_leilao(text):
    '''Parse date from text.'''
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
            return timezone.make_aware(naive_dt)
        except ValueError:
            continue
    print(f"Erro ao parsear data: {text}, formatos tentados: {formats}")
    return None


@retry(stop_max_attempt_number=3, wait_exponential_multiplier=1000, wait_exponential_max=10000)
def make_request(session, url, method='post', **kwargs):
    '''Make HTTP request with retry mechanism.'''
    response = session.request(method, url, **kwargs)
    response.encoding = 'utf-8'
    return response


class Command(BaseCommand):
    '''Script to get imoveis from Caixa (Venda Online).'''
    help = 'Executa o processo completo de scraping (lista e detalhes) dos imóveis da Caixa em Venda Online.'

    def handle(self, *args, **options):
        estados_brasil = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
                          'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO']

        self.stdout.write(self.style.SUCCESS(
            'Iniciando processo unificado de scraping (Venda Online)...'))
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
            params = {'hdn_estado': estado, 'hdn_cidade': '',
                      'hdn_quartos': '', 'hdn_tp_venda': 34}

            try:
                self.stdout.write('Etapa 1: Buscando lista completa de IDs...')
                response = make_request(
                    session, search_url, data=params, verify=False, timeout=60)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                all_ids_raw = []
                imovel_inputs = soup.find_all(
                    'input', id=re.compile(r'^hdnImov\d+'))
                for input_tag in imovel_inputs:
                    if value := input_tag.get('value'):
                        all_ids_raw.extend(value.split('||'))

                all_ids = sorted(list(set(filter(None, all_ids_raw))))
                if not all_ids:
                    self.stderr.write(self.style.ERROR(
                        'Nenhum ID de imóvel encontrado. Abortando.'))
                    continue
                self.stdout.write(self.style.SUCCESS(
                    f'Etapa 1 concluída. {len(all_ids)} IDs únicos encontrados.'))

                imoveis_criados_total, imoveis_atualizados_total = 0, 0
                chunk_size = 10

                for i in range(0, len(all_ids), chunk_size):
                    chunk = all_ids[i:i+chunk_size]
                    self.stdout.write(self.style.HTTP_INFO(
                        f'\n--- Processando lote {i//chunk_size + 1} ({len(chunk)} imóveis) / {len(all_ids)} ---'))

                    imoveis_str_chunk = '||'.join(chunk)
                    list_response = make_request(session, f"{base_url}/sistema/carregaListaImoveis.asp",
                                                 data={
                                                     'hdnImov': imoveis_str_chunk},
                                                 headers={'Referer': search_url}, verify=False, timeout=60)
                    list_soup = BeautifulSoup(
                        list_response.text, 'html.parser')

                    for item in list_soup.find_all('li', class_='group-block-item'):
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

                            defaults = {'numero_imovel': numero_imovel_raw}
                            if dados_imovel_div:
                                defaults['title'] = dados_imovel_div.find('h5').get_text(
                                    strip=True) if dados_imovel_div.find('h5') else 'Título não encontrado'
                                defaults['modalidade'] = 'Venda Direta'

                                p_prices = dados_imovel_div.find(
                                    'p', style="font-size:14pt")
                                if p_prices:
                                    text_prices = p_prices.get_text()
                                    defaults['valor_avaliacao'] = parse_numero(re.search(
                                        r"Valor de avaliação: R\$ ([\d,.]+)", text_prices, re.I).group(1) if re.search(r"Valor de avaliação", text_prices, re.I) else None)
                                    defaults['valor_venda_leilao_1'] = parse_numero(re.search(
                                        r"Valor mínimo de venda 1º Leilão: R\$ ([\d,.]+)", text_prices, re.I).group(1) if re.search(r"1º Leilão", text_prices, re.I) else None)
                                    defaults['valor_venda_leilao_2'] = parse_numero(re.search(
                                        r"Valor mínimo de venda 2º Leilão: R\$ ([\d,.]+)", text_prices, re.I).group(1) if re.search(r"2º Leilão", text_prices, re.I) else None)
                                    defaults['amount'] = defaults['valor_venda_leilao_1'] or defaults['valor_venda_leilao_2'] or parse_numero(re.search(r"Valor mínimo de venda: R\$ ([\d,.]+)", text_prices, re.I).group(
                                        1) if re.search(r"Valor mínimo de venda:", text_prices, re.I) else None) or parse_numero(item.find_all('li', class_='form-row')[0].get_text(strip=True))

                                content_div = dados_imovel_div.find(
                                    'div', class_='content')
                                if content_div:
                                    for span in content_div.find_all('span'):
                                        text = span.get_text(strip=True)
                                        key, *value = text.split(':', 1)
                                        value = value[0].strip(
                                        ) if value else ''
                                        strong_tag = span.find('strong')
                                        strong_value = strong_tag.get_text(
                                            strip=True) if strong_tag else value
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
                                            defaults['averbacao_leiloes_negativos'] = strong_value
                                        elif 'Área total' in text:
                                            defaults['area_total'] = parse_numero(
                                                text)
                                        elif 'Área privativa' in text:
                                            defaults['area_privativa'] = parse_numero(
                                                text)
                                        elif 'Área do terreno' in text:
                                            defaults['area_terreno'] = parse_numero(
                                                text)

                                situacao_span = dados_imovel_div.find(
                                    'span', string=re.compile(r"Situação:", re.I))
                                if situacao_span:
                                    strong_tag = situacao_span.find('strong')
                                    defaults['situacao'] = strong_tag.get_text(
                                        strip=True) if strong_tag else None
                                else:
                                    comments = detail_soup.find_all(
                                        string=lambda text: isinstance(text, Comment))
                                    for comment in comments:
                                        if 'Situação:' in comment:
                                            situacao_match = re.search(
                                                r"<strong>(.*?)</strong>", comment, re.I)
                                            if situacao_match:
                                                defaults['situacao'] = situacao_match.group(
                                                    1).strip()
                                                break

                                related_box = dados_imovel_div.find(
                                    'div', class_='related-box')
                                if related_box:
                                    related_text = related_box.get_text(
                                        separator='\n', strip=True)

                                    related_text_full = related_box.get_text(
                                        separator=' ', strip=True)
                                    formas_pagamento_match = re.search(
                                        r"FORMAS DE PAGAMENTO.*?((?:Recursos próprios|Exclusivamente à vista).*?)(?:REGRAS PARA PAGAMENTO DAS DESPESAS|$)", related_text_full, re.I | re.DOTALL)
                                    regras_despesas_match = re.search(
                                        r"REGRAS PARA PAGAMENTO DAS DESPESAS.*?((?:Condomínio|Tributos).*?)(?:\s*$|\s*FORMAS DE PAGAMENTO)", related_text_full, re.I | re.DOTALL)

                                    if formas_pagamento_match:
                                        defaults['formas_pagamento'] = formas_pagamento_match.group(
                                            1).strip()

                                    if regras_despesas_match:
                                        defaults['regras_despesas'] = regras_despesas_match.group(
                                            1).strip()

                                    desc_tag = related_box.find(
                                        'strong', string=re.compile("Descrição:"))
                                    if desc_tag and hasattr(desc_tag.next_sibling, 'next_sibling'):
                                        defaults['descricao_detalhada'] = desc_tag.next_sibling.next_sibling.strip(
                                        )

                                    addr_tag = related_box.find(
                                        'strong', string=re.compile("Endereço:"))
                                    if addr_tag and hasattr(addr_tag.next_sibling, 'next_sibling'):
                                        full_addr = addr_tag.next_sibling.next_sibling.strip()
                                        defaults['address'] = full_addr
                                        defaults['cep'] = re.search(
                                            r"CEP: ([\d-]+)", full_addr).group(1) if re.search(r"CEP:", full_addr) else None

                                hdn_imovel = dados_imovel_div.find(
                                    'input', id='hdnimovel')
                                if hdn_imovel:
                                    defaults['hdn_imovel_id'] = hdn_imovel.get(
                                        'value')

                                link_matricula_tag = detail_soup.find(
                                    'a', onclick=re.compile("ExibeDoc.*matricula"))
                                if link_matricula_tag:
                                    path = re.search(
                                        r"ExibeDoc\('(.*?)'\)", link_matricula_tag['onclick']).group(1)
                                    defaults['link_matricula'] = f"{base_url}{path}"

                                link_venda_online = detail_soup.find(
                                    'a', href=re.compile("regrasVendaOnline"))
                                if link_venda_online:
                                    defaults['link_venda_online'] = link_venda_online.get(
                                        'href')

                                link_formas_pagamento = detail_soup.find(
                                    'a', href=re.compile("formasPagamento"))
                                if link_formas_pagamento:
                                    defaults['link_formas_pagamento'] = link_formas_pagamento.get(
                                        'href')

                                if galeria := detail_soup.find('div', id='galeria-imagens'):
                                    defaults['fotos'] = [f"{base_url}{img.get('src')}" for img in galeria.find_all(
                                        'img') if img.get('src')]

                                defaults['description'] = desc_block_raw.strip().split('\n')[
                                    0].strip()
                                if img_tag := item.find('div', class_='fotoimovel-col1').find('img'):
                                    defaults['image_url'] = f"{base_url}{img_tag.get('src')}"
                                defaults['source_url'] = f"{detail_url}?hdnImovel={imovel_id_numeric}"

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
                    f'\nScraping unificado concluído! Criados: {imoveis_criados_total}. Atualizados: {imoveis_atualizados_total}.'))

            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(f'Erro fatal de rede: {e}'))
