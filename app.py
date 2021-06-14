
from flask import Flask, render_template, request, jsonify
import pandas as pd 
import numpy as np
import psycopg2
from splinter import Browser
from bs4 import BeautifulSoup as soup
from webdriver_manager.chrome import ChromeDriverManager
import time
from sqlalchemy import create_engine


# Expand cols
pd.set_option('display.max_columns', 80)
pd.options.mode.chained_assignment = None

app = Flask(__name__)

connection = psycopg2.connect(
    host = 'nba-db.cpmpsi1pfaz0.us-east-2.rds.amazonaws.com',
    port = 5432,
    user = 'postgres',
    password = 'caf3rac3',
    database='postgres'
    )
cursor=connection.cursor()

#read in data from database for All NBA table
nba_unpivoted_sql = 'SELECT * FROM public.allnba_unpivoted'
All_NBA_Unpivoted_df = pd.read_sql(nba_unpivoted_sql, con=connection).drop(['Lg'],axis=1)
#rename the players column
All_NBA_Unpivoted_df=All_NBA_Unpivoted_df.rename(columns = {'Value':'PlayerName'})
#create column with the start year
All_NBA_Unpivoted_df['Season_Start_Year'] = All_NBA_Unpivoted_df['Season'].apply(lambda row: row[0:4])
All_NBA_Unpivoted_df['Season_Start_Year'] = pd.to_numeric(All_NBA_Unpivoted_df['Season_Start_Year'])

#make dummies for position and team (1st, 2nd, 3rd)
All_NBA_Unpivoted_df = pd.get_dummies(All_NBA_Unpivoted_df,columns=['Position','Tm']).drop(['Season'],axis=1)
#rename the columns (cosmetic)
All_NBA_Unpivoted_df=All_NBA_Unpivoted_df.rename(columns = {'Position_C':'AllNBA_Center'})
All_NBA_Unpivoted_df=All_NBA_Unpivoted_df.rename(columns = {'Position_F':'AllNBA_Forward'})
All_NBA_Unpivoted_df=All_NBA_Unpivoted_df.rename(columns = {'Position_G':'AllNBA_Guard'})

#get list of all of the players that have made an all nba team
AllNBAPlayersList = All_NBA_Unpivoted_df['PlayerName'].unique()

#read in data from database for season stats table
seasons_stats_sql = 'SELECT * FROM public.seasons_stats WHERE "Year" between 1980 and 2020'
season_stats_df = pd.read_sql(seasons_stats_sql, con=connection)
#divid year into season start and end
season_stats_df=season_stats_df.rename(columns = {'Year':'Year_season_end'})
season_stats_df['Year_season_end'] = pd.to_numeric(season_stats_df['Year_season_end'])
season_stats_df['Year_season_start'] = (season_stats_df['Year_season_end'] - 1)
season_stats_df['Player'] = season_stats_df['Player'].apply(lambda row: row.replace("*",""))

# Make sure that the games played for 2021 is normalized to 82 games
# 72 games in 2021 
# 1998-1999 50 games
# 2011-2011 66 games

filename =  r'Stat_Glossary.xlsx'
stat_glossary = pd.read_excel(filename) 
scaled_stats = stat_glossary[stat_glossary.Scaled_Per_Game != 0].reset_index().drop(['index'], axis=1).Stat

def scale_stats_per_season(season_df, num_games, year):
    for stat in scaled_stats:
        season_df[stat].loc[season_df['Year_season_end']==year] = season_df[stat].loc[season_df['Year_season_end']==year] * 82/num_games
    return season_df


scale_stats_per_season(season_stats_df,50,1999)
scale_stats_per_season(season_stats_df,66,2012)
scale_stats_per_season(season_stats_df,75,2020)

# get list of every nba player
AllPlayersList = season_stats_df.Player.unique()
AllPlayersList_df = pd.DataFrame(AllPlayersList)

