# importing the requests library
import requests
import json
import time
from datetime import datetime, timezone
from dateutil import relativedelta, parser
import argparse
import os
from enum import Enum
  
# api-endpoint
URL = "https://ballchasing.com/api/replays/"
PING = "https://ballchasing.com/api"
# location given here
apiKey = os.getenv("BALLCHASING_API_KEY")

with open('data/players.json') as f:
    PLAYERS = json.load(f)

# defining a params dict for the parameters to be sent to the API
KEY = {'Authorization': apiKey} #

class TeamColor(Enum):
    BLUE = 0
    ORANGE = 1
    NEITHER = 2

def get_player_id(name):
    for player in PLAYERS['data']:
        if player['name'] == name:
            return str(player['platform']+':'+str(player['id']))
    print(f'ERROR: Player "{name}" not found')
    return None

def grabGames(args):
    PARAMS = {'player-id':get_player_id(args.player1)}

    if args.type == '1':
        PARAMS['playlist'] = 'ranked-duels'
    elif args.type == '2':
        PARAMS['playlist'] = 'ranked-doubles'
    elif args.type == '3':
        PARAMS['playlist'] = 'ranked-standard'
    elif args.type == 'p':
        PARAMS['playlist'] = 'private'
    #elif args.type == 'all':
        #do nothing

    if args.date:
        PARAMS['replay-date-after'] = args.date
    
    dataLeft = True
    games = []

    numRequests = 0
    nextURL = URL
    nextPARAMS = PARAMS
    numGames = 0
    while dataLeft:
        try:
            # sending get request and saving the response as response object
            r = requests.get(url = nextURL, headers = KEY, params = nextPARAMS)
            numRequests = numRequests + 1

            # extracting data in json format
            data = r.json()

            if 'count' in data.keys():
                numGames = numGames + len(data['list'])

                print(str(numRequests) + ': Requested ' + str(numGames) + '/' + str(data['count']) + ' games')

            games = games + data['list']

            if "next" in data.keys():
                nextURL = data['next']
                # nextPARAMS = []
            else:
                dataLeft = False
        except:
            print("REQUEST ERROR: ", end="")
            print(r)
            dataLeft = False
        # dataLeft = False ## DEBUG - TURN THIS OFF THIS FORCES A LACK OF REPLAYS
    
    return games

def hasPlayer(replay, name):
    try:
        playerId = nameToId(name)

        ids = [player['id']['id'] for player in replay['blue']['players']] + [player['id']['id']  for player in replay['orange']['players']]
        if playerId in ids:
            return True
        return False
    except:
        return False
    
def getPlayerTeam(replay, name):
    try:
        playerId = nameToId(name)

        blue_ids = [player['id']['id'] for player in replay['blue']['players']]
        orange_ids = [player['id']['id']  for player in replay['orange']['players']]
        if playerId in blue_ids:
            return TeamColor.BLUE
        if playerId in orange_ids:
            return TeamColor.ORANGE
        
        return TeamColor.NEITHER
    except:
        return TeamColor.NEITHER
    
def getWinner(replay):
    try:
        blueGoals = replay['blue']['goals']
    except:
        blueGoals = '0'

    try:
        orangeGoals = replay['orange']['goals']
    except:
        orangeGoals = '0'

    if int(blueGoals) > int(orangeGoals):
        return TeamColor.BLUE
    
    if int(blueGoals) < int(orangeGoals):
        return TeamColor.ORANGE
    
    return TeamColor.NEITHER

def countNotables(replay):
    count = 0
    for player in PLAYERS['data']:
        if hasPlayer(replay,player['name']):
            count += 1
    return count

def isGameType(replay, gameType):
    try:
        if gameType == '1':
            gameType = 'ranked-duels'
        elif gameType == '2':
            gameType = 'ranked-doubles'
        elif gameType == '3':
            gameType = 'ranked-standard'
        elif gameType == 'p':
            gameType = 'private'

        return replay['playlist_id'] == gameType
    except:
        return False

def nameToId(name):
    for player in PLAYERS['data']:
        if player['name'] == name:
            return str(player['id'])
    print(f'ERROR: Player "{name}" not found')
    return None

