from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import requests

import werkzeug  # server
import os
import sys
import re  # regular expressions
from urllib.parse import urlparse, parse_qs

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)


def keep_only_numbers(string):
    """Removes all characters except numbers and the decimal point from a string before returning it."""
    return re.sub(r'[^0-9.]', '', string)


def get_champion_winrate(champion, role, patch="latest", rank="default", region="default"):
    """Returns a dict containing, for each enemy champion, the winrate against it and the number of match.

    patch should be written as "13_9" or "13_10". ("13.9" or "13_09" won't work.)
    retry is the number of time we retried due to a stale element.

    return dict = format: champ_name -> [winrate, total_games]
    """
    champion = champion.lower()
    role = role.lower()
    try:
        assert role in ["top", "jungle", "middle", "adc", "support"]
    except AssertionError:
        print(role)
        raise

    print(champion, role, patch, rank, region, sep=" | ")
    url = f"https://u.gg/lol/champions/{champion}/matchups?role={role}"
    if patch != "latest":  # 13_10, not 13.10
        url += f"&patch={patch}"
    if rank != "default":
        url += f"&rank={rank}"

    if region != "default":
        url += f"&region={region}"
    print("URL visited:", url)
    response = requests.get(url, headers=headers, allow_redirects=True)

    try:
        response.raise_for_status()
    except Exception as excep:
        print(excep)
        return {}

    soup = BeautifulSoup(response.content, "lxml")

    try:
        counters_list = soup.find("div", class_="matchups-table").find("div", class_="rt-tbody")
    except Exception:
        print(soup.prettify())
        raise

    dict_champions_winrate = {}  # format: champ_name -> [winrate, total_games]
    for div in counters_list.findAll("div", class_="rt-tr-group"):
        row = div.find("div", class_="rt-tr")
        champ_name = row.find("div", class_="champion").find("a").find("div", class_="champion-name").get_text()
        winrate = keep_only_numbers(row.find("div", class_="win_rate").find("div").get_text())
        total_games = row.find("div", class_="matches").find("span").get_text()
        dict_champions_winrate[champ_name] = [winrate, total_games]
    return dict_champions_winrate


def get_pool_counters(pool, role, patch=None, delta=False, rank="default", region="default"):
    """
    Return a list containing the best counter among the pool for every champion, along with the WR and games of
    each pool champ.
    """

    dict_winrates = {champ: get_champion_winrate(champ, role, patch, rank, region) for champ in pool}

    dict_total_winrates = {}
    pool_totals = []

    # calculating total winrate and total games
    for pool_champ in pool:
        numerator_weighted_average = 0  # It should become the sum of winrate% * number_of_games
        denominator_weighted_average = 0  # It should become the total number of games on the champ.
        for winrate, number_of_games in dict_winrates[pool_champ].values():
            winrate = float(winrate) / 100
            number_of_games = int(number_of_games.replace(",", ""))
            numerator_weighted_average += winrate * number_of_games
            denominator_weighted_average += number_of_games
        average_winrate = numerator_weighted_average / denominator_weighted_average * 100
        dict_total_winrates[pool_champ] = average_winrate
        pool_totals.append(
            [pool_champ, f"{average_winrate:2.2f}%", f"{denominator_weighted_average:,}".replace(",", " ")]
        )

    list_champions = [set(dict_winrates[counter_champ].keys()) for counter_champ in dict_winrates.keys()]
    set_champions = set()
    for new_set in list_champions:
        set_champions = set_champions | new_set  # add the new set of champions without duplicates
    all_champs = sorted(list(set_champions))  # to be sure there isn't any duplicates

    table = []
    for counter_champ in all_champs:
        if counter_champ == "Annie":
            pass
        best_champ = "None"
        best_value = -100 if delta else 0
        best_number_of_games = 0
        infos_by_champ = {}

        for pool_champ in pool:
            infos = dict_winrates[pool_champ].get(counter_champ)

            if infos:
                winrate, number_of_games = float(infos[0]), int(infos[1].replace(",", ""))
                value = winrate - dict_total_winrates[pool_champ] if delta else winrate
                str_value = f"{value:+2.2f}%" if delta else f"{value:2.2f}%"
                infos_by_champ[pool_champ] = str_value, f"{number_of_games:,}".replace(",", "")

                if value > best_value:
                    best_value = value
                    best_champ = pool_champ
                    best_number_of_games = number_of_games
            else:
                infos_by_champ[pool_champ] = "-99.99%" if delta else "0%", 0

            str_best_value = f"{best_value:+2.2f}%" if delta else f"{best_value:2.2f}%"
        table.append([counter_champ, best_champ, str_best_value,
                      f"{best_number_of_games:,}".replace(",", " "), infos_by_champ])

    return table, pool_totals


@app.route("/results", methods=['GET'])
def results():
    pool = [champ.replace("'", "").replace(" ", "").replace(".", "") for champ in request.args.getlist('pool[]')]
    role = request.args.get("role")
    patch = request.args.get("patch")
    if patch == "custom":
        patch = request.args.get("patch_custom")
    delta = request.args.get("delta") == "on"
    rank = request.args.get("rank")

    region = request.args.get("region")
    pool_evaluation, pool_totals = get_pool_counters(pool, role, patch, delta, rank, region)
    return render_template("results.html",
                           pool_evaluation=pool_evaluation,
                           pool=pool,
                           role=role,
                           patch=patch,
                           delta=delta,
                           pool_totals=pool_totals,
                           rank=rank,
                           region=region)


@app.route("/credits")
def page_credits():
    return render_template("credits.html")


@app.route("/")
@app.route("/home")
def home():
    with open("static/data/champs.csv", "r") as file:
        champs = file.read().split("\n")
    return render_template("home.html", champs=champs)


@app.route("/error", defaults={'exception': None})
@app.errorhandler(werkzeug.exceptions.InternalServerError)
def handle_internal_server_error(exception):
    return render_template("error.html", exception=str(exception))
