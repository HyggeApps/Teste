import os
import re
import rhinoinside
from multiprocessing.pool import ThreadPool
import time
import streamlit as st
import tempfile
import pandas as pd
from honeybee.model import Model
from honeybee.aperture import Aperture
from ladybug_vtk.visualization_set import VisualizationSet, LBVisualizationSet
from ladybug_vtk.visualization_set import VisualizationSet as VTKVS
from honeybee.model import Model as HBModel
from honeybee_display.model import model_to_vis_set

st.set_page_config(page_title='HYGGE - Validação da modelagem', layout='wide')
st.cache_data.clear()

image1 = 'https://hygge.eco.br/wp-content/uploads/2023/11/marrom_escolhido.png'

# Especificar a largura da imagem em percentagem
image_width_percent = 50

# Criar código HTML/CSS para redimensionar e centralizar a imagem
html_code1 = f"""
    <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
        <img src="{image1}" alt="Image" style="width: {image_width_percent}%;"/>
    </div>
"""

image2 = 'https://hygge.eco.br/wp-content/uploads/2023/11/RECORTADO-MARROM-SLOGAN.png'

# Especificar a largura da imagem em percentagem
image_width_percent = 80

# Criar código HTML/CSS para redimensionar e centralizar a imagem
html_code2 = f"""
    <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
        <img src="{image2}" alt="Image" style="width: {image_width_percent}%;"/>
    </div>
"""

# Exibir a imagem redimensionada na barra lateral
st.sidebar.markdown(html_code1, unsafe_allow_html=True)
st.sidebar.markdown(html_code2, unsafe_allow_html=True)
st.sidebar.write('---')

uploaded_file  = st.sidebar.file_uploader('Upload do arquivo *.3dm',type='3dm')

st.sidebar.write('---')

# Configurar o caminho do Rhino
os.environ["RHINO_SYSTEM_DIR"] = r"C:\Program Files\Rhino 8\System"
rhinoinside.load()

# Agora, importe os módulos necessários
import Rhino  # type: ignore
from Rhino.Geometry import Brep, Extrusion  # type: ignore
import rhino3dm
import plotly.graph_objects as go
import Libs.grasshopper as funcs_gh
from honeybee.room import Room
from ladybug_rhino.intersect import bounding_box, intersect_solids

tolerance = 0.10
angle_tolerance = 1

