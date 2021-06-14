"""
This module runs the entire NBA_bet project process daily one hour before the first game time.

It runs one hour before game times in order to capture the most up-to-date betting information. The project is meant to
be run from the command line. Once running, debug information from the scheduler will be printed as well as notifying
the user if a job has been successfully run. Terminate the process via a keyboard interrupt. For more details on what
happens during a scheduled job, refer to run/all.py

Example:
    From the project directory, run 'python -m run.daily'
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
import time

# Local Imports
from NBApredict.database import getters
from NBApredict.database.dbinterface import DBInterface
from NBApredict.run.all import run_all


def datetime_to_dict(d_time):
    """Take a datetime and convert it to a dictionary.

    The output is to be used as arguments for an apshceduler cron trigger."""
    time_dict = {"year": d_time.year, "month": d_time.month, "day": d_time.day, "hour": d_time.hour,
                 "minute": d_time.minute}
    return time_dict


def job_runs(event):
    """Attached to a Scheduler as a listener that prints job status on job completion."""
    if event.exception:
        print('The job did not run')
    else:
        print('The job completed @ {}'.format(datetime.now()))


def missed_job(event):
    print('The job was missed. Scheduling a new one to run in one minute')
    run_time = datetime_to_dict(datetime.now() + timedelta(minutes=1))
    scheduler.add_job(run_all, "cron", **run_time)
    scheduler.print_jobs()


if __name__ == "__main__":
    # DBInterface setup
    database = DBInterface()
    year = 2019
    session = Session(bind=database.engine)
    sched_tbl = database.get_table_mappings("sched_{}".format(year))

    # Get today and the last day of the season so jobs can be scheduled from today through end of season
    start_date = datetime.date(datetime.now())
    end_date = session.query(sched_tbl.start_time).order_by(sched_tbl.start_time.desc()).first()[0]
    end_date = datetime.date(end_date)

    # Get every date between now and the last day of the season
    date = start_date
    game_dates = [date]
    while date <= end_date:
        date = date + timedelta(days=1)
        game_dates.append(date)

    # Get start times for every day in date if there are games on that day
    start_times = []
    for date in game_dates:
        first_game_time = getters.get_first_game_time_on_day(sched_tbl, session, date)
        if first_game_time:
            start_times.append(first_game_time - timedelta(hours=1))

    # Transform start times into chron arguments for triggers
    cron_args = [datetime_to_dict(s_time) for s_time in start_times]
    # cron_args = [datetime.now() + timedelta(minutes=i*5) for i in range(1, 2)]  # TEST
    # cron_args = [datetime_to_dict(d_time) for d_time in cron_args]  # TEST

    # Setup scheduler, add jobs and listeners, and start the scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_listener(job_runs, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_listener(missed_job, EVENT_JOB_MISSED)
    for kwargs in cron_args:
        scheduler.add_job(run_all, "cron", **kwargs, misfire_grace_time=60)
    scheduler.start()
    scheduler.print_jobs()

    logging.basicConfig()
    logging.getLogger('apscheduler').setLevel(logging.DEBUG)

    try:
        sleep_time = 0
        while True:
            time.sleep(1)
            sleep_time += 1
            if sleep_time >= 600:
                scheduler.wakeup()
                sleep_time = 0
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
