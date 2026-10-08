# -*- coding: utf-8 -*-
"""
Plateforme web – Susceptibilité aux inondations, commune d'Abomey-Calavi
Streamlit + Folium. Données dans le dossier data/ (produit par
OS3_preparation_couches_web.py).
"""
import base64
import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Inondations – Abomey-Calavi", page_icon="🌊", layout="wide")
ICI = Path(__file__).parent
# fichiers de données dans data/ ou directement à côté de app.py
DATA = ICI / "data" if (ICI / "data" / "meta.json").exists() else ICI

PALETTES = {
    "susc": {1: ("Très faible", "#1a9641"), 2: ("Faible", "#a6d96a"), 3: ("Modérée", "#ffffbf"),
             4: ("Forte", "#fdae61"), 5: ("Très forte", "#d7191c")},
    "lulc": {1: ("Bâti", "#e31a1c"), 2: ("Sols nus", "#fdbf6f"), 3: ("Végétation", "#33a02c"),
             4: ("Zones humides", "#a6cee3"), 5: ("Eau libre", "#1f78b4")},
}


def lire_json(nom):
    return json.loads((DATA / nom).read_text(encoding="utf-8"))


def image_png(nom):
    return "data:image/png;base64," + base64.b64encode((DATA / f"{nom}.png").read_bytes()).decode()


def lire_stats():
    f = DATA / "stats_arrondissements.csv"
    return pd.read_csv(f) if f.exists() else None


meta = lire_json("meta.json")
stats = lire_stats()
arr_dispo = (DATA / "arrondissements.geojson").exists()
arr_geo = lire_json("arrondissements.geojson") if arr_dispo else None

def point_etiquette(f):
    """[lat, lon] où écrire le nom : point fourni par meta.json, sinon centre de
    gravité du plus grand contour du polygone."""
    nom = f["properties"]["nom"]
    if nom in meta.get("arr_label", {}):
        return meta["arr_label"][nom]
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    meilleur, aire_max = None, -1
    for poly in polys:
        x = [p[0] for p in poly[0]]; y = [p[1] for p in poly[0]]
        a = cx = cy = 0.0
        for i in range(len(x) - 1):
            t = x[i] * y[i + 1] - x[i + 1] * y[i]
            a += t; cx += (x[i] + x[i + 1]) * t; cy += (y[i] + y[i + 1]) * t
        if abs(a) > aire_max and a != 0:
            aire_max, meilleur = abs(a), [cy / (3 * a), cx / (3 * a)]
    return meilleur


def emprise_arrondissement(nom):
    """[[lat_min, lon_min], [lat_max, lon_max]] de l'arrondissement."""
    if nom in meta.get("arr_bbox", {}):
        return meta["arr_bbox"][nom]
    f = next((f for f in arr_geo["features"] if f["properties"]["nom"] == nom), None)
    if f is None:
        return None
    pts = []

    def parcourir(c):
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                parcourir(x)

    parcourir(f["geometry"]["coordinates"])
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


# Superficies de susceptibilité validées par l'encadreur (commune entière, ha).
# Les pourcentages sont recalculés à partir des superficies.
SUSC_COMMUNE = {
    "susceptibilite_2025": [32460, 5342, 4533, 3465, 3851],
    "susceptibilite_2040": [32593, 5235, 4530, 3453, 3840],
}


# ---------------- Barre latérale ----------------
st.sidebar.title("Paramètres")
theme = st.sidebar.radio("Carte", ["Susceptibilité aux inondations", "Occupation du sol"])
annee = st.sidebar.radio("Année", ["2025", "2040"], horizontal=True)
opacite = st.sidebar.slider("Opacité", 0.2, 1.0, 1.0, 0.1)
fond = st.sidebar.selectbox("Fond de carte", ["Clair (sans détails)", "OpenStreetMap", "Satellite"])
noms_arr = sorted(f["properties"]["nom"] for f in arr_geo["features"]) if arr_dispo else []
choix_arr = st.sidebar.selectbox("Arrondissement", ["Toute la commune"] + noms_arr)

couche = ("susceptibilite_" if theme.startswith("Susc") else "occupation_") + annee
typ = meta["couches"][couche]["type"]
pal = PALETTES[typ]