# Caminho do arquivo 3DM
#file_path = r"C:\Users\RodrigoLeitzke\OneDrive - Hygge\3 PROJETOS\000 - teste1\3-RHINO\Modelo LYX.3dm"
st.title('Ambiente de testes de modelagem da HYGGE')
st.write('---')
if uploaded_file is not None:
    # Obter o nome do arquivo
    file_name = uploaded_file.name

    # Exibir o nome do arquivo
    st.sidebar.info(f"Arquivo enviado: {file_name}")

    # Ler o conteúdo do arquivo
    file_content = uploaded_file.read()

    # Exibir o tamanho do arquivo
    st.sidebar.info(f"Tamanho do arquivo carregado: {len(file_content) / 1000} Kb")

    # Salvar o arquivo temporariamente
    with tempfile.NamedTemporaryFile(delete=False, suffix=".3dm") as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    # Ler o arquivo 3DM a partir do caminho temporário
    model = Rhino.FileIO.File3dm.Read(temp_file_path)

    # Verificar se o modelo foi carregado com sucesso
    if model is not None:
        st.sidebar.success("Modelo carregado com sucesso!")
    else:
        st.sidebar.write("Falha ao carregar o modelo.")

    # Listas para armazenar layers e geometrias filtradas
    filtered_layers = []
    filtered_geometries = []


    # Dicionário para associar todos os layers às suas geometrias
    all_layers = {layer.Name: [] for layer in model.Layers}

    # Associar geometrias aos respectivos layers
    for obj in model.Objects:
        layer_index = obj.Attributes.LayerIndex
        layer_name = model.Layers[layer_index].Name

        # Adiciona a geometria ao layer correspondente
        all_layers[layer_name].append(obj.Geometry)

    # Analisar os layers
    layers_without_geometry = []
    layers_with_multiple_geometries = []

    for layer, geometries in all_layers.items():
        if len(geometries) == 0:
            layers_without_geometry.append(layer)
        elif len(geometries) > 1:
            layers_with_multiple_geometries.append((layer, len(geometries)))

    windows = []
    windows_layers = []
    doors = []

    # Iterar pelos objetos no modelo
    for obj in model.Objects:
        layer_index = obj.Attributes.LayerIndex
        layer_name = model.Layers[layer_index].Name
        geometry = obj.Geometry

        # Verificar se o nome do layer contém '_UH' ou '_J'
        if '_UH' in layer_name and ('_J' in layer_name or '_XJ' in layer_name or '_YJ' in layer_name or '_UJ' in layer_name or '_ZJ' in layer_name):
            windows.append(geometry)
            windows_layers.append(layer_name)

        # Verificar se o nome do layer contém '_PI' (portas)
        if '_PI' in layer_name:
            doors.append(geometry)
    
    # Iterar sobre os objetos e filtrar pelos critérios do nome do layer
    for obj in model.Objects:
        layer_index = obj.Attributes.LayerIndex
        layer_name = model.Layers[layer_index].Name
        if ('_UH' in layer_name or '_G0' in layer_name or 'GARAGEM' in layer_name or 'ADJ' in layer_name) and not (
            'JP' in layer_name or 'JF' in layer_name or 'JC' in layer_name or 'JO' in layer_name or
            'JS' in layer_name or 'JM' in layer_name or 'JA' in layer_name or 'JG' in layer_name or
            'PI' in layer_name or 'PC' in layer_name or 'AW' in layer_name or 'JI' in layer_name or
            'XJ' in layer_name or 'YJ' in layer_name or 'UJ' in layer_name or 'ZJ' in layer_name
        ):
            if layer_name not in filtered_layers:
                filtered_layers.append(layer_name)
            filtered_geometries.append(obj.Geometry)

    # Converter geometrias para Rhino.Geometry.Brep
    _rooms = []
    for geo in filtered_geometries:
        if isinstance(geo, Extrusion):
            # Converter Extrusion diretamente para Brep
            brep = geo.ToBrep(False)
            if brep:
                _rooms.append(brep)
            else:
                print("Falha ao converter Extrusion para Brep")
        elif isinstance(geo, Brep):
            _rooms.append(geo)
        else:
            print(f"Tipo de geometria não suportada: {type(geo)}")

    if not _rooms:
        raise ValueError("Nenhuma geometria válida foi convertida para Brep.")

    b_boxes = [bounding_box(brep) for brep in _rooms]
    int_rooms = intersect_solids(_rooms, b_boxes)
    
    rooms = funcs_gh.getRooms(_rooms, filtered_layers)
    apertures = funcs_gh.getApertures(windows, windows_layers)
    intdoors = funcs_gh.getDoors(doors)
    subfaces = apertures+intdoors
    rooms_subfaces, unmatcheds = funcs_gh.AddSubface(rooms, subfaces)
    
    if len(unmatcheds) > 0:
        surfaces = []
        for a, w in zip(apertures, windows):
            name_ap = re.sub(r'_[a-f0-9]+$', '', str(a.display_name))
            for u in unmatcheds:
                if name_ap in str(u):
                    surfaces.append(w)
                    break
        for id, d in zip(intdoors, doors):
            name_ap = str(id.display_name)
            for u in unmatcheds:
                if name_ap in str(u):
                    surfaces.append(d)
                    break

    
    st.write('---')
    st.subheader('Conferências de Layers, Geometrias Rhino (Breps) e Zonas Térmicas (Honeybee):')
    st.info('Serão realizados XX testes, envolvendo quantidade de layers/geometrias configurados, adjacências, modelos de simulação (IDF e HBJSON) e o teste do pacote Ladybug Tools sobre a qualidade do modelo elaborado.')
    #st.info('O teste pode ser unitário/individual (clique no botão do teste desejado dentre as opções abaixo) ou completo (clique no botão **"Conferência Geral"** abaixo).')
    st.write('---')
    st.write("\n**1. Teste de layers sem geometria atribuída:**")
    t1, t2, t3, t4, t5, t6 = False, False, False, False, False, False

    semgeo_attr = []
    for layer in layers_without_geometry:
        if ('_UH' in layer or '_G0' in layer or 'GARAGEM' in layer or 'ADJ' in layer):
            semgeo_attr.append(layer)
    
    if semgeo_attr:
        for s in semgeo_attr:
            st.error(f"{s}", icon="🚨")

    if len(semgeo_attr) == 0: 
        st.success('1/5 - Nenhum layer sem geometria atribuída identificado.', icon="✅")
        t1 = True

    st.write("\n**2. Teste de layers com mais de uma geometria:**")
    md1geo_attr = []
    for layer, count in layers_with_multiple_geometries:
        if ('_UH' in layer or '_G0' in layer or 'GARAGEM' in layer or 'ADJ' in layer):
            md1geo_attr.append(layer)

    if md1geo_attr:
        for s in md1geo_attr:
            st.error(f"{s}", icon="🚨")
    
    elif len(md1geo_attr) == 0 and t1: 
        st.success('2/5 - Nenhum layer com mais de uma geometria identficado.', icon="✅")
        t2 = True
    
    else: st.warning('Aguardando a solução do(s) teste(s) anterior(es).')

    st.write("\n**3. Layers de janelas posicionados em ambientes errados:**")

    jan_diffs = funcs_gh.verificar_layers_jan(rooms_subfaces)

    if jan_diffs and t1 and t2:
        for s in jan_diffs:
            st.error(f"{s}", icon="🚨")

    elif len(jan_diffs) == 0 and t1 and t2:
        st.success('3/5 - Nenhum layer de janela posicionado em um room errado.', icon="✅")
        t3 = True
    
    else: st.warning('Aguardando a solução do(s) teste(s) anterior(es).')

    st.write("\n**4. Quantidade de aberturas nos ambientes (duas ou mais):**")
    #st.write(unmatcheds)
    nro_aberturas_ambs = funcs_gh.verificar_layers_ambs(rooms_subfaces)
    
    if nro_aberturas_ambs and t1 and t2 and t3:
        for s in nro_aberturas_ambs:
            st.error(f"{s}", icon="🚨")

    elif len(jan_diffs) == 0 and t1 and t2 and t3:
        st.success('4/5 - Todos os ambientes possuem duas ou mais aberturas.', icon="✅")
        t4 = True
    
    else: st.warning('Aguardando a solução do(s) teste(s) anterior(es).')

    st.write("\n**5. Padrão de nomenclatura dos layers:**")
    
    padroes_layers = []
    for room in rooms_subfaces:
        resultado = funcs_gh.verificar_padrao(str(room).replace('Room: ',''))
        if resultado != 'Padrão correto':
            amb = str(room).replace('Room: ', '')
            padroes_layers.append(f'{resultado} - {amb}')
    
    if padroes_layers and t1 and t2 and t3 and t4:
        for s in padroes_layers:
            st.error(f"{s}", icon="🚨")

    elif len(padroes_layers) == 0 and t1 and t2 and t3 and t4:
        st.success('5/5 - Padrão correto na nomenclatura dos layers.', icon="✅")
        t5 = True
    
    else: st.warning('Aguardando a solução do(s) teste(s) anterior(es).')

    model = Model('Modelo', rooms, tolerance=tolerance, angle_tolerance=tolerance)
    model.display_name = 'Modelo'

    st.write('----')
    if t1 and t2 and t3 and t4 and t5:
        if st.button('Validar o modelo de simulação'):
            report = model.check_all(raise_exception=False)
            st.write(report)
            # check the report and write the summary of errors
            if report == '':
                st.success('Parabéns! Modelo validado.')
            else:
                error_msg = 'Seu modelo foi invalidado pelas seguintes informações:'
                st.write('\n'.join([error_msg, report]))

            st.balloons()

    #----------------------------------------- ELABORAÇÃO DO 3D DE CONFERÊNCIA -------------------------------------------
    
    # Criando o conjunto de visualização
    vs: VisualizationSet = model_to_vis_set(
        model=model,
        include_wireframe=True
    )

    vvs = VTKVS.from_visualization_set(vs)
    vvs.to_html(folder='C:/Users/RodrigoLeitzke/Desktop/TESTES/',name=f'HTML teste')