#check and make sure every all-nba player shows up in the season data dataset
for player in AllNBAPlayersList:
    if player not in AllPlayersList:   
        print(player)

#merge allNBA status into season stats
Season_Stats_ML_DF = pd.merge(season_stats_df,All_NBA_Unpivoted_df,how='left',left_on = ['Player','Year_season_start'], right_on = ['PlayerName','Season_Start_Year'])

# get rid of duplicate cols
Season_Stats_ML_DF = Season_Stats_ML_DF.drop(['Season_Start_Year','PlayerName'],axis=1)

# fill in zeros for players that arent all nba
Season_Stats_ML_DF['AllNBA_Center'] = Season_Stats_ML_DF['AllNBA_Center'].fillna(int(0))
Season_Stats_ML_DF['AllNBA_Forward'] = Season_Stats_ML_DF['AllNBA_Forward'].fillna(int(0))
Season_Stats_ML_DF['AllNBA_Guard'] = Season_Stats_ML_DF['AllNBA_Guard'].fillna(int(0))
Season_Stats_ML_DF['Tm_1st'] = Season_Stats_ML_DF['Tm_1st'].fillna(int(0))
Season_Stats_ML_DF['Tm_2nd'] = Season_Stats_ML_DF['Tm_2nd'].fillna(int(0))
Season_Stats_ML_DF['Tm_3rd'] = Season_Stats_ML_DF['Tm_3rd'].fillna(int(0))

#get list of positions
Positions_List = Season_Stats_ML_DF['Pos'].unique()

# create functions to determine if player is a guard forward and/or center
def is_forward(pos):
    possible_pos = [ 'SF',  'PF', 'PF-C', 'SG-SF', 'PF-SF', 'SF-SG', 'SF-PF', 'C-PF', 'SG-PF', 'C-SF', 'PG-SF']
    if pos in possible_pos: isF = 1
    else: isF = 0
    return isF

def is_guard(pos):
    possible_pos = ['PG','SG','SG-SF','PG-SG','SG-PG','SF-SG','SG-PF','PG-SF']
    if pos in possible_pos: isG = 1
    else: isG = 0
    return isG

def is_center(pos):
    possible_pos = ['C','PF-C','C-PF','C-SF']
    if pos in possible_pos: isC = 1
    else: isC = 0
    return isC

#Create dummy columns for G, F, C
Season_Stats_ML_DF['is_Guard'] = Season_Stats_ML_DF['Pos'].apply(lambda pos: is_guard(pos) )
Season_Stats_ML_DF['is_Forward'] = Season_Stats_ML_DF['Pos'].apply(lambda pos: is_forward(pos) )
Season_Stats_ML_DF['is_Center'] = Season_Stats_ML_DF['Pos'].apply(lambda pos: is_center(pos) )

#Drop the Pos Column since we have dummy columns
Season_Stats_ML_DF=Season_Stats_ML_DF.drop(['Pos'],axis=1)

# drop year  and player name
Season_Stats_ML_DF=Season_Stats_ML_DF.drop(['Year_season_end','Player'],axis=1)
Season_Stats_ML_DF=Season_Stats_ML_DF.drop(['Year_season_start'],axis=1)

#Creating Per Game Statistics
#Points per Game
Season_Stats_ML_DF["PPG"] = Season_Stats_ML_DF["PTS"]/Season_Stats_ML_DF["G"]
#Assits Per Game
Season_Stats_ML_DF["APG"] = Season_Stats_ML_DF["AST"]/Season_Stats_ML_DF["G"]
#Rebounds Per Game
Season_Stats_ML_DF["RPG"] = Season_Stats_ML_DF["TRB"]/Season_Stats_ML_DF["G"]
#Blocks Per Game
Season_Stats_ML_DF["RPG"] = Season_Stats_ML_DF["BLK"]/Season_Stats_ML_DF["G"]
#STLs Per Game
Season_Stats_ML_DF["SPG"] = Season_Stats_ML_DF["STL"]/Season_Stats_ML_DF["G"]

