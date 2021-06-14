"""
Predict.odds contains functions organized around comparing predictions to odds

ToDo:
    In theory, the module will allow multiple model inputs. Thus, we can pass it a linear, bayesian, ML, etc. model,
    generate results, and store them. That functionality does not exist. This should also have a class of some sort to
    manage predictions. It will add specificity and remove call complexity and name overlaps (i.e.
    predict_games_on_day() vs. predict_games_on_date())
"""

from datetime import datetime
import numpy as np
import pandas as pd
import scipy.stats as stats
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

# Local imports
from NBApredict.configuration import Config
from NBApredict.helpers import br_references
from datatotable.database import Database
from datatotable.data import DataOperator
from NBApredict.database import getters
from NBApredict.management import conversion
from NBApredict.management.tables import predictions
from NBApredict.models import four_factor_regression as ff_reg


def get_prediction(reg, pred_df):
    """Generate and return a prediction for the observations in the pred_df.

    Args:
        reg: LinearRegression class from four_factors_regression.py
        pred_df: A dataframe of observations, with home and away statistics, from which to generate a prediction

    Returns:
        The predicted value generated from the regression object and the predictors"""
    return reg.results.predict(pred_df).values[0]


def get_team_name(team):
    """Match team to a standard team name and return the br_references standard team name."""
    for team_name in br_references.Team:
        if team.lower() == team_name.value.lower():
            return team_name.value


# def create_prediction_df(home_tm, away_tm, ff_df):
#     """Create and return a dataframe that merges the four factors for the home and away team.
#     TODO: Replace with ff_reg.alt_regression_df/getregression_df
#
#     Args:
#         home_tm: The home team
#         away_tm: The away team
#         ff_df: Dataframe of the four factors for all teams
#
#     Returns:
#         A single row four factors data frame of the home and away team's four factors
#     """
#     home_ff = get_team_ff(home_tm, ff_df, home=True)
#     away_ff = get_team_ff(away_tm, ff_df, home=False)
#     home_ff["key"] = 1
#     home_ff["const"] = 1.0  # sm.add_const does not add a constant for whatever reason
#     away_ff["key"] = 1
#     merged = pd.merge(home_ff, away_ff, on="key", sort=True)
#     merged = merged.drop(["key"], axis=1)
#     merged = merged.sort_index(axis=1)
#     return merged


def get_team_ff(team, ff_df, home):
    """Create and return a data frame of the four factors for the specified team.

    Args:
        team: The team to extract the four factors for
        ff_df: A dataframe of the four factors
        home: Boolean which dictates if an '_h or '_a' should be appended to the team's stats

    Returns:
        The four factors, with a home or away suffix, for a team are returned as a data frame
    """
    ff_list = br_references.four_factors
    team_ff = ff_df[ff_df.team_name.str.lower() == team.lower()][ff_list]
    if home:
        team_ff = team_ff.rename(ff_reg.append_h, axis='columns')
    else:
        team_ff = team_ff.rename(ff_reg.append_a, axis='columns')
    return team_ff


def line_probability(prediction, line, std):
    """Calculate and return the CDF or SF, as appropriate, of the line if the model were true.

    "if the model were true" means that if the assumption holds that the residuals are homoscedastic and follow a
    normal distribution

    Args:
        prediction: The prediction for a game
        line: The line associated with the same game as the prediction
        std: The standard deviation of the residuals for the model used to make the prediction

    Returns:
        The survival function or cumulative density function for the line in relation to the prediction
    """
    # ToDo: T-Distribution?
    dist = stats.norm(loc=prediction, scale=std)
    line_prediction = -1 * line

    if prediction > line_prediction:
        return dist.cdf(line_prediction), "cdf"
    elif prediction < line_prediction:
        return dist.sf(line_prediction), "sf"
    elif prediction == line_prediction:
        return 0.5  # If the predictions are equal, the cdf automatically equals 0.5


def prediction_result_console_output(home_tm, away_tm, line, prediction, probability):
    """Generate human readable printout comparing the model's predictions, the line, and the p_value of the line.

    Args:
        home_tm: The home team
        away_tm: The away team
        line: The betting line
        prediction: A prediction of the home team's margin of victory
        probability: The probability of the betting line as determined by a CDF or SF
    """
    if prediction > 0:
        print("The {} are projected to beat the {} by {} points".format(home_tm, away_tm, prediction))
        if (-1 * line) < prediction:
            print("If the model were true, the betting line's ({}) CDF, in relation to the prediction, would "
                  "be realized {}% of the time".format(line, probability))
        else:
            print("If the model were true, the betting line's ({}) SF, in relation to the prediction, would "
                  "be realized {}% of the time".format(line, probability))
    if prediction < 0:
        print("The {} are projected to lose to the {} by {} points".format(home_tm, away_tm, prediction))
        if (-1 * line) < prediction:
            print("If the model were true, the betting line's ({}) CDF, in relation to the prediction, would "
                  "be realized {}% of the time".format(line, probability))
        else:
            print("If the model were true, the betting line's ({}) SF, in relation to the prediction, would "
                  "be realized {}% of the time".format(line, probability))


