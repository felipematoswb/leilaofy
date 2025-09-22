''' Imovel model '''
import hashlib
import random
from django.db import models
from django.conf import settings


class Imovel(models.Model):
    numero_imovel = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    modalidade = models.CharField(max_length=100, null=True)
    valor_avaliacao = models.FloatField(null=True)
    valor_venda_leilao_1 = models.FloatField(null=True)
    valor_venda_leilao_2 = models.FloatField(null=True)
    amount = models.FloatField(null=True)
    tipo_imovel = models.CharField(max_length=100, null=True)
    quartos = models.IntegerField(null=True)
    garagem = models.IntegerField(null=True)
    matricula = models.CharField(max_length=100, null=True)
    comarca = models.CharField(max_length=100, null=True)
    oficio = models.CharField(max_length=50, null=True)
    inscricao_imobiliaria = models.CharField(max_length=100, null=True)
    averbacao_leiloes_negativos = models.CharField(max_length=100, null=True)
    area_total = models.FloatField(null=True)
    area_privativa = models.FloatField(null=True)
    area_terreno = models.FloatField(null=True)
    situacao = models.CharField(max_length=100, null=True)
    edital = models.CharField(max_length=255, null=True)
    numero_item = models.CharField(max_length=50, null=True)
    leiloeiro = models.CharField(max_length=255, null=True)
    data_leilao_1 = models.DateTimeField(null=True)
    data_leilao_2 = models.DateTimeField(null=True)
    descricao_detalhada = models.TextField(null=True)
    address = models.TextField(null=True)
    estado = models.CharField(max_length=2, null=True,
                              blank=True, db_index=True)
    cep = models.CharField(max_length=20, null=True)
    link_venda_online = models.URLField(null=True)  # Novo campo
    link_formas_pagamento = models.URLField(null=True)
    link_matricula = models.URLField(null=True)
    link_edital = models.URLField(null=True)
    site_leiloeiro = models.URLField(null=True)
    fotos = models.JSONField(null=True)
    description = models.TextField(null=True)
    image_url = models.URLField(null=True)
    source_url = models.URLField(null=True)
    hdn_imovel_id = models.CharField(max_length=50, null=True)
    formas_pagamento = models.TextField(null=True)
    regras_despesas = models.TextField(null=True)
    data_publicacao_edital = models.DateTimeField(null=True)
    slug = models.SlugField(max_length=255, unique=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    @staticmethod
    def create_slug(title, description, amount):
        slug_base = f"{title}-{description}-{amount}" if title and description and amount else f"imovel-{random.randint(1, 10000)}"
        return hashlib.md5(slug_base.encode()).hexdigest()[:255]

    def get_city(self):
        '''get city from address'''
        # SP = SAO PAULO
        return self.address.split('-')[1] if self.address else None

    class Meta:
        verbose_name = "Imóvel"
        verbose_name_plural = "Imóveis"


class Favorito(models.Model):
    ''' Favorito model '''
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    imovel = models.ForeignKey(
        Imovel, on_delete=models.CASCADE, related_name='favoritos')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('usuario', 'imovel')

    def __str__(self):
        return f"{self.usuario.username} favoritou {self.imovel.title}"


class BuscaSalva(models.Model):
    ''' BuscaSalva model '''
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nome_da_busca = models.CharField(
        max_length=100, help_text="Ex: Apartamentos na Vila Mariana")
    # Usamos JSONField para guardar um dicionário flexível com todos os filtros
    filtros = models.JSONField()
    criada_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Busca '{self.nome_da_busca}' de {self.usuario.username}"
