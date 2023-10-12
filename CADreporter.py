'''
Pomocou SQLalchemy stahujem data z OpenProjectu, dalej ich spracujem pomocou kniznice pandas. Vysledok zobrazijem cez webovu kniznicu Streamlit.
Aplikacia zistuje vytazenost CAD konstrukterov na rok dopredu.
Tiez monitoruje zazaznamenane hodiny na projektoch a triedi ich podla vykonanych uloh.
'''



import pandas as pd
from sqlalchemy import create_engine, text
from calendra.europe import Slovakia, Poland
import streamlit as st #pip install streamlit
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from isoweek import Week
import numpy as np


#----------------SQL-----------------------

def get_data_from_sql(start_week, end_week, year): 
 
    engine = create_engine('postgresql+psycopg2://addresstoopenprojectsql:5432/openproject')

    with engine.connect() as connection:

        query = text(f"""
        SELECT te.tweek as week, te.tmonth as month, te.tyear as year, us.lastname as user, te.spent_on as date, te.hours as timespent, wp.subject, tp.name as type
        FROM users us
        JOIN time_entries te on te.user_id = us.id
        JOIN work_packages wp on wp.id = te.work_package_id
        JOIN types tp on tp.id = wp.type_id
        WHERE te.tweek >= {start_week} AND te.tweek <= {end_week} AND te.tyear = {year}
        ORDER BY te.spent_on ASC
        """)

        with engine.begin() as conn:
            df = pd.read_sql(query, engine)

    for index, row in df.iterrows():
        if row['subject'] == "Not planned revisions":
            df.at[index, 'type'] = 'Not planned revision'

    for index, row in df.iterrows():
        if row['type'] == 'day-off':
            df.loc[index, 'vacation'] = df.loc[index, 'timespent']
            df.at[index, 'timespent'] = 0
        elif row['type'] != 'day-off':
            df.loc[index, 'vacation'] = 0
        
    for index, row in df.iterrows():
        if row['type'] == 'bank holiday':
            df.loc[index, 'vacation'] = 0
            df.at[index, 'timespent'] = 0

    # add is_working day to dataframe
    for index, row in df.iterrows():
        if row['user'] == "User1" or row['user'] == "User2":
            df.loc[index, 'is_workday'] = Poland().is_working_day(row['date'])
        else:
            df.loc[index, 'is_workday'] = Slovakia().is_working_day(row['date'])

    return df


def get_data_from_sql_av(): 
 
    start_date = date.today()-timedelta(days=30)
    start_date.strftime("%Y-%m-%d")
    
    engine = create_engine('postgresql+psycopg2://addresstoopenprojectsql:5432/openproject')

    with engine.connect() as connection:

        query_av = text(f"""
        SELECT wp.start_date, wp.due_date, wp.duration, us.lastname
        FROM work_packages wp
        JOIN users us ON us.id = wp.assigned_to_id
        WHERE wp.start_date >= '{start_date}'
        ORDER BY start_date ASC                      
        """)

        with engine.begin() as conn:
            df_av = pd.read_sql(query_av, engine)

    return df_av

def timespent_by_type(df):
    df = df[~((df['type'] == 'day-off') | (df['type'] == 'bank holiday'))]
    type_timespent = df.groupby('type')['timespent'].agg(timespent='sum')
    type_timespent = pd.DataFrame(type_timespent).reset_index()
    # Výpočet percentuálnych hodnôt pre každý typ
    total_timespent = type_timespent['timespent'].sum()
    type_timespent['percent'] = type_timespent['timespent'] / total_timespent * 100

    # Vytvorenie histogramu pomocou knižnice Plotly
    fig = px.bar(type_timespent, x='type', y='timespent', color='type', width=1200, height=500,
                    title="Spent time per task type",
                    labels={"timespent": "Spent time", "type": "Type", "user": "CAD Designer"},
                    text=type_timespent[['timespent', 'percent']].apply(lambda x: f'{x["timespent"]}h<br>{x["percent"]:.2f}%', axis=1))
    return fig, type_timespent

