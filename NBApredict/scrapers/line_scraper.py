"""
line_scraper scrapes NBA betting odds from Bovada and stores them in the database.
"""

from datetime import datetime, timedelta
import re
import requests
from sqlalchemy import UniqueConstraint, ForeignKey, Integer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, relationship

# Local Imports
from NBApredict.configuration import Config
from NBApredict.database.manipulator import DataOperator
from NBApredict.database import getters
from NBApredict.database.reconcile import reconcile


def bovada_json_request(url):
    response = requests.get(url, allow_redirects=False).json()
    if not len(response):
        return None
    return response


def odds_for_today():
    """Match betting odds from Bovada to the games_query and return the odds

    Args:
        date to reflect the current games on Bovada.

    Returns:
        A dictionary where the column keys lists of values
    """
    scrape_time = datetime.now()

    # Check for response from Bovada
    url = Config.get_property("regularURL")
    response = bovada_json_request(url)
    if not response:
        url = Config.get_property("playoffURL")
        response = bovada_json_request(url)
        if not response:
            return None

    # Move down tree towards games
    events = response[0]["events"]

    # Strip games from the 'event's object (which holds a bunch of random information)
    bovada_games = [e for e in events if e['description'].count('@') > 0 and e['type'] == 'GAMEEVENT']
    if not bovada_games:
        return None

    # Set-up the line dictionary which stores data in the correct table format
    lines = {"home_team": [], "away_team": [], 'start_time': [], "spread": [], "home_spread_price": [],
             "away_spread_price": [], "home_moneyline": [], "away_moneyline": [], "scrape_time": []}

    # Iterate through each game returned by bovada and store its information
    for game in bovada_games:
        link = game['link'].split('-')
        link = link[len(link)-1]
        str_time = re.findall('[0-9]', link)
        start_time = ''.join(str_time)
        start_time = datetime.strptime(start_time, "%Y%m%d%H%M")
        if datetime.now() > start_time:
            # An ongoing game will not have the correct betting data. We don't want to store this information
            print("This game ({}) is either ongoing or completed. Not scraping".format(game['description']))
            continue

        home_team, away_team = parse_teams(game["competitors"])

        # Get only the full match betting information from the game object
        betting_info = game["displayGroups"][0]["markets"]
        full_match_bets = [bet for bet in betting_info if bet["period"]["description"] == "Match"]

        # Extract the betting data associated with the game
        money_lines = False
        for bet in full_match_bets:
            if bet["description"] == "Moneyline":
                home_moneyline, away_moneyline = parse_moneyline(bet)
                if home_moneyline == "":
                    home_moneyline = None
                if away_moneyline == "":
                    away_moneyline = None
                money_lines = True
            elif bet["description"] == "Point Spread":
                spread, home_spread_price, away_spread_price = parse_spread(bet)
                if spread == "":
                    spread = None
                if home_spread_price == "":
                    home_spread_price = None
                if away_spread_price == "":
                    away_spread_price = None
        if not money_lines:
            home_moneyline = None
            away_moneyline = None

        game_lines = [home_team, away_team, start_time, spread, home_spread_price, away_spread_price, home_moneyline,
                      away_moneyline, scrape_time]

        # This section depends on python 3.7+ to preserve the order of dict keys in lines
        i = 0
        for key in lines:
            lines[key].append(game_lines[i])
            i += 1
    return lines


def parse_teams(competitors):
    """Parse a competitors object from Bovada and return the home and away teams, respectively"""
    if len(competitors) > 2:
        raise Exception("Unexpected objects in competitors")
    home_team = ""
    away_team = ""
    for team in competitors:
        if team["home"]:
            home_team = team["name"]
        else:
            away_team = team["name"]
    if not home_team == "" or away_team == "":
        return home_team.upper(), away_team.upper()
    else:
        raise Exception("Competitors was not properly parsed. Missing data.")


def parse_moneyline(moneyline_bet):
    """Parse a moneyline bet object from Bovada and return, in order, the home and away moneyline"""
    outcomes = moneyline_bet["outcomes"]
    home_moneyline = ""
    away_moneyline = ""
    if len(outcomes) > 2:
        raise Exception("Unexpected objects in moneyline bet")
    for o in outcomes:
        price = o["price"]["american"]
        if price == "EVEN":
            price = 100
        else:
            price = int(price)
        if o["type"] == "H":
            home_moneyline = price
        elif o["type"] == "A":
            away_moneyline = price
    if not home_moneyline == "" or away_moneyline == "":
        return home_moneyline, away_moneyline
    else:
        raise Exception("Moneyline was not properly parsed. Missing data.")