Season_Stats_ML_DF['3PAr'] = Season_Stats_ML_DF['3PAr'].fillna(int(0))
Season_Stats_ML_DF['3P'] = Season_Stats_ML_DF['3P'].fillna(int(0))
Season_Stats_ML_DF['3PA'] = Season_Stats_ML_DF['3PA'].fillna(int(0))
Season_Stats_ML_DF['3P_pct'] = Season_Stats_ML_DF['3P_pct'].fillna(int(0))

# Fill null values with zero
for col in list(Season_Stats_ML_DF.columns):
    Season_Stats_ML_DF[col] = Season_Stats_ML_DF[col].fillna(int(0))

# implement random oversampling
from imblearn.over_sampling import RandomOverSampler
ros = RandomOverSampler(random_state=78)

X = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Center==1]
X = X.drop(['AllNBA_Center','AllNBA_Forward','AllNBA_Guard','is_Guard','is_Center','is_Forward','WS/48','STL_pct','APG','GS'], axis=1)
X = X.drop(['Tm','Tm_1st','Tm_2nd','Tm_3rd'], axis=1)

y = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Center==1]
y = y["AllNBA_Center"].values.reshape(-1, 1)

# Splitting into Train and Test sets
# Creating StandardScaler instance
# Fitting Standard Scaller
# Scaling data

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=78)

#oversampling
X_train, y_train = ros.fit_resample(X_train, y_train)

scaler = StandardScaler()
X_scaler = scaler.fit(X_train)
X_Center_Train = X_train

X_train_scaled = X_scaler.transform(X_train)
X_test_scaled = X_scaler.transform(X_test)

from sklearn import tree
from sklearn.metrics import confusion_matrix, accuracy_score, classification_report


# Creating the decision tree classifier instance
model = tree.DecisionTreeClassifier(max_depth=20,random_state=78)

center_model = model.fit(X_train_scaled, y_train)

X = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Guard==1]
X = X.drop(['AllNBA_Center','AllNBA_Forward','AllNBA_Guard','is_Guard','is_Center','is_Forward','WS/48','STL_pct','APG','GS'], axis=1)
X = X.drop(['Tm','Tm_1st','Tm_2nd','Tm_3rd'], axis=1)

y = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Guard==1]
y = y["AllNBA_Guard"].values.reshape(-1, 1)

# Splitting into Train and Test sets
# Creating StandardScaler instance
# Fitting Standard Scaller
# Scaling data

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=78)

#oversampling
X_train, y_train = ros.fit_resample(X_train, y_train)

scaler = StandardScaler()
X_scaler = scaler.fit(X_train)
X_Guard_Train = X_train
X_train_scaled = X_scaler.transform(X_train)
X_test_scaled = X_scaler.transform(X_test)


# Creating the decision tree classifier instance
model = tree.DecisionTreeClassifier(max_depth=25, random_state=78)

guard_model = model.fit(X_train_scaled, y_train)

X = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Forward==1]
X = X.drop(['AllNBA_Center','AllNBA_Forward','AllNBA_Guard','is_Guard','is_Center','is_Forward','WS/48','STL_pct','APG','GS'], axis=1)
X = X.drop(['Tm','Tm_1st','Tm_2nd','Tm_3rd'], axis=1)

y = Season_Stats_ML_DF[Season_Stats_ML_DF.is_Forward==1]
y = y["AllNBA_Forward"].values.reshape(-1, 1)

# Splitting into Train and Test sets
# Creating StandardScaler instance
# Fitting Standard Scaller
# Scaling data

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=78)

#oversampling
X_train, y_train = ros.fit_resample(X_train, y_train)

scaler = StandardScaler()
X_scaler = scaler.fit(X_train)
X_Forward_Train = X_train
X_train_scaled = X_scaler.transform(X_train)
X_test_scaled = X_scaler.transform(X_test)


# Creating the decision tree classifier instance
model = tree.DecisionTreeClassifier(max_depth=19, random_state=78)

