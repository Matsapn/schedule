
# Install & Import libraries
from operator import itemgetter
import pandas as pd
import random
import pulp
import xlrd
import openpyxl
import streamlit as st
import plotly.express as px
from PIL import Image
import io
import os
import warnings
#from pandas.api.types import CategoricalDtype
warnings.filterwarnings('ignore')

# Page Design

st.set_page_config(page_title="NETCARE",layout="wide")

st.title("Shift Schedule Overview")
st.markdown('<style>div.block-container{padding-top:1rem;}</style>',unsafe_allow_html=True)

#Side bar Coding

# Logo

img = Image.open("Capture.PNG")

st.sidebar.image (img, width=250)

# File uploads

dfs = []
workerdf = []
quarters = []

uploaded_worker_file = st.sidebar.file_uploader("Upload worker availability", type=['csv', 'xlsx'])
uploaded_quarters_file = st.sidebar.file_uploader("Upload quarters requirement", type=['csv','xlsx'])
 
if uploaded_worker_file and uploaded_quarters_file:
    if uploaded_worker_file.name.endswith('.xlsx'):
        workerdf = pd.read_excel(uploaded_worker_file)
        st.subheader("Worker Availability:")
        st.write(workerdf)
    else:
            workerdf = pd.read_csv(uploaded_worker_file)
 
    if uploaded_quarters_file.name.endswith('.xlsx'):
        quarters = pd.read_excel(uploaded_quarters_file)
        st.subheader("No. of people required per quarter:")
        st.write(quarters)
    else:
            quarters = pd.read_csv(uploaded_quarters_file)


#######################################################################
# Gen

# Divide total week hours of 84 into 42 periods of 4-hours each week.
# Where: 0 = Monday 0-4, 1 = Monday 4-8, 2 = Monday 8-12........ 39 = Sunday 12-16, 40 = Sunday 16-20, 41 = Sunday 20-24
# Multiply 4 quaters a day by 7 days to get 28 quarters per week.
# quarters = [5, 4, 10, .... , 8, 9, 12] Amount of workers needed for each quarter of day.

NUM_WORKERS = 25
AM_PERIODS = 42
AM_QUARTERS = 28

periods = [
    "{} {}-{}".format(
        day, hour*4, (hour+1)*4
    ) for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] for hour in range(6)
]

worker_data = {}

for worker in range(NUM_WORKERS):
    worker_data["worker{}".format(str(worker))] = {
        "period_avail": [random.randint(0,1) for period in range(AM_PERIODS)],
        "skill_level": random.randint(0,100),
    }