def filterGames(args,games):
    filteredGames = []
    past = None

    if args.date:
        today = datetime.now(timezone.utc)
        past = today - relativedelta.relativedelta(months=args.date)
        # PARAMS['replay-date-after'] = d2.isoformat('T')

    for replay in games:
        if past:
            if past > datetime.strptime(replay['date'],"%Y-%m-%dT%H:%M:%S%z"):
                continue

        # Filter by game type
        if args.type:
            if not isGameType(replay, args.type):
                continue

        if args.remove_priv:
            if isGameType(replay,'p'):
                continue

        # Filter by player1
        if args.player1:
            if not hasPlayer(replay, args.player1):
                continue

        # Filter by player2
        if args.player2:
            if not hasPlayer(replay, args.player2):
                continue
        
        if args.stacked_lobby:
            if countNotables(replay) < int(args.stacked_lobby):
                continue

        # This replay passed the filters
        filteredGames.append(replay)

    return filteredGames

def refreshPlayer():
    database = {}

    print("Loading Current Database...")
    with open("data/database.json", 'r') as file:
        database = json.load(file)

    if not args.player1:
        print("Enter the player to refresh using -p1")
        return
    # for player in PLAYERS['data']:
    # #grab replays
    # args.player1 = player['name']
    replays = grabGames(args)

    # For replay type
    for replay in replays:
        if replay['id'] not in database:
            # add replay to database
            database[replay['id']] = replay
    
    with open("data/database.json","w") as outfile:
        print("Writing Database....")
        json.dump(database, outfile)

def buildDatabase():
    print("Build Database")

    database = {}

    print("Loading Current Database...")
    with open("data/database.json", 'r') as file:
        database = json.load(file)

    largest = max(database.values(), key=lambda x: datetime.strptime(x['date'],"%Y-%m-%dT%H:%M:%S%z").timestamp())

    d = datetime.strptime(largest['date'],"%Y-%m-%dT%H:%M:%S%z")
    d2 = d - relativedelta.relativedelta(days=1)
    args.date = d2.isoformat('T')

    # playlists = ['1','2']
    # # For Game Type
    # for playlist in playlists:
    #     args.type = playlist
    for player in PLAYERS['data']:
        #grab replays
        args.player1 = player['name']
        # print(args.player1 + ' ' + args.type + 's')
        print(args.player1 + '...')
        replays = grabGames(args)
        # For replay type
        for replay in replays:
            if replay['id'] not in database:
                # add replay to database
                database[replay['id']] = replay

    with open("data/database.json","w") as outfile:
        print("Writing Database....")
        json.dump(database, outfile)

parser = argparse.ArgumentParser(
                    prog = 'ProgramName',
                    description = 'What the program does',
                    epilog = 'Text at the bottom of help')

parser.add_argument('-p1','--player1', default=None)
parser.add_argument('-p2','--player2', default=None)
parser.add_argument('-qt','--qualityTeammate', action="store_true")
parser.add_argument('-d','--date',type=int, default=None)
parser.add_argument('-op','--opponent', action="store_true")
parser.add_argument('-s','--sort',default=None)
parser.add_argument('-t','--type',default=None) # 1,2,3,P,ALL
parser.add_argument('-b','--buildDatabase',action="store_true")
parser.add_argument('-r','--refreshPlayer',action="store_true")
parser.add_argument('-p','--ping',action="store_true")
parser.add_argument('-sl','--stacked_lobby',default=None)
parser.add_argument('--remove_priv',action="store_true")


