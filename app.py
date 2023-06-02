from flask import Flask, render_template
from bs4 import BeautifulSoup
import requests
import werkzeug

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"}

app = Flask(__name__, static_folder='./static', template_folder='./templates')


def get_soup(url):
    """
    Obtient la soupe d'html grâce à une url.
    """
    return BeautifulSoup(requests.get(url, headers=headers).content, "lxml")


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
        assert role in ["top", "jungle", "mid", "adc", "bot", "support"]
    except AssertionError:
        print(role)
        raise
    if patch:
        url = f"https://www.op.gg/champions/{champion}/{role}/counters?patch={patch}"
    else:
        url = f"https://www.op.gg/champions/{champion}/{role}/counters"
    soup = get_soup(url)
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


if __name__ == '__main__':
    app.run()
