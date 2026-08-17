"""
gerar_icone.py

Converte icone.png para icone.ico com multiplos tamanhos embutidos,
para o Windows escolher a resolucao certa em cada contexto (area de
trabalho, barra de tarefas, propriedades do arquivo, etc.)

Requisitos:
    pip install pillow

Rodar:
    python gerar_icone.py
"""

from PIL import Image

origem = "icone.png"
destino = "icone3.ico"

img = Image.open(origem).convert("RGBA")
print(f"Imagem original: {img.size[0]}x{img.size[1]} pixels")

# Recorta a margem transparente/vazia ao redor do desenho, para o icone
# preencher o quadrado como os demais icones da area de trabalho.
bbox = img.getbbox()
if bbox:
    largura_antes, altura_antes = img.size
    img = img.crop(bbox)
    print(f"Margem removida: {largura_antes}x{altura_antes} -> {img.size[0]}x{img.size[1]}")
else:
    print("AVISO: nao foi possivel detectar bordas para recorte (imagem pode ser totalmente transparente).")

# Adiciona uma margem pequena e uniforme de volta (5% do lado maior),
# para o desenho nao ficar colado na borda do icone.
lado = max(img.size)
margem = int(lado * 0.05)
canvas = Image.new("RGBA", (lado + margem * 2, lado + margem * 2), (0, 0, 0, 0))
pos_x = margem + (lado - img.size[0]) // 2
pos_y = margem + (lado - img.size[1]) // 2
canvas.paste(img, (pos_x, pos_y), img)
img = canvas

if img.size[0] < 256 or img.size[1] < 256:
    print("AVISO: a imagem original é menor que 256x256.")
    print("O ícone final vai ficar borrado nos tamanhos maiores,")
    print("porque não dá para gerar resolução que a fonte não tem.")

img.save(destino, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Ícone gerado: {destino}")