def insert_predictions(rows, session, pred_tbl, sched_tbl):
    """Add rows into the prediction table in session with additional information from sched_tbl and odds_tbl.

    # ToDo: Will need equivalent function, but it won't look like this
    Args:
        rows: SQLalchemy compatible rows
        session: A SQLalchemy session object
        pred_tbl: A mapped prediction table object
        sched_tbl: A mapped scheduled table object
    """
    row_objects = []
    for row in rows:
        row_obj = pred_tbl(**row)
        row_objects.append(row_obj)
    row_objects = update_schedule_attributes(row_objects, session, sched_tbl)

    session.add_all(row_objects)


def insert_new_predictions(rows, session, pred_tbl, sched_tbl, odds_tbl):
    """Insert unique predictions in rows which do not already exist in the prediction table.

    Additional information from sched_tbl and odds_tbl is added to the rows as well.

    # ToDo: Will need significant rewrite (Also note similarities between this function and the one above)
    Args:
        rows: SQLalchemy compatible rows
        session: a SQLalchemy session object
        pred_tbl: A mapped prediction table object
        sched_tbl: A mapped scheduled table object
        odds_tbl: A mapped odds_tbl object
    """
    row_objects = []
    existing_predictions = session.query(pred_tbl.home_team, pred_tbl.away_team, pred_tbl.start_time).all()
    existing_predictions = [(game.home_team, game.away_team, game.start_time) for game in existing_predictions]
    for row in rows:
        game_identifier = (row["home_team"], row["away_team"], row["start_time"])
        if game_identifier in existing_predictions:
            continue
        else:
            row_obj = pred_tbl(**row)
            row_objects.append(row_obj)
    if len(row_objects) > 0:
        row_objects = update_odds_id(row_objects, session, odds_tbl)
        row_objects = update_schedule_attributes(row_objects, session, sched_tbl)
        session.add_all(row_objects)


def update_prediction_table(session, pred_tbl, sched_tbl, odds_tbl):
    """Find and update null or 0 values in the score, odds_id, or bet_result columns of the prediction table.

    Args:
        session: A SQLalchemy session object
        pred_tbl: A mapped prediction table object
        sched_tbl: A mapped scheduled table object
        odds_tbl: A mapped odds_tbl object
    """
    score_update_objs = session.query(pred_tbl).filter(or_(pred_tbl.home_team_score == 0,
                                                           pred_tbl.away_team_score == 0)).all()
    session.add_all(score_update_objs)

    bet_update_objs = session.query(pred_tbl).filter(pred_tbl.bet_result.is_(None), pred_tbl.home_team_score > 0).all()
    bet_update_objs = update_bet_results(bet_update_objs)
    session.add_all(bet_update_objs)


def update_bet_results(bet_update_objects):
    """Take bet_update_objects, determine the prediction result, and add the result to each row in bet_update_objects.

    # ToDo: Will need this function, but will require a lot of modification
    Args:
        bet_update_objects: Objects from a query.all() from the prediction table. Objects should have a home and
        away team score.

    Returns:
        bet_update_objects updated with the bet results (WIN, LOSS, or PUSH).
    """
    for row in bet_update_objects:
        score_margin = row.home_team_score - row.away_team_score
        line_inverse = row.line * -1
        prediction = row.prediction
        if score_margin == line_inverse:
            row.bet_result = "PUSH"
        elif (score_margin < line_inverse) and (prediction < line_inverse):
            row.bet_result = "WIN"
        elif (score_margin > line_inverse) and (prediction > line_inverse):
            row.bet_result = "WIN"
        else:
            row.bet_result = "LOSS"
    return bet_update_objects


def get_sample_prediction(session, regression):
    """Generate and return a sample prediction formatted specifically for table creation.

    Args:
        session: A SQLalchemy session object
        regression: A regression object from four_factor_regression.py

    Returns:
        A DataOperator object initialized with a prediction from regression
    """
    one_row_dataframe = regression.predictors.loc[[0]]

    sample_prediction = predict_game(session, regression, one_row_dataframe)
    data = DataOperator(sample_prediction)
    return data


def predict_game(session, regression, x_df, console_out=False):
    """Predict a game and return the information in a dictionary.

    Use console out for human readable output if desired.Cdf is a cumulative density function. SF is a survival
    function. CDF is calculated when the betting line's prediction is below the model's prediction. SF is calculated
    when the betting line's prediction is above the model's prediction.

    Args:
        session: A SQLalchemy session object
        regression: A regression object

        console_out: If true, print the prediction results. Ignore otherwise
    """

    prediction = get_prediction(regression, x_df)
    # probability, function = line_probability(prediction, line, np.std(regression.residuals))

    # if console_out:
    #     prediction_result_console_output(home_tm, away_tm, prediction, probability)

    return {"prediction": prediction}