forward_model = model.fit(X_train_scaled, y_train)

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/form")
def form():
    return render_template('form.html')


@app.route("/model/", methods = ['POST', 'GET'])
def model():
    if request.method == 'GET':
        return f"The URL /model is accessed directly. Try going to '/form' to submit form"
    if request.method == 'POST':
        form_data = request.form
        
        input_year_dict = dict(form_data)
        input_year = input_year_dict['season']

        testing_stats_sql = f'SELECT * FROM public.seasons_stats WHERE "Year" = {input_year}'
        testing_stats = pd.read_sql(testing_stats_sql, con=connection)

        #Points per Game
        testing_stats["PPG"] = testing_stats["PTS"]/testing_stats["G"]
        #Assits Per Game
        testing_stats["APG"] = testing_stats["AST"]/testing_stats["G"]
        #Rebounds Per Game
        testing_stats["RPG"] = testing_stats["TRB"]/testing_stats["G"]
        #Blocks Per Game
        testing_stats["BPG"] = testing_stats["BLK"]/testing_stats["G"]
        #STLs Per Game
        testing_stats["SPG"] = testing_stats["STL"]/testing_stats["G"]    

        # Clean players that were on multiple teams
        traded_players = list(testing_stats[testing_stats.Tm == 'TOT'].Player)

        def was_traded(Player,traded_players):
            was_traded_num = 0 
            if Player in traded_players: was_traded_num=1
            return was_traded_num

        testing_stats['was_traded'] = testing_stats.Player.apply(lambda player: was_traded(player,traded_players) )
        testing_stats = testing_stats[(testing_stats.Tm == 'TOT') | (testing_stats.was_traded == 0)]
        testing_stats=testing_stats.drop(['was_traded'], axis=1)

        # Scale stats for shortened season
        def scale_stats(season_df, num_games):
            #scaled_season_df = pd.DataFrame()
            for stat in scaled_stats:
                season_df[stat] = season_df[stat] * 82/num_games
            return season_df

        testing_stats = scale_stats(testing_stats,72)

        centers_stats_2021 = testing_stats
        forwards_stats_2021 = testing_stats
        guards_stats_2021 = testing_stats

        centers_stats_2021['is_Center'] = centers_stats_2021['Pos'].apply(lambda pos: is_center(pos) )
        guards_stats_2021['is_Guard'] = guards_stats_2021['Pos'].apply(lambda pos: is_guard(pos) )
        forwards_stats_2021['is_Forward'] = forwards_stats_2021['Pos'].apply(lambda pos: is_forward(pos) )

        centers_stats_2021=centers_stats_2021[centers_stats_2021['is_Center']==1]
        guards_stats_2021=guards_stats_2021[guards_stats_2021['is_Guard']==1]
        forwards_stats_2021=forwards_stats_2021[forwards_stats_2021['is_Forward']==1]

        centers_stats_2021=centers_stats_2021[centers_stats_2021['is_Center']==1].reset_index()
        guards_stats_2021=guards_stats_2021[guards_stats_2021['is_Guard']==1].reset_index()
        forwards_stats_2021=forwards_stats_2021[forwards_stats_2021['is_Forward']==1].reset_index()

        #Predict All- nba Centers
        X_scaler = StandardScaler().fit(X_Center_Train)
        X_test_scaled = X_scaler.transform(centers_stats_2021[['Age','G','MP','PER','TS_pct','3PAr','FTr','ORB_pct',
                                                               'DRB_pct','TRB_pct','AST_pct','BLK_pct',
                                                               'TOV_pct','USG_pct','OWS', 'DWS','WS','OBPM',
                                                               'DBPM','BPM','VORP','FG','FGA','FG_pct','3P',
                                                               '3PA','3P_pct','2P','2PA','2P_pct','eFG_pct',
                                                               'FT','FTA','FT_pct','ORB','DRB','TRB','AST',
                                                               'STL','BLK','TOV','PF','PTS','PPG','RPG','SPG']])
        X_test_scaled = np.nan_to_num(X_test_scaled)
        predictions = center_model.predict(X_test_scaled)
        predictions_df = pd.DataFrame(predictions)
        predictions_df = predictions_df.rename(columns = {predictions_df.columns[0]:'All_NBA_Status'})
        centers_stats_2021=centers_stats_2021.join(predictions_df)
        # List All NBA team players in order of feature importance
        allnbacenter_df = centers_stats_2021[centers_stats_2021.All_NBA_Status == 1].sort_values(by=['WS','FTA','TRB','Age','RPG'],ascending=False).head(3)

        #Predict All- nba Guards
        X_scaler = StandardScaler().fit(X_Guard_Train)
        X_test_scaled = X_scaler.transform(guards_stats_2021[['Age','G','MP','PER','TS_pct','3PAr','FTr','ORB_pct',
                                                              'DRB_pct','TRB_pct','AST_pct','BLK_pct','TOV_pct','USG_pct',
                                                              'OWS', 'DWS','WS','OBPM','DBPM','BPM','VORP','FG','FGA',
                                                              'FG_pct','3P','3PA','3P_pct','2P','2PA','2P_pct','eFG_pct',
                                                              'FT','FTA','FT_pct','ORB','DRB','TRB','AST','STL','BLK',
                                                              'TOV','PF','PTS','PPG','RPG','SPG']])
        X_test_scaled = np.nan_to_num(X_test_scaled)
        predictions = guard_model.predict(X_test_scaled)
        predictions_df = pd.DataFrame(predictions)
        predictions_df = predictions_df.rename(columns = {predictions_df.columns[0]:'All_NBA_Status'})
        guards_stats_2021=guards_stats_2021.join(predictions_df)
        # List All NBA team players in order of feature importance
        allnbaguard_df=guards_stats_2021[guards_stats_2021.All_NBA_Status == 1].sort_values(by=['WS','PPG','PER','3PAr','DRB_pct','DRB','FT'],ascending=False).head(6)

        #Predict All- nba Forwards
        X_scaler = StandardScaler().fit(X_Forward_Train)
        X_test_scaled = X_scaler.transform(forwards_stats_2021[['Age','G','MP','PER','TS_pct','3PAr','FTr','ORB_pct','DRB_pct',
                                                                'TRB_pct','AST_pct','BLK_pct','TOV_pct','USG_pct','OWS', 'DWS',
                                                                'WS','OBPM','DBPM','BPM','VORP','FG','FGA','FG_pct','3P','3PA',
                                                                '3P_pct','2P','2PA','2P_pct','eFG_pct','FT','FTA','FT_pct','ORB',
                                                                'DRB','TRB','AST','STL','BLK','TOV','PF','PTS','PPG','RPG','SPG']])
        X_test_scaled = np.nan_to_num(X_test_scaled)
        predictions = forward_model.predict(X_test_scaled)
        predictions_df = pd.DataFrame(predictions)
        predictions_df = predictions_df.rename(columns = {predictions_df.columns[0]:'All_NBA_Status'})
        forwards_stats_2021=forwards_stats_2021.join(predictions_df)
        # List All NBA team players in order of feature importance
        allnbaforward_df=forwards_stats_2021[forwards_stats_2021.All_NBA_Status == 1].sort_values(by=['PPG','VORP','WS','PER','TRB_pct','FTr','DWS'],ascending=False).head(6)

        # fix the all nba column to only include top 6 (or 3 for centers) choices
        allnba_list=list(allnbacenter_df.Player)+ list(allnbaforward_df.Player)+ list(allnbaguard_df.Player)

        def all_nba_final(player,playerlist):
            allnba = 0
            if player in playerlist: allnba=1
            return allnba

        
        forwards_stats_2021.All_NBA_Status = forwards_stats_2021.Player.apply(lambda player: all_nba_final(player,allnba_list) )
        guards_stats_2021.All_NBA_Status = guards_stats_2021.Player.apply(lambda player: all_nba_final(player,allnba_list) )
        centers_stats_2021.All_NBA_Status = centers_stats_2021.Player.apply(lambda player: all_nba_final(player,allnba_list) )
        centers_stats_2021[centers_stats_2021.All_NBA_Status==1]

        allNBAteam = allnbacenter_df.append(allnbaforward_df).append(allnbaguard_df).drop(columns=['index','is_Center','is_Guard','is_Forward','All_NBA_Status'])



        return render_template('model.html', tables=[allNBAteam.to_html()], titles=allNBAteam.columns.values)
        