def timespent_per_user(df):

    start_date = df.iloc[0]['date']
    end_date = df.iloc[-1]['date']

    work_days_sk = Slovakia().get_working_days_delta(start_date, end_date, include_start=True)
    work_days_pl = Poland().get_working_days_delta(start_date, end_date, include_start=True)

    labour_fund_sk = (work_days_sk*8)
    labour_fund_pl = (work_days_pl*8)

    sum_by_user = df.groupby('user').agg({'timespent': 'sum', 'vacation': 'sum'}).reset_index()

    for index, row in sum_by_user.iterrows():
        if row['user'] == "User1" or row['user'] == "User2":
            sum_by_user.loc[index,'workdays'] = work_days_pl
            sum_by_user.loc[index,'group'] = "PL"
            sum_by_user.loc[index,'manhours'] = row['timespent']
            sum_by_user.loc[index,'labourfund'] = labour_fund_pl - row['vacation']
            sum_by_user.loc[index,'absence'] = 0
            sum_by_user.loc[index,'overtime'] = 0
            if row['timespent'] > labour_fund_pl:
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_pl + row['vacation']
            elif row['timespent'] <= labour_fund_pl:
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_pl + row['vacation'] if row['timespent'] - labour_fund_pl + row['vacation'] > 0 else 0
                sum_by_user.loc[index,'absence'] = labour_fund_pl - (row['timespent'] + row['vacation']) if labour_fund_pl - (row['timespent'] + row['vacation']) > 0 else 0
        else:
            sum_by_user.loc[index,'workdays'] = work_days_sk
            sum_by_user.loc[index,'group'] = "SK"
            sum_by_user.loc[index,'manhours'] = row['timespent']
            sum_by_user.loc[index,'labourfund'] = labour_fund_sk - row['vacation']
            sum_by_user.loc[index,'absence'] = 0
            sum_by_user.loc[index,'overtime'] = 0
            if row['timespent'] > labour_fund_sk:
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_sk + row['vacation']
            elif row['timespent'] <= labour_fund_sk:
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_sk + row['vacation'] if row['timespent'] - labour_fund_sk + row['vacation'] > 0 else 0
                sum_by_user.loc[index,'absence'] = labour_fund_sk - (row['timespent'] + row['vacation']) if labour_fund_sk - (row['timespent'] + row['vacation']) > 0 else 0
    
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=sum_by_user['user'],
            y=sum_by_user['labourfund'] - sum_by_user['absence'],
            name='Labour fund',
            # marker_color='#4a0eff',
            text=sum_by_user['labourfund'] - sum_by_user['absence'],
            textposition='auto',
            hovertemplate='User: %{x}<br>Labour fund: %{y}'
            ))
        fig.add_trace(go.Bar(
            x=sum_by_user['user'],
            y=sum_by_user['absence'],
            name='Absence',
            # marker_color='#ff0e0e',
            text=sum_by_user['absence'],
            textposition='auto',
            hovertemplate='User: %{x}<br>Absence: %{y}'
            ))
        fig.add_trace(go.Bar(
            x=sum_by_user['user'],
            y=sum_by_user['overtime'],
            name='Overtime',
            # marker_color='#0eff8f',
            text=sum_by_user['overtime'],
            textposition='auto',
            hovertemplate='User: %{x}<br>Overtime: %{y}'
            ))
        
        fig.update_layout(
            barmode='stack',
            title=f"Labour fund SK: {labour_fund_sk} / Labour fund PL: {labour_fund_pl}<br>From {start_date} to {end_date}",
            width=1200,
            height=500,
            xaxis_title="CAD Designers",
            yaxis_title="Labour fund | Absence |Overtime",
            )

        # fig = px.bar(sum_by_user, x='user', y=['labourfund','absence','overtime'], width=1200, height=500,text_auto=True, title=f"Labour fund SK: {labour_fund_sk} / Labour fund PL: {labour_fund_pl}<br>From {start_date} to {end_date}", labels={
        #     "user": "CAD Designers",
        #     "value": "Labour fund | Absence |Overtime"
        #     })
        # fig.update_traces(hovertemplate='User: %{x}<br>Labour fund: %{y[0]}<br>absence: %{y[1]}<br>Overtime: %{y[2]}')
    
    return fig, sum_by_user

