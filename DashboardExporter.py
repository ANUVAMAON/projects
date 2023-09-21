import pandas as pd
from sqlalchemy import create_engine, text
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import date, timedelta
from isoweek import Week
import os
import pdfkit

print('DashboardEmailter.py is running...')

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

def availability_of_CAD(df_av):
    # remove team tasks/holidays
    df_av = df_av[df_av['lastname'] != 'Jaworski']
    df_av = df_av[df_av['lastname'] != 'Møller-Jacobsen']
    df_av = df_av[df_av['lastname'] != 'Team_DK']

    Team_SK = ["Jenčár", "Ondrejka", "Pero", "Varga", "Marček"]
    Team_PL = ["Bednarczyk"]
    
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
    week_numbers = pd.to_datetime(matrix.index).strftime('%U-%Y')
    plt.subplots(figsize=(15,5))
    sns.barplot(matrix, x=week_numbers, y=-matrix['count']+CAD_Designers, color='#e14b4a', errorbar=None)# ['count', 'sum', 'avg', 'min', 'max']

    plt.title('Availability of CAD Designers')
    plt.xlabel('Week/Year')
    plt.ylabel('Availability')
    plt.tick_params(axis='x', rotation=90)
    for i in range(1,6):
        plt.axhline(y=i, color='gray', linestyle='--', linewidth=1, alpha=0.2)
    plt.savefig('CADavailability.png', dpi=600, bbox_inches='tight')

availability_of_CAD(get_data_from_sql_av())


path_wkthmltopdf = 'C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe'
config = pdfkit.configuration(wkhtmltopdf=path_wkthmltopdf)
path_to_save = 'C:\\CAD availability.pdf'
options= {
    'page-size': 'A4',
    'orientation': 'Landscape',
}
pdfkit.from_file('CADavailability.html', path_to_save, configuration=config, options=options )

os.remove('CADavailability.png')