def model_problem():

    workers_data = {}
    for iteration in workerdf.iterrows():
        row = iteration[1]
        name = row[0]
        workers_data[name] = {}
        workers_data[name]["skill_level"] = row[1]
        workers_data[name]["period_avail"] = []
        for day in range(7):
            for period in range(6):
                workers_data[name]["period_avail"].append(
                    int((period*4 >= row[2 + day * 2]) and ((period+1)*4 <= row[2 + day*2 + 1]))
                )

    problem = pulp.LpProblem("ScheduleWorkers", pulp.LpMinimize)

    workerid = 0
    for worker in workers_data.keys():
        workerstr = str(workerid)
        periodid = 0

        workers_data[worker]["worked_periods"] = []
        workers_data[worker]["rest_periods"] = []
        workers_data[worker]["weekend_periods"] = []

        for period in workers_data[worker]["period_avail"]:

            periodstr = str(periodid)
            # worked periods: worker W works in period P
            workers_data[worker]["worked_periods"].append(
                pulp.LpVariable("x_{}_{}".format(workerstr, periodstr), cat=pulp.LpBinary, upBound=period)
            )
            # rest periods: worker W takes a 12-hour rest starting on period P
            workers_data[worker]["rest_periods"].append(
                pulp.LpVariable("d_{}_{}".format(workerstr, periodstr), cat=pulp.LpBinary)
            )
            # weekend periods: worker W takes a 48-hour rest starting on period P
            workers_data[worker]["weekend_periods"].append(
                pulp.LpVariable("f_{}_{}".format(workerstr, periodstr), cat=pulp.LpBinary)
            )

            periodid += 1

        workerid += 1

    # Create objective function (amount of turns worked)
    objective_function = None
    for worker in workers_data.keys():
        objective_function += sum(workers_data[worker]["worked_periods"])

    problem += objective_function

    # Every quarter minimum workers constraint
    for quarter in range(AM_QUARTERS):
        workquartsum = None
        for worker in workers_data.keys():
            workquartsum += workers_data[worker]["worked_periods"][quarter + quarter // 2] + workers_data[worker]["worked_periods"][quarter + quarter // 2 + 1]

        problem += workquartsum >= quarters.iloc[0,quarter]

    # No worker with skill <= 25 is left alone
    for period in range(AM_PERIODS):
        skillperiodsum = None
        for worker in workers_data.keys():
            skillperiodsum += workers_data[worker]["worked_periods"][period] * workers_data[worker]["skill_level"]

        problem += skillperiodsum >= 26

    # Each worker must have one 12-hour break per day
    for day in range(7):
        for worker in workers_data.keys():
            problem += sum(workers_data[worker]["rest_periods"][day * 6:(day + 1) * 6]) >= 1

    # If a worker takes a 12-hour break, can't work in the immediate 3 periods

    for period in range(AM_PERIODS):
        for worker in workers_data.keys():
            access_list = [period, (period + 1) % 42, (period + 2) % 42]
            problem += sum(list((workers_data[worker]["worked_periods"]))) <= 3 * (1 - workers_data[worker]["rest_periods"][period])

    # A worker can't work more than 12 hours every 24 hours
    for period in range(AM_PERIODS):
        for worker in workers_data.keys():
            access_list = [period, (period + 1)  % 42, (period + 2) % 42, (period + 3) % 42, (period + 4) % 42, (period + 5) % 42]
            problem += sum(list(itemgetter(*access_list)(workers_data[worker]["worked_periods"]))) <= 3

    # Each worker must have one 48-hour break per week

    for worker in workers_data.keys():
        problem += sum(workers_data[worker]["weekend_periods"]) == 1

    # If a worker takes a 48-hour break, can't work in the inmediate 12 periods

    for period in range(AM_PERIODS):
        for worker in workers_data.keys():
            for miniperiod in range(12):
                problem += workers_data[worker]["worked_periods"][(period + miniperiod) % AM_PERIODS] <= (1 - workers_data[worker]["weekend_periods"][period])
        problem += workers_data[worker]["worked_periods"][(period + 12) % AM_PERIODS] >= workers_data[worker]["weekend_periods"][period]

    try:
        problem.solve()
    except Exception as e:
        print("Can't solve problem: {}".format(e))

    for worker in workers_data.keys():
        workers_data[worker]["schedule"] = []
        for element in range(len(workers_data[worker]["worked_periods"])):
            if workers_data[worker]["worked_periods"][element].varValue == 1:
                workers_data[worker]["schedule"].append(periods[element])

    return problem, workers_data


######################################################
if st.sidebar.button("Generate"):
        problem, workers_data = model_problem()
        f = open("./schedule.csv", "w")
        for worker in workers_data.keys():
                f.write(worker)
                for element in workers_data[worker]["schedule"]:
                        f.write(", " + element)
                f.write("\n")
        f.close()    


        shifts_to_workers = {}
        # Iterate through each worker
        for worker, data in workers_data.items():
                for shift in data['schedule']:
                        # Add the worker to the corresponding shift
                        if shift not in shifts_to_workers:
                                shifts_to_workers[shift] = []
                        shifts_to_workers[shift].append(worker)

        new = pd.DataFrame.from_dict(shifts_to_workers.items())
        new.columns = ['Shift', 'Employees On Duty']
        #cats = [ 'Mon 0-6','Mon 6-12','Mon 12-18','Mon 18-24','Tue 0-6','Tue 6-12','Tue 12-18','Tue 18-24','Wed 0-6','Wed 6-12','Wed 12-18','Wed 18-24','Thu 0-6','Thu 6-12','Thu 12-18','Thu 18-24','Fri 0-6','Fri 6-12','Fri 12-18','Fri 18-24','Sat 0-6','Sat 6-12','Sat 12-18','Sat 18-24','Sun 0-6','Sun 6-12','Sun 12-18','Sun 18-24']   
        #new = new.sort_values('Shift')
        # Print the result
        new.reset_index(drop=True, inplace=True)
        st.subheader("Fair Shift allocations for The Week")
        st.write(new)    