def main(args):

    ####################
    # Grab the games
    ####################
    #games = grabGames(args)
    print("Opening Database...")
    with open("data/database.json", 'r') as file:
        database = json.load(file)
    games = list(database.values())
    games.sort(key=lambda x: x['date'])

    ####################
    # Filter the games
    ####################
    print("Filtering games...")
    filteredGames = filterGames(args,games)

    ####################
    # Sort the games
    ####################
    print("Sorting games...")
    if args.sort != None:
        if(args.sort == 'score'):
            for game in filteredGames:
                game['sort'] = '-1'
                #Find the player score
                try:
                    for player in (game['blue']['players'] + game['orange']['players']):
                        if(player['id']['id'] == nameToId(args.player1)):
                            #Add it to high level data
                            game['sort'] = player['score']
                            break
                except:
                    print('buggy replay')
                
                if(game['sort'] == '-1'):
                    print('FAILURE')

        if(args.sort == 'thousand'):
            finalGames = []
            for game in filteredGames:
                game['sort'] = '-1'
                for notable in PLAYERS['data']:
                
                    #Find the player score
                    for player in (game['blue']['players'] + game['orange']['players']):
                        player_id_info = player.get('id', {})
                        if player_id_info.get('id') == str(notable['id']):
                            try:
                                score = int(player.get('score', -1))
                                sort_val = int(game.get('sort', -1))
                                if score > 1000 and sort_val < score:
                                    game['sort'] = str(score)
                            except (ValueError, TypeError):
                                print("Invalid score format in replay")

                    # if(game['sort'] == '-1'):
                    #     print('FAILURE')
                if game['sort'] != '-1':
                    finalGames.append(game)
            filteredGames = finalGames
        if args.sort == 'spm':
            for game in filteredGames:
                game['sort'] = '-1'
                for notable in PLAYERS['data']:
                    try:
                        # Combine players from both teams, defaulting to empty lists if any keys are missing
                        blue_players = game.get('blue', {}).get('players', [])
                        orange_players = game.get('orange', {}).get('players', [])
                        all_players = blue_players + orange_players

                        # Find the notable player in the game
                        for player in all_players:
                            player_id_info = player.get('id', {})
                            if player_id_info.get('id') == str(notable['id']):
                                score = int(player.get('score', -1))
                                duration = game.get('duration', 10000)
                                spm = score / (duration / 60)

                                current_sort = float(game.get('sort', -1))
                                if current_sort < spm:
                                    game['sort'] = str(int(spm)).zfill(5)
                    except Exception as e:
                        print(f"Error processing game {game.get('id', 'unknown')} for notable {notable.get('name', 'unknown')}: {e}")


                    # if(game['sort'] == '-1'):
                    #     print('FAILURE')

        if(args.sort == 'avg_speed') or (args.sort == 'car'):
            numRequests = 0
            numGames = len(filteredGames)
            for game in filteredGames:
                game['sort'] = '-1'
                url = URL + game['id']
                numRequests = numRequests + 1
                print('{}/{}-Requesting Details...'.format(str(numRequests),numGames))
                try:
                    r = requests.get(url = url, headers = KEY)
                    data = r.json()
                    try:
                        for player in (data['blue']['players'] + data['orange']['players']):
                            if(player['id']['id'] == nameToId(args.player1)):
                                #Add it to high level data
                                if(args.sort == 'avg_speed'):
                                    game['sort'] = player['stats']['movement']['avg_speed']
                                if(args.sort == 'car'):
                                    game['sort'] = player['car_name']
                                break
                    except:
                        print('buggy replay')
                except:
                    print("REQUEST ERROR: ", end="")
                    print(r)
                if(game['sort'] == '-1'):
                    print('FAILURE')

        #sort
        filteredGames.sort(key=lambda x: x['sort'])


    ####################
    # Print the games
    ####################
    for game in filteredGames:
        now = datetime.now(timezone.utc)
        name_elements = [args.player1, args.player2, str(args.type), args.sort, str(args.date), now.strftime('%Y_%m_%d')]
        filename = '-'.join(e for e in name_elements if e) +'.txt'

        complete_output = []

        try:
            overtime = ''
            if game['overtime'] == True:
                overtime = '(ot '+ str(game['duration']/60)[:3] +')'
            
            blueNames = ''
            orangeNames = ''

            blueGoals = str(game.get('blue', {}).get('goals', 0))
            orangeGoals = str(game.get('orange', {}).get('goals', 0))

            winloss = ''
            if args.player1:
                if getPlayerTeam(game,args.player1) == getWinner(game):
                    winloss = 'WIN'
                else:
                    winloss = 'LOSS'
                    
            for player in game.get('blue', {}).get('players', []):
                blueNames += player['name'][:12].ljust(12)

            for player in game.get('orange', {}).get('players', []):
                orangeNames += player['name'][:12].ljust(12)

            gameType = ''
            if game['playlist_id'] == 'ranked-duels':
                gameType = '1v1'
            if game['playlist_id'] == 'ranked-doubles':
                gameType = '2v2'
            if game['playlist_id'] == 'ranked-standard':
                gameType = '3v3'
            if game['playlist_id'] == 'private':
                gameType = 'pri'
            
            if args.sort == None:
                game['sort'] = ''

            formatted_string = f"{str(game['sort']).ljust(5)}{overtime.ljust(9)}- ({gameType}) {winloss.ljust(4)} {blueGoals.rjust(2)}-{orangeGoals.ljust(2)} - {game['date'][:10]}: {blueNames} vs   {orangeNames}| ballchasing.com/replay/{game['id']}"
            print(formatted_string)
            complete_output.append(formatted_string + '\n')
            
        except:
            print('buggy game')
            complete_output.append('buggy game\n')


        with open(os.path.join('output', filename),'a') as file:
            file.writelines(complete_output)

        #TODO: 

def ping():
    r = requests.get(url = PING, headers = KEY)
    # extracting data in json format
    data = r.json()
    print(r)
    return 

if __name__ == '__main__':
    
    args = parser.parse_args()

    if(args.buildDatabase):
        buildDatabase()
    elif(args.refreshPlayer):
        refreshPlayer()
    elif(args.ping):
        ping() 
    else:
        main(args)

