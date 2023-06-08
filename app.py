from flask import Flask, render_template
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
import requests
import werkzeug
import os
import sys
import atexit

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"}

browsers = [
    {'name': 'Firefox', 'driver': webdriver.Firefox, 'service': FirefoxService, 'manager': GeckoDriverManager},
    {'name': 'Chrome', 'driver': webdriver.Chrome, 'service': ChromeService, 'manager': ChromeDriverManager},
    {'name': 'Edge', 'driver': webdriver.Edge, 'service': EdgeService, 'manager': EdgeChromiumDriverManager}
]

driver = None

# Parcourir chaque navigateur et essayer de l'initialiser
for browser in browsers:
    try:
        service = browser['service'](browser['manager']().install())
        driver = browser['driver'](service=service)
        print(f"Navigateur {browser['name']} initialisé avec succès.")
        break  # Sortir de la boucle si l'initialisation du navigateur est réussie
    except Exception as e:
        print(f"Échec de l'initialisation du navigateur {browser['name']}: {e}")

# Vérifier si un navigateur a été initialisé avec succès
if driver is None:
    print("Aucun navigateur compatible trouvé. Fermeture...")
else:
    print("Driver connecté!")

    # Fermer le navigateur à la fermeture
    atexit.register(lambda: driver.quit())

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)


def get_champion_winrate(champion, role, patch=None):
    """
    Obtient un dictionnaire contenant un champion adverse, le winrate contre ce champion et son nombre de matchs.
    :param patch:
    :param champion:
    :param role:
    :return:
    """
    role = role.lower()
    champion = champion.lower()
    try:
        assert role in ["top", "jungle", "middle", "adc", "support"]
    except AssertionError:
        print(role)
        raise

    if patch:  # 13_10 not 13.10
        url = f"https://u.gg/lol/champions/{champion}/counter?patch={patch}&role={role}"
    else:
        url = f"https://u.gg/lol/champions/{champion}/counter&role={role}"
    driver.get(url)

    button_show_more = driver.find_element_by_class_name("view-more-btn")
    driver.execute_script("arguments[0].click();", button_show_more);

    soup = button_show_more(driver.page_source, "lxml")
    if len(soup.findAll("aside", limit=2)) > 1:
        print("Ahh")

    try:
        aside = soup.find("aside")
    except:
        print(soup.prettify())
        raise

    try:
        table_container = aside.find("div", class_="table-container")
    except:
        print(aside.prettify())
        raise

    try:
        table_champions_winrate = table_container.find("div") \
            .find("table") \
            .find("tbody")
    except:
        print(table_container.prettify())
        raise

    dict_champions_winrate = {}  # format: champ_name -> [winrate, number_of_games]
    for tr in table_champions_winrate.findAll("tr"):
        _, td_champ_name, td_winrate, td_games = tr.findAll("td")
        champ_name = td_champ_name.find("div").find("div").get_text()
        winrate = td_winrate.find("span").get_text().replace("%", "")
        number_of_games = td_games.find("span").get_text().replace(",", "")
        dict_champions_winrate[champ_name] = [winrate, number_of_games]
    return dict_champions_winrate


def get_pool_counters(pool, role, patch=None):
    dict_winrates = {champ: get_champion_winrate(champ, role, patch) for champ in pool}
    list_champions = [set(dict_winrates[key].keys()) for key in dict_winrates.keys()]
    set_champions = set()
    for new_set in list_champions:
        set_champions = set_champions | new_set  # ajoute le nouveau set de champions sans faire de doublons
    all_champs = sorted(list(set_champions))  # pour être *sûr* qu'il n'y a pas de doublons

    table = []  # format: champ -> best_champ, best_winrate, best_number_of_games
    for champ in all_champs:
        best_champ = "None"
        best_winrate = 0
        best_number_of_games = 0
        infos_by_champ = {}
        for pool_champ in pool:
            infos = dict_winrates[pool_champ].get(champ)
            if infos:
                winrate, number_of_games = float(infos[0]), int(infos[1])
                infos_by_champ[pool_champ] = f"{winrate:2.2f}%", f"{number_of_games:,}".replace(",", " ")
                if winrate and winrate > best_winrate:
                    best_winrate = winrate
                    best_champ = pool_champ
                    best_number_of_games = number_of_games
            else:
                infos_by_champ[pool_champ] = "0%", 0

        table.append(
            [champ, best_champ, f"{best_winrate:2.2f}%", f"{best_number_of_games:,}".replace(",", " "), infos_by_champ])
    return table


@app.route('/results/<pool>/<string:role>')
@app.route('/results/<pool>/<string:role>/<patch>')
def results(pool, role, patch=None):
    pool = pool.split(",")
    return render_template("results.html", pool_evaluation=get_pool_counters(pool, role, patch=patch), pool=pool,
                           role=role, patch=patch)


@app.route("/credits")
def page_credits():
    return render_template("credits.html")


@app.route("/")
@app.route("/home")
def home():
    with open("static/data/champs.csv", "r") as file:
        champs = file.read().split("\n")
    return render_template("home.html", champs=champs)


@app.errorhandler(werkzeug.exceptions.InternalServerError)
def handle_internal_server_error(exception):
    return render_template("error.html", exception=str(exception))