st.sidebar.markdown("**Légende**")
for k, (nom, coul) in pal.items():
    st.sidebar.markdown(
        f"<span style='display:inline-block;width:14px;height:14px;background:{coul};"
        f"border:1px solid #555;margin-right:6px'></span>{nom}", unsafe_allow_html=True)
if meta.get("gris_affiche") and meta.get("non_modelise_ha", 0) > 0:
    st.sidebar.markdown(
        "<span style='display:inline-block;width:14px;height:14px;background:#bdbdbd;"
        "border:1px solid #555;margin-right:6px'></span>Sans données (non modélisé)",
        unsafe_allow_html=True)
if annee == "2040":
    st.sidebar.caption("2040 : scénario tendanciel (projection de l'occupation du sol), "
                       "pas une observation.")

# ---------------- En-tête ----------------
st.title("Susceptibilité aux inondations – commune d'Abomey-Calavi")
onglet_carte, onglet_prev, onglet_info = st.tabs(["Carte", "Prévention", "À propos"])

with onglet_carte:
    c_carte, c_info = st.columns([3, 1.3])

    with c_carte:
      try:
        m = folium.Map(tiles=None, control_scale=True)
        if fond == "OpenStreetMap":
            folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
        elif fond == "Satellite":
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri, Maxar, Earthstar Geographics", name="Satellite").add_to(m)
        else:
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                attr="Esri, HERE, Garmin, OpenStreetMap contributors", name="Clair").add_to(m)
        # pixels nets : pas de mélange de couleurs quand l'image est réduite à l'écran
        m.get_root().header.add_child(folium.Element(
            "<style>.leaflet-image-layer{image-rendering:pixelated;"
            "image-rendering:crisp-edges;}</style>"))
        folium.raster_layers.ImageOverlay(
            image=image_png(couche), bounds=meta["couches"][couche]["png_bounds"],
            opacity=opacite, name=f"{theme} {annee}", interactive=False, zindex=1,
        ).add_to(m)

        bbox = meta["bbox"]
        if arr_dispo:
            folium.GeoJson(
                arr_geo, name="Arrondissements",
                style_function=lambda f: {
                    "fill": False, "color": "#000000",
                    "weight": 3 if f["properties"]["nom"] == choix_arr else 1,
                    "dashArray": None if f["properties"]["nom"] == choix_arr else "4 4"},
                tooltip=folium.GeoJsonTooltip(fields=["nom"], aliases=["Arrondissement :"]),
            ).add_to(m)
            for f in arr_geo["features"]:
                pt = point_etiquette(f)
                if pt:
                    folium.Marker(pt, icon=folium.DivIcon(
                        icon_size=(160, 20), icon_anchor=(80, 10),
                        html=("<div style='text-align:center;font:600 13px Arial,sans-serif;"
                              "color:#111;white-space:nowrap;text-shadow:"
                              "-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff,"
                              "0 0 3px #fff'>" + f["properties"]["nom"] + "</div>"))).add_to(m)
            if choix_arr != "Toute la commune":
                bbox = emprise_arrondissement(choix_arr) or bbox
        m.fit_bounds(bbox)
        folium.LayerControl(collapsed=True).add_to(m)
        st_folium(m, height=620, use_container_width=True, returned_objects=[],
                  key=f"{couche}_{choix_arr}_{opacite}_{fond}")
      except Exception as err:
        st.error("Erreur d'affichage de la carte")
        st.exception(err)

    with c_info:
      try:
        st.subheader(choix_arr)
        if choix_arr == "Toute la commune" or stats is None:
            if couche in SUSC_COMMUNE:
                ha = SUSC_COMMUNE[couche]
                tab = pd.DataFrame({"Classe": [pal[k][0] for k in range(1, 6)],
                                    "Superficie (ha)": ha,
                                    "%": [round(100 * x / sum(ha), 2) for x in ha]})
            else:
                sup = meta["couches"][couche]["superficie_ha"]
                ha = [round(v) for v in sup.values()]
                tab = pd.DataFrame({"Classe": [pal[int(k)][0] for k in sup],
                                    "Superficie (ha)": ha,
                                    "%": [round(100 * x / sum(ha), 2) for x in ha]})
            expo = {a: meta[f"exposition_{a}"] for a in ("2025", "2040")}
        else:
            s = stats[(stats.arrondissement == choix_arr) & (stats.couche == couche)]
            tab = s[["nom", "superficie_ha", "pourcentage"]].rename(
                columns={"nom": "Classe", "superficie_ha": "Superficie (ha)", "pourcentage": "%"})
            tab["Classe"] = tab["Classe"].replace({"Moyenne": "Modérée"})
            e = stats[stats.arrondissement == choix_arr].set_index("couche")
            expo = {a: {"ha": e.loc[f"exposition_{a}", "superficie_ha"],
                        "pct": e.loc[f"exposition_{a}", "pourcentage"]} for a in ("2025", "2040")}
        st.dataframe(tab, hide_index=True)

        st.markdown("**Bâti en zones de susceptibilité forte ou très forte**")
        c1, c2 = st.columns(2)
        c1.metric("2025", f"{expo['2025']['ha']:,.0f} ha".replace(",", " "),
                  help=f"{expo['2025']['pct']} % de ces zones")
        c2.metric("2040", f"{expo['2040']['ha']:,.0f} ha".replace(",", " "),
                  delta=f"{expo['2040']['ha'] - expo['2025']['ha']:+,.0f} ha".replace(",", " "),
                  delta_color="inverse", help=f"{expo['2040']['pct']} % de ces zones")

        st.markdown("**Télécharger la couche affichée**")
        f_geo, f_shp = DATA / f"{couche}.geojson", DATA / f"{couche}_shp.zip"
        if f_geo.exists():
            st.download_button("GeoJSON (WGS 84)", f_geo.read_bytes(),
                               file_name=f_geo.name, mime="application/geo+json")
        if f_shp.exists():
            st.download_button("Shapefile (UTM 31N, zip)", f_shp.read_bytes(),
                               file_name=f_shp.name, mime="application/zip")
      except Exception as err:
        st.error("Erreur d'affichage du tableau")
        st.exception(err)