@app.route("/new_season")
def new_season():
    return render_template('new_season.html')

@app.route("/upload/", methods = ['POST', 'GET'])
def upload():
    if request.method == 'GET':
        return f"The URL /upload is accessed directly. Try going to '/new_season' to submit form"
    if request.method == 'POST':
        form_data = request.form
        
        input_year_dict = dict(form_data)
        input_year = input_year_dict['season']
        verify_sql = f'SELECT 1 AS year_exist FROM public.seasons_stats WHERE "Year" = {input_year} group by 1;'
        verifing_year = pd.read_sql(verify_sql, con=connection)

        if not verifing_year.empty:
            upload_output = f'The {input_year} season is already in the database.'
            return render_template('upload.html', upload_output=upload_output)
        else:
            executable_path = {'executable_path': ChromeDriverManager().install()}
            browser = Browser('chrome', **executable_path, headless=False)

            
            # Pick stat year to pull
            year = input_year
            
            # Visit the basketball-reference site
            url = f'https://www.basketball-reference.com/leagues/NBA_{year}_totals.html'
            browser.visit(url)

            
            html = browser.html
            totals_soup = soup(html, 'html.parser')
            totals_div = totals_soup.find('div', attrs={'id':'div_totals_stats'})
            totals_table = totals_div.find('table', attrs={'id':'totals_stats'})
            totals_body = totals_table.find('tbody')
            totals_rows = totals_body.find_all('tr')

            
            totals_df = pd.DataFrame()
            player_stats = pd.DataFrame()

            
            # Find all rows
            for row in totals_rows:
                totals_row = row
                totals_elem = totals_row.find_all('td')

                # Iterate through each stat in row
                for stat in totals_elem:
                    stat_feature = stat['data-stat']
                    stat_value = stat.get_text()
                    player_stats[stat_feature] = [stat_value]

                # Add each player stat to totals dataframe
                totals_df = totals_df.append(player_stats, ignore_index=True)
            
            totals_df.drop_duplicates(inplace=True)

            
            url = f'https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html'
            browser.visit(url)

            
            html = browser.html
            advanced_soup = soup(html, 'html.parser')
            advanced_div = advanced_soup.find('div', attrs={'id':'div_advanced_stats'})
            advanced_table = advanced_div.find('table', attrs={'id':'advanced_stats'})
            advanced_body = advanced_table.find('tbody')
            advanced_rows = advanced_body.find_all('tr')

            
            advanced_df = pd.DataFrame()
            advanced_stats = pd.DataFrame()

            
            # Find all rows
            for row in advanced_rows:
                advanced_row = row
                advanced_elem = advanced_row.find_all('td')

                # Iterate through each stat in row
                for stat in advanced_elem:
                    stat_feature = stat['data-stat']
                    stat_value = stat.get_text()
                    advanced_stats[stat_feature] = [stat_value]

                # Add each player stat to advanced dataframe
                advanced_df = advanced_df.append(advanced_stats, ignore_index=True)

            
            advanced_df.drop_duplicates(inplace=True)

            
            browser.quit()

            # %%
            # Merge both totals and advanced stats into one dataframe
            full_stat_df = totals_df.merge(advanced_df, how='left', left_index=True, right_index=True)

            # %%
            # Preprocessing for database load
            full_stat_df.drop(['player_y', 'pos_y', 'age_y', 'team_id_y','g_y', 'mp_y','DUMMY'], axis=1, inplace=True)
            full_stat_df.rename(columns={'player_x':'Player', 'pos_x':'Pos', 'age_x':'Age', 'team_id_x':'Tm', 'g_x':'G', 'gs':'GS', 'mp_x':'MP', 
                'fg':'FG', 'fga':'FGA', 'fg_pct':'FG_pct', 'fg3':'3P', 'fg3a':'3PA', 'fg3_pct':'3P_pct', 'fg2':'2P', 'fg2a':'2PA', 'fg2_pct':'2P_pct',
                'efg_pct':'eFG_pct', 'ft':'FT', 'fta':'FTA', 'ft_pct':'FT_pct', 'orb':'ORB', 'drb':'DRB', 'trb':'TRB', 'ast':'AST', 'stl':'STL',
                'blk':'BLK', 'tov':'TOV', 'pf':'PF', 'pts':'PTS', 'per':'PER', 'ts_pct':'TS_pct', 'fg3a_per_fga_pct':'3PAr', 'fta_per_fga_pct':'FTr',
                'orb_pct':'ORB_pct', 'drb_pct':'DRB_pct', 'trb_pct':'TRB_pct', 'ast_pct':'AST_pct', 'stl_pct':'STL_pct', 'blk_pct':'BLK_pct',
                'tov_pct':'TOV_pct', 'usg_pct':'USG_pct', 'ows':'OWS', 'dws':'DWS', 'ws':'WS', 'ws_per_48':'WS/48', 'obpm':'OBPM',
                'dbpm':'DBPM', 'bpm':'BPM', 'vorp':'VORP'}, inplace=True)
            full_stat_df['Year'] = year
            full_stat_df = full_stat_df[['Year', 'Player', 'Pos', 'Age', 'Tm', 'G', 'GS', 'MP', 'PER', 'TS_pct', '3PAr', 'FTr', 
                'ORB_pct', 'DRB_pct', 'TRB_pct', 'AST_pct', 'STL_pct', 'BLK_pct', 'TOV_pct', 'USG_pct', 'OWS', 'DWS', 'WS', 'WS/48', 
                'OBPM', 'DBPM', 'BPM', 'VORP', 'FG', 'FGA', 'FG_pct', '3P', '3PA', '3P_pct', '2P', '2PA', '2P_pct', 'eFG_pct', 'FT', 
                'FTA', 'FT_pct', 'ORB', 'DRB', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 'PTS']]

            num_cols = ['G', 'GS', 'MP', 'PER', 'TS_pct',
                '3PAr', 'FTr', 'ORB_pct', 'DRB_pct', 'TRB_pct', 'AST_pct', 'STL_pct',
                'BLK_pct', 'TOV_pct', 'USG_pct', 'OWS', 'DWS', 'WS', 'WS/48', 'OBPM',
                'DBPM', 'BPM', 'VORP', 'FG', 'FGA', 'FG_pct', '3P', '3PA', '3P_pct',
                '2P', '2PA', '2P_pct', 'eFG_pct', 'FT', 'FTA', 'FT_pct', 'ORB', 'DRB',
                'TRB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 'PTS']

            for col in num_cols:
                full_stat_df[col] = pd.to_numeric(full_stat_df[col])


            conn_string = 'postgres://postgres:caf3rac3@nba-db.cpmpsi1pfaz0.us-east-2.rds.amazonaws.com/postgres'
            db = create_engine(conn_string)
            conn = db.connect()

            
            start_time = time.time()
            full_stat_df.to_sql('seasons_stats', con=conn, if_exists='append', index=False)
            upload_output = "Upload sucessful. Duration: {} seconds".format(time.time() - start_time)
            return render_template('upload.html', upload_output=upload_output)
    
@app.route("/analysis")
def analysis():
    return render_template('analysis.html')

if __name__ == "__main__":
    app.run()