def parse_spread(spread_bet):
    """Parse a spread bet object from Bovada and return, in order, the spread and the home and away spread prices"""
    outcomes = spread_bet["outcomes"]
    spread = ""
    home_spread_price = ""
    away_spread_price = ""
    if len(outcomes) > 2:
        raise Exception("Unexpected objects in spread bet")
    for o in outcomes:
        if o["type"] == "H":
            spread = float(o["price"]["handicap"])
            home_spread_price = int(o["price"]["american"])
        elif o["type"] == "A":
            away_spread_price = int(o["price"]["american"])
    if not spread == "" or home_spread_price == "" or away_spread_price == "":
        return spread, home_spread_price, away_spread_price
    else:
        raise Exception("Spread was not properly parsed. Missing data.")


def create_odds_table(database, data, tbl_name, sched_tbl):
    """Creates an odds_table in the database based on the data with foreign key based on the schedule

    Args:
        database: An instance of the DBInterface class from database/DBInterface.py
        data: A DataOperator object from database/manipulator which holds the data and
        tbl_name:
        sched_tbl: The schedule table which will contain the game_id for the odds_table and which will be given a
        relationship to the odds table
    """
    # Set columns and constraints
    sql_types = data.get_sql_type()
    sched_tbl_name = sched_tbl.classes.items()[0][0]
    sql_types.update({'game_id': [Integer, ForeignKey(sched_tbl_name + ".id")]})
    constraint = {UniqueConstraint: ["home_team", "away_team", "start_time"]}

    database.map_table(tbl_name, sql_types, constraint)  # Maps the odds table

    # Establish relationship if it does not exist
    if "odds" not in sched_tbl.__mapper__.relationships.keys():
        sched_tbl.odds = relationship(database.Template)

    database.create_tables()
    database.clear_mappers()


def update_odds_table(odds_table, sched_tbl, rows, session):
    """Update the odds_table with the information in rows

    Args:
        odds_table: A mapped odds table object from the database
        sched_tbl: A mapped schedule table object from the database
        rows: A dictionary of rows with column names as keys with lists of values
        session: A SQLalchemy session object
    """
    row_objects = []
    if len(rows) == 0:  # Avoid messing with things if no rows exist
        print("No new odds available. Returning without updating odds table")
        return
    for row in rows:
        # Delete the row in the table if it exists to allow overwrite
        existing_rows = session.query(odds_table).filter(odds_table.home_team == row["home_team"],
                                                         odds_table.away_team == row["away_team"],
                                                         odds_table.start_time == row["start_time"])
        if len(existing_rows.all()) > 0:
            for exist_row in existing_rows.all():
                session.delete(exist_row)

        # Adds all of the normal betting data
        row_object = odds_table(**row)

        # Finds and adds the foreign key from the schedule
        game = session.query(sched_tbl).filter(sched_tbl.home_team == row_object.home_team,
                                               sched_tbl.away_team == row_object.away_team,
                                               sched_tbl.start_time == row_object.start_time).all()
        if len(game) > 1:
            raise Exception("More than one game matches the row")
        game = game[0]
        row_object.game_id = game.id

        row_objects.append(row_object)
    try:
        session.add_all(row_objects)
    except IntegrityError:  # If all objects cannot be added, try to add each one individually
        for row in row_objects:
            try:
                session.add(row)
            except IntegrityError:
                continue


def scrape():
    """Scrapes betting line information from bovada and adds it to the session"""
    league_year = Config.get_property("league_year")
    lines = odds_for_today()
    if not lines:
        return False
    return lines

    line_data = DataOperator(lines)

    tbl_name = "odds_{}".format(league_year)
    tbl_exists = database.table_exists(tbl_name)
    if not tbl_exists:
        create_odds_table(database, line_data, tbl_name, schedule)
        tbl_exists = database.table_exists(tbl_name)

    if line_data.validate_data_length() and tbl_exists:
        # All values in line_data are expected to be be unique from values in the database. A possible place for errors
        # to occur
        odds_table = database.get_table_mappings([tbl_name])

        # Reconcile ensures the odds_table has appropriate start_times; Add logic so its not called every run
        reconcile(schedule, odds_table, "start_time", "id", "game_id", session)

        update_odds_table(odds_table, schedule, line_data.dict_to_rows(), session)
    else:
        raise Exception("Something is wrong here (Not descriptive, but this point shouldn't be hit.)")

    return True


if __name__ == "__main__":
    from datatotable.database import Database
    db = Database("test", Config.get_property("outputs"))
    year = 2019
    session = Session(bind=db.engine)
    scrape(db, session)
