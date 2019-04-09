# NBA_bet

NBA_bet is a package for predicting NBA games against betting lines. It has two main behaviors: 
1. Scrape and store team statistics, game results, and betting lines.
2. Generate predictions for each NBA game, compare the prediction to the betting line, and store the results.

## Project Overview
### Directories
This section overviews the main components of the project. Details for other sections of the project are available in the documentation. 

* run - The run directory holds two scripts, daily.py and all.py. The daily script will set the project to run daily while the all script runs the project when called. 
* scrapers - The scrapers folder holds modules for scaping data. scraper.py's scrape_all() function will scrape all season, team, and betting line data. To just scrape one type of data, call the desired data's scrape function. For example, line_scraper.scrape() will scrape betting lines.
* database - This directory holds three modules. database/database holds a Database class. The database class controls table access and creation. database/manipulator holds the DataManipulator class which manipulates input data for table creation and insertion. Combined, Database and DataManipulator allow the data to dictate tables in the database. Finally, getters.py has functions which return specific queries or datatypes from the database. 
* stats - The stats directory contains the four_factor_regression and graphing modules. four_factor_regression implements a linear regression based on the four factors as explained in [the model section](#the-model). The graphing module functions generate graphs for regression evaluation.
* predict - Holds the predict module. The predict module has functions for predicting games on a date, a single game, or all games for which betting odds exist. Predict generates predictions from the linear model discussed in [the model section](#the-model)


## The Model
As of now, the model uses a linear regression based on the [Four Factors of Basketball Success](https://www.basketball-reference.com/about/factors.html) which encapsulates shooting, turnovers, rebounding, and free throws. Further, we include the opposing four factors, which are how a team's opponents perform on the four factors in aggregate. Thus, each team has eight variables, and the model uses sixteen variables (eight for each team) for each prediction. The target, Y, or dependent variable is home Margin of Victory (MOV). Away MOV is simply the inverse of home MOV. 

### What are betting lines? 
MOV is targeted because it provides an easy comparison with two types of betting lines, the spread and moneyline. Here's what the spread and moneyline might look like for a matchup between the Milwaukee Bucks and Atlanta Hawks:

Milwaukee Bucks (Home):
1. Spread: -8
2. Moneyline: -350

Atlanta Hawks (Away):
1. Spread: 8
2. Moneyline: 270

First, the spread attempts to guess the MOV between two teams. The Milwaukee Bucks spread of -8 indicates the betting line expects the Bucks to beat the Hawks by eight points. Or, the Bucks are "given" eight points. If one thinks the Bucks will beat the Hawks by more than eight points, they bet the Bucks. If one believes the Bucks will either win by less than eight points or lose, they bet the Hawks. Typically, spreads have symetric, or near-symetric, returns where picking the Bucks or the Hawks provides an equal return on a correct bet.

In comparison, the moneyline states the likelihood of a team winning or losing in terms of a monetary return. A negative moneyline, such as the Buck's -350, means one must put up $350 in order to win $100. A positive moneyline, such as the Hawk's 270, means a bet of $100 will return $270 if it is correct. 

### Generating Predictions

Before comparing predictions to betting lines, we need to ensure the model meets the assumptions of regression. For now, assume assumptions are met, and refer to [Additional Reading](#additional-reading) for further model discussion. To compare the model's predictions to betting lines, we look at the prediction's distance from the betting line. In the model, the prediction is the expected value, or the mean, of the matchup. All possible outcomes of the game are normally distributed around this mean with a standard deviation, which as of 04/07/2019, is approximately thirteen. 

Continuing the Bucks-Hawks example, lets say the model predicts the Bucks to win by 6 in comparison to the betting line of 8. To compare the betting line to the prediction, we want to evaluate the likelihood of a Bucks win by 8 or more given a normal distribution with a mean of 6 and standard deviation of 13. Thus, we calculate the survival function** of 8 based on the distribution. The result is approximately 0.44 which means we'd expect the home MOV to be greater than or equal to 8 44% of the time. Inversely, we expect the home MOV to be less than 8 approximately 56% of the time. 

To compare moneylines instead of spreads, simply set the spread to 0, and the output will be the likelihood of a win or loss. 

This process is repeated for every game where odds are available, and the results are stored in the predictions table in the database. 

*The variance inflation factor of the intercept is very high. I have no clue if this is bad or unexpected. Any advice on the consequences of this are appreciated.

**The model uses a cumulative density function when the predicted MOV is greater than the betting line

## Usage
Clone this repo to your local machine: https://github.com/Spencer-Weston/NBA_bet.git

To set the project to run daily:
```~\NBA_bet>python -m run.daily```

Or to run the project once:
```~\NBA_bet>python -m run.all```


## Status: Minimum Viable Product (V0.1)

In its current status, the project operates as a concurrent whole. From the run directory, the user can either run the project at their leisure with run.all, or they can set the project to run daily with run.daily which schedules run.all to run each day. Either method builds all databases and tables, scrapes all data, and predicts all games. In this sense, it's a viable product.

The project is minimal because it doesn't do anything else. First, it contains no other functionality and/or no method for propogating functionality through the project at run time. For example, the regression model has graphing functions available, but the user cannot specify graph generation unless they run the regression script on its own. Second, the project only generates predictions with a linear model on a specific subset of data. A better product would allow the user to choose their desired data and model. Finally, the current product lacks infrastructure. There are no tests, and there is no setup.py. Thus, the project is not particularly resiliant to bugs nor automatically reproducible for users across environments. 

## Author
Spencer Weston

personal website: [Crockpot Thoughts](https://crockpotthoughts.wordpress.com/)

## Additional Reading
* Will be added as published 

## Credits:
Jae Bradley: https://github.com/jaebradley/basketball_reference_web_scraper
    - Used to scrape games and game results

## License
MIT