with onglet_prev:
    st.subheader("Que faire face au risque d'inondation ?")
    # [À COMPLÉTER ET À SOURCER : consignes officielles (ANPC, mairie d'Abomey-Calavi),
    #  numéros d'urgence vérifiés]
    st.markdown("""
**Avant la saison des pluies**
- Vérifier le niveau de susceptibilité de son quartier sur la carte.
- Ne pas obstruer les caniveaux ni les exutoires naturels (déchets, remblais).
- Surélever les biens de valeur et les documents importants.

**Pendant une inondation**
- Ne pas traverser une rue ou un bas-fond inondé, à pied ou en véhicule.
- Couper l'électricité si l'eau entre dans le logement.
- Suivre les consignes des autorités locales.

**Avant d'acheter une parcelle ou de construire**
- Éviter les zones classées « forte » ou « très forte ».
- Se renseigner auprès des services techniques de la mairie.
""")

with onglet_info:
    st.subheader("Méthode")
    st.markdown("""
- **Susceptibilité** : modèle Random Forest entraîné sur 400 points (200 inondés, 200 non
  inondés) et 13 facteurs (topographie, hydrologie, végétation, occupation du sol, sols,
  pluviométrie). AUC sur le jeu de test : 0,979. Cinq classes par la méthode de Jenks.
- **2040** : même modèle appliqué à l'occupation du sol projetée par le Land Change Modeler
  (TerrSet). Les autres facteurs restent ceux de 2025.
- **Occupation du sol** : classification Random Forest d'images Sentinel-2 (2025) et
  projection 2040.
- La partie nord de la commune, située hors de l'emprise des variables du modèle,
  n'a pas été prédite : elle est complétée à l'affichage par la classe du pixel
  prédit le plus proche et n'entre pas dans les superficies.
- Cartes affichées après un filtre majoritaire (statistique focale, fenêtre de 5 × 5
  pixels, soit 50 m) qui supprime les pixels isolés. Les fichiers téléchargeables sont
  en plus vectorisés et simplifiés (taches < 2 ha supprimées). Les superficies et
  pourcentages sont calculés sur les rasters à 10 m non filtrés.

**Limites** : la susceptibilité traduit une prédisposition physique, pas une prévision
d'événement. La carte 2040 est un scénario tendanciel. Échelle d'usage : communale ;
ne pas l'utiliser à la parcelle.

*Mémoire de Master en Génie Géomatique – ENSTP/UNSTIM, 2025-2026.*
""")