def predict_games_in_odds(session, regression, odds_tbl):
    """Generate and return predictions for all games with odds in the odds_tbl

    ToDo: Take tables as inputs vs. DB
    Args:
        session: A SQLalchemy session object
        regression: A linear regression object generated from four_factor_regression
        odds_tbl: Mapped sqlalchemy odds table

    """
    all_odds = session.query(odds_tbl).all()
    predictions = []
    for odds in all_odds:
        home_team = odds.home_team
        away_team = odds.away_team
        start_time = odds.start_time
        line = odds.spread
        predictions.append(predict_game(session, regression, home_team, away_team, start_time, line))
    return predictions


def predict_games_on_day(database, session, games, console_out=False):
    """Take a SQLalchemy query object of games, and return a prediction for each game.

    ToDO: On day versus on date?
    Args:
        database: an instantiated DBInterface class from database.dbinterface.py
        session: A SQLalchemy session object
        games: a SQLalchemy query object of games containing start_time, home_tm, away_tm, and the spread
        console_out: A bool. True to print prediction outputs
    """
    results = []
    regression = ff_reg.main(database=database, session=session, year=year)
    try:
        for game in games:
            prediction = predict_game(database=database, session=session, regression=regression, home_tm=game.home_team,
                                      away_tm=game.away_team, start_time=game.start_time, line=game.spread,
                                      console_out=console_out)
            results.append(prediction)
    except AttributeError:
        # If games doesn't contain spreads, catch the attribute error and pass a 0 line.
        # If games is missing other data, function will break.
        for game in games:
            prediction = predict_game(database=database, session=session, regression=regression, home_tm=game.home_team,
                                      away_tm=game.away_team, start_time=game.start_time, line=0,
                                      console_out=console_out)
            results.append(prediction)
    return results


def predict_games_on_date(database, session, league_year, date, console_out):
    """Predict games on the specified date and write the results to the database

    ToDO: On day versus on date?
    Args:
        database: An instantiated DBInterface class from dbinterface.py
        session: A sqlalchemy session object for queries and writes
        league_year: The league year to work with. For example, the league year of the 2018-19 season is 2019
        date: Either a datetime.date or a dictionary keyed formatted as {"day": day, "month": month, "year": year"}
        console_out: If true, prints prediction results to the console
    """
    # Get lines for the games
    if not isinstance(date, datetime):
        date = datetime(date["year"], date["month"], date["day"])
    odds_tbl = database.get_table_mappings(["odds_{}".format(league_year)])
    games_query = getters.get_spreads_for_date(odds_tbl, session, date)
    game_spreads = [game for game in games_query]

    results = predict_games_on_day(database, session, game_spreads, console_out=console_out)

    prediction_tbl = "predictions_{}".format(league_year)
    data = DataOperator(results)

    sched_tbl = database.get_table_mappings("sched_{}".format(league_year))
    pred_tbl = database.get_table_mappings("predictions_{}".format(league_year))

    # Results are sent to DataOperator in row format, so just pass data.data instead of data.dict_to_rows()
    try:
        insert_predictions(data.data, session, pred_tbl, sched_tbl, odds_tbl)
        session.commit()
    except IntegrityError:
        session.rollback()
        update_prediction_table(session, pred_tbl, sched_tbl, odds_tbl)
        session.commit()
    finally:
        session.close()


def predict_all(db):
    """Generate and store predictions for all games available in the odds table.

    Checks if the table exists. If it doesn't, generate a table in the database.
    """
    session = Session(bind=db.engine)
    league_year = Config.get_property("league_year")
    sched_tbl = db.table_mappings["schedule_{}".format(league_year)]
    team_stats_tbl = db.table_mappings['team_stats_{}'.format(league_year)]
    odds_tbl = db.table_mappings['odds_{}'.format(league_year)]

    regression = ff_reg.main(session, team_stats_tbl, sched_tbl)

    pred_tbl_name = "predictions_{}".format(league_year)

    if not db.table_exists(pred_tbl_name):
        sample = get_sample_prediction(session, regression, sched_tbl)
        pred_data = predictions.format_data()
        predictions.create_table()
        pred_tbl = db.table_mappings[pred_tbl_name]
        session.add_all([pred_tbl(**row) for row in pred_data.rows])
        session.commit()
    else:
        # Data operator
        pred_tbl = db.table_mappings[pred_tbl_name]
        schedule_tbl = db.table_mappings[pred_tbl_name]
        update_rows = predictions.insert(session, )
        results = predict_games_in_odds(session, regression, odds_tbl)
        session.add_all(update_rows)
        session.commit()

    insert_new_predictions(results, session, pred_tbl, sched_tbl, odds_tbl)

    session.commit()  # Commit here b/c update_prediction_tbl() needs the inserted values

    update_prediction_table(session, pred_tbl, sched_tbl, odds_tbl)


if __name__ == "__main__":
    db = Database('test', "../management")
    predict_all(db)
    predict_game("Sacramento Kings", "Orlando Magic", line=-5.5, year=2019, console_out=True)
    date = datetime(2019, 3, 26)
    predict_games_on_date(db, session, league_year=2019, date=date, console_out=True)
