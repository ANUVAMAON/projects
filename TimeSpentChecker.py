'''
Pomocou SQLalchemy stahujem data z OpenProjectu, dalej ich spracujem pomocou kniznice pandas.
Skript zistuje pocet zapisanych hodin do openprojectu. Zohladnuje pracovne dni. V pripade,
ze chyba zapis v danom tyzdni, posiela email uzivatelovi.
'''


import pandas as pd
from datetime import date
import isoweek
from sqlalchemy import create_engine, text
from calendra.europe import Slovakia, Poland

start_week = isoweek.Week.thisweek().week-3
end_week = isoweek.Week.thisweek().week-1
year = date.today().year

CAD_users = {'user': [''],
             'user_name': [''],
             'email': ['']
             }

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

    # add is_working day to dataframe
    for index, row in df.iterrows():
        if row['user'] == "Bednarczyk" or row['user'] == "Jaworski":
            df.loc[index, 'is_workday'] = Poland().is_working_day(row['date'])
        else:
            df.loc[index, 'is_workday'] = Slovakia().is_working_day(row['date'])

    return df

def timespent_per_user(df):
    
    start_date = df.iloc[0]['date']
    end_date = df.iloc[-1]['date']

    work_days_sk = Slovakia().get_working_days_delta(start_date, end_date, include_start=True)
    work_days_pl = Poland().get_working_days_delta(start_date, end_date, include_start=True)

    labour_fund_sk = (work_days_sk*8)
    labour_fund_pl = (work_days_pl*8)


    sum_by_user = df.groupby('user').agg({'timespent': 'sum', 'vacation': 'sum'}).reset_index()
    # sum_by_user = pd.DataFrame(sum_by_user).reset_index()

    for index, row in sum_by_user.iterrows():
        if row['user'] == "Bednarczyk" or row['user'] == "Jaworski":
            sum_by_user.loc[index,'workdays'] = work_days_pl
            sum_by_user.loc[index,'group'] = "PL"
            sum_by_user.loc[index,'labourfund'] = labour_fund_pl
            if row['timespent'] >= labour_fund_pl:
                sum_by_user.loc[index,'absence'] = 0
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_pl
            elif row['timespent'] <= labour_fund_pl:
                sum_by_user.loc[index,'overtime'] = 0
                sum_by_user.loc[index,'absence'] = labour_fund_pl - (row['timespent'] + row['vacation']) if labour_fund_pl - (row['timespent'] + row['vacation']) > 0 else 0
                sum_by_user.loc[index,'labourfund'] = row['timespent']  
        else:
            sum_by_user.loc[index,'workdays'] = work_days_sk
            sum_by_user.loc[index,'group'] = "SK"
            sum_by_user.loc[index,'labourfund'] = labour_fund_sk
            if row['timespent'] >= labour_fund_sk:
                sum_by_user.loc[index,'absence'] = 0
                sum_by_user.loc[index,'overtime'] = row['timespent'] - labour_fund_sk
            elif row['timespent'] <= labour_fund_sk:
                sum_by_user.loc[index,'overtime'] = 0
                sum_by_user.loc[index,'absence'] = labour_fund_sk - (row['timespent'] + row['vacation']) if labour_fund_sk - (row['timespent'] + row['vacation']) > 0 else 0
                sum_by_user.loc[index,'labourfund'] = row['timespent']
    
    return sum_by_user

dfs = []
sums_by_user = []

for week_number in range(start_week, end_week+1):
    df = get_data_from_sql(week_number, week_number, year)
    dfs.append(df)
    sum_by_user = timespent_per_user(df)
    sum_by_user['email'] = sum_by_user['user'].apply(lambda x: CAD_users['email'][CAD_users['user'].index(x)])
    sum_by_user['user_name'] = sum_by_user['user'].apply(lambda x: CAD_users['user_name'][CAD_users['user'].index(x)])
    sum_by_user.name = (f'Week {week_number}')
    sums_by_user.append(sum_by_user)

def send_email(email, week, absence, user_name):

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # SMTP server configuration
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587
    smtp_username = '@gmail.com'
    smtp_password = ''

    # Sender and recipient details
    sender_email = '@gmail.com'
    sender_alias = 'OpenProject Reminder'
    recipient_email = email

    # Create a multipart message
    message = MIMEMultipart()
    message['From'] = f'{sender_alias} <{sender_email}>' #sender_email
    message['To'] = recipient_email
    message['Importance'] = 'High'
    message['Subject'] = 'Missing time in timesheets'

    # HTML body of the email
    if absence != 'whole week':
        html_content = f'''
        <html>
        <head>
            <title>Missing time in timesheets</title>
        </head>
        <body>
            <p>Hello {user_name},</p>

            <p>This is a reminder that you have missing hours in your timesheets for <strong>{week}</strong>.</p>
            <p>You have <strong>{absence}</strong> hours of absence.</p>

            <p>Please ensure that you update your timesheets accordingly.</p>

            <p>Thank you,</p>
        </body>
        </html>
        '''
    else:
        html_content = f'''
        <html>
        <head>
            <title>Missing time in timesheets</title>
        </head>
        <body>
            <p>Hello {user_name},</p>

            <p>This is a reminder that you have missing hours in your timesheets for <strong>{week}</strong>.</p>

            <p>Please ensure that you update your timesheets accordingly.</p>

            <p>Thank you,</p>
        </body>
        </html>
        '''

    # Add body to the email
    message.attach(MIMEText(html_content, 'html'))

    # Connect to the SMTP server
    smtp = smtplib.SMTP(smtp_server, smtp_port)
    smtp.starttls()  # Enable TLS encryption
    smtp.login(smtp_username, smtp_password)

    # Send the email
    smtp.send_message(message)

    # Disconnect from the SMTP server
    smtp.quit()

for sbu in sums_by_user:

    for index, row in sbu.iterrows():
        if row['absence'] > 2:
            send_email(row['email'], sbu.name, row['absence'], row['user_name'])
    
    missing_users = set(CAD_users['user']) - set(sbu.user)
    for missing_user in missing_users:
        email = CAD_users['email'][CAD_users['user'].index(missing_user)]
        user_name = CAD_users['user_name'][CAD_users['user'].index(missing_user)]
        send_email(email, sbu.name, 'whole week', user_name)