def availability_of_CAD(df_av):
    # remove team tasks/holidays
    df_av = df_av[df_av['lastname'] != 'User2']
    df_av = df_av[df_av['lastname'] != 'Møller-Jacobsen']
    df_av = df_av[df_av['lastname'] != 'Team_DK']

    Team_SK = ["Jenčár", "Ondrejka", "Pero", "Varga", "Marček"]
    Team_PL = ["User1"]
    
    if 'Team_SK' in df_av['lastname'].values:
        # Find Team_SK row and copy it
        team_row = df_av[df_av['lastname'] == 'Team_SK']
        # Remove Team_SK row
        df_av = df_av[df_av['lastname'] != 'Team_SK']
        # Append Team_SK members to df_av
        new_rows = [team_row.assign(lastname=name) for name in Team_SK]
        df_av = df_av.append(new_rows, ignore_index=True)
    
    if 'Team_PL' in df_av['lastname'].values:
        # Find Team_PL row and copy it
        team_row = df_av[df_av['lastname'] == 'Team_PL']
        # Remove Team_PL row
        df_av = df_av[df_av['lastname'] != 'Team_PL']
        # Append Team_PL members to df_av
        new_rows = [team_row.assign(lastname=name) for name in Team_PL]
        df_av = df_av.append(new_rows, ignore_index=True)

    CAD_Designers = df_av['lastname'].nunique() + 0.01 # CAD Designers + 1% to avoid 0% availability
    days_to_next_week = (7 - df_av['start_date'].min().weekday())%7
    start_date = df_av['start_date'].min()+timedelta(days=30+days_to_next_week)
    due_date = df_av['due_date'].max()
    calendar = pd.date_range(start=start_date, end=due_date, freq='D')

    matrix = pd.DataFrame(index=calendar, columns=['count'])
    matrix['count'] = 0

    for _, row in df_av.iterrows():
        start = row['start_date'] - pd.DateOffset(days=1) # safety gap -1 day
        due = row['due_date'] + pd.DateOffset(days=1) # safety gap +1 day
        lastname = row['lastname']
        matrix.loc[start:due, lastname] = True

    matrix['count'] = matrix.iloc[:,1:].sum(axis=1)
    print(matrix)
    week_numbers = pd.to_datetime(matrix.index).strftime('%U-%Y')
 
    fig = px.histogram(matrix, x=week_numbers, y=-matrix['count']+CAD_Designers,text_auto=False, width=2000, height=600, histfunc='avg')# ['count', 'sum', 'avg', 'min', 'max']
    fig.update_traces(marker_color='#e14b4a')
    fig.update_layout(yaxis_title = "Availability", xaxis_title = "Week/Year")

    return fig


#----------------STREAMLIT-----------------
#----------------SETTINGS------------------
page_title = "Construction Dep. Dashboard"
page_icon = "📊"
layout = "wide"
#-------------------------------------------

st.set_page_config(page_title=page_title,page_icon=page_icon, layout=layout)
st.title(page_title + " " + page_icon)

start_week = Week.thisweek().week - 2
end_week = Week.thisweek().week
years = [date.today().year, date.today().year+1]

df_av = get_data_from_sql_av()
st.subheader("Availability of CAD Designers")
st.plotly_chart(availability_of_CAD(df_av), use_container_width=True)

with st.form("entry_form", clear_on_submit=False):
    
    st.subheader("Timespent by type and user")
    col1, col2 = st.columns(2)
    col1.slider('Select a range of weeks', 1, end_week, value=(start_week, end_week), key="weeks")
    col2.selectbox("Select Year:", years, key="year")
    "---"
    submitted = st.form_submit_button("Load data")
    if submitted:
        df = get_data_from_sql(st.session_state['weeks'][0], st.session_state['weeks'][1], st.session_state['year'])
        col1, col2 = st.columns(2)
        col1.plotly_chart(timespent_by_type(df)[0], use_container_width=True)
        col2.dataframe(timespent_by_type(df)[1])
        col3, col4 = st.columns(2)
        col3.plotly_chart(timespent_per_user(df)[0], use_container_width=True)
        col4.dataframe(timespent_per_user(df)[1])
        
