# %%
# Import Splinter and BeautifulSoup
from splinter import Browser
from bs4 import BeautifulSoup as soup
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
#%%
executable_path = {'executable_path': ChromeDriverManager().install()}
browser = Browser('chrome', **executable_path, headless=False)

#%%
# Pick stat year to pull
year = '2021'
#%%
# Visit the basketball-reference site
url = f'https://www.basketball-reference.com/leagues/NBA_{year}_totals.html'
browser.visit(url)

#%%
html = browser.html
totals_soup = soup(html, 'html.parser')
totals_div = totals_soup.find('div', attrs={'id':'div_totals_stats'})
totals_table = totals_div.find('table', attrs={'id':'totals_stats'})
totals_body = totals_table.find('tbody')
totals_rows = totals_body.find_all('tr')

#%%
totals_df = pd.DataFrame()
player_stats = pd.DataFrame()

#%%
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
#%%
totals_df.drop_duplicates(inplace=True)

#%%
url = f'https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html'
browser.visit(url)

#%%
html = browser.html
advanced_soup = soup(html, 'html.parser')
advanced_div = advanced_soup.find('div', attrs={'id':'div_advanced_stats'})
advanced_table = advanced_div.find('table', attrs={'id':'advanced_stats'})
advanced_body = advanced_table.find('tbody')
advanced_rows = advanced_body.find_all('tr')

#%%
advanced_df = pd.DataFrame()
advanced_stats = pd.DataFrame()

#%%
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

#%%
advanced_df.drop_duplicates(inplace=True)

#%%
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

# %%
# Database upload
import time
import pandas as pd
from sqlalchemy import create_engine
import psycopg2

conn_string = 'postgres://postgres:caf3rac3@nba-db.cpmpsi1pfaz0.us-east-2.rds.amazonaws.com/postgres'
db = create_engine(conn_string)
conn = db.connect()

#%%
start_time = time.time()
full_stat_df.to_sql('testing_stats', con=conn, if_exists='replace', index=False)
print("Upload duration: {} seconds".format(time.time() - start_time))
# %%
