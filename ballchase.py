# importing the requests library
import requests
import json
import time
import logging
from datetime import datetime, timezone
from dateutil import relativedelta, parser
import argparse
import os
from enum import Enum
from typing import List, Dict, Any, Optional, Union
from requests.exceptions import RequestException
from time import sleep

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ballchasing.log'),
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

# Constants
URL = "https://ballchasing.com/api/replays/"
PING = "https://ballchasing.com/api"
API_KEY = os.getenv("BALLCHASING_API_KEY")
if not API_KEY:
    logger.error("BALLCHASING_API_KEY environment variable not set")
    raise EnvironmentError("BALLCHASING_API_KEY environment variable not set")

# API request headers
HEADERS = {'Authorization': API_KEY}

# Load player data
try:
    with open('data/players.json') as f:
        PLAYERS = json.load(f)
except FileNotFoundError:
    logger.error("players.json not found in data directory")
    raise
except json.JSONDecodeError:
    logger.error("Invalid JSON in players.json")
    raise

class TeamColor(Enum):
    BLUE = 0
    ORANGE = 1
    NEITHER = 2

def get_player_id(name: str) -> Optional[str]:
    """Get player ID from name.
    
    Args:
        name: Player name to look up
        
    Returns:
        Player ID string or None if not found
    """
    for player in PLAYERS['data']:
        if player['name'] == name:
            return f"{player['platform']}:{player['id']}"
            
    logger.error(f'Player "{name}" not found')
    return None

def grabGames(args: argparse.Namespace, max_retries: int = 3, retry_delay: int = 1) -> List[Dict[str, Any]]:
    """Fetch games from ballchasing.com API with retry logic.
    
    Args:
        args: Command line arguments
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    
    Returns:
        List of replay data
    """
    player_id = get_player_id(args.player1)
    if not player_id:
        return []

    params = {'player-id': player_id}
    
    # Set playlist parameter
    if args.type == '1':
        params['playlist'] = 'ranked-duels'
    elif args.type == '2':
        params['playlist'] = 'ranked-doubles'
    elif args.type == '3':
        params['playlist'] = 'ranked-standard'
    elif args.type == 'p':
        params['playlist'] = 'private'

    if args.date:
        params['replay-date-after'] = args.date
    
    games = []
    data_left = True
    next_url = URL
    next_params = params
    num_requests = 0
    num_games = 0

    while data_left:
        for attempt in range(max_retries):
            try:
                response = requests.get(url=next_url, headers=HEADERS, params=next_params)
                response.raise_for_status()
                num_requests += 1
                data = response.json()

                if 'count' in data:
                    num_games += len(data['list'])
                    logger.info(f'Request {num_requests}: Retrieved {num_games}/{data["count"]} games')
                
                games.extend(data['list'])
                
                if "next" in data:
                    next_url = data['next']
                else:
                    data_left = False
                
                break  # Success, exit retry loop
                
            except RequestException as e:
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"Failed to fetch data after {max_retries} attempts: {e}")
                    data_left = False
                else:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    sleep(retry_delay)
    
    return games

def hasPlayer(replay: Dict[str, Any], name: str) -> bool:
    """Check if a player is in a replay.
    
    Args:
        replay: Replay data
        name: Player name to check for
        
    Returns:
        True if player is in replay, False otherwise
    """
    try:
        player_id = nameToId(name)
        if not player_id:
            return False

        blue_ids = [p['id']['id'] for p in replay.get('blue', {}).get('players', [])]
        orange_ids = [p['id']['id'] for p in replay.get('orange', {}).get('players', [])]
        return player_id in blue_ids or player_id in orange_ids
    except (KeyError, TypeError) as e:
        logger.warning(f"Error checking player in replay: {e}")
        return False

def getPlayerTeam(replay: Dict[str, Any], name: str) -> TeamColor:
    """Get which team a player is on in a replay.
    
    Args:
        replay: Replay data
        name: Player name to check
        
    Returns:
        TeamColor enum indicating which team the player is on
    """
    try:
        player_id = nameToId(name)
        if not player_id:
            return TeamColor.NEITHER

        blue_ids = [p['id']['id'] for p in replay.get('blue', {}).get('players', [])]
        orange_ids = [p['id']['id'] for p in replay.get('orange', {}).get('players', [])]
        
        if player_id in blue_ids:
            return TeamColor.BLUE
        if player_id in orange_ids:
            return TeamColor.ORANGE
        
        return TeamColor.NEITHER
    except (KeyError, TypeError) as e:
        logger.warning(f"Error getting player team: {e}")
        return TeamColor.NEITHER

def getWinner(replay: Dict[str, Any]) -> TeamColor:
    """Get the winning team from a replay.
    
    Args:
        replay: Replay data
        
    Returns:
        TeamColor enum indicating the winning team
    """
    try:
        blue_goals = int(replay.get('blue', {}).get('goals', 0))
        orange_goals = int(replay.get('orange', {}).get('goals', 0))

        if blue_goals > orange_goals:
            return TeamColor.BLUE
        if orange_goals > blue_goals:
            return TeamColor.ORANGE
        
        return TeamColor.NEITHER
    except (ValueError, TypeError) as e:
        logger.warning(f"Error determining winner: {e}")
        return TeamColor.NEITHER

def countNotables(replay: Dict[str, Any]) -> int:
    """Count how many notable players are in a replay.
    
    Args:
        replay: Replay data
        
    Returns:
        Number of notable players in the replay
    """
    count = 0
    for player in PLAYERS['data']:
        if hasPlayer(replay, player['name']):
            count += 1
    return count

def isGameType(replay: Dict[str, Any], game_type: str) -> bool:
    """Check if a replay is of a specific game type.
    
    Args:
        replay: Replay data
        game_type: Game type to check for ('1', '2', '3', 'p')
        
    Returns:
        True if replay matches game type, False otherwise
    """
    try:
        if game_type == '1':
            game_type = 'ranked-duels'
        elif game_type == '2':
            game_type = 'ranked-doubles'
        elif game_type == '3':
            game_type = 'ranked-standard'
        elif game_type == 'p':
            game_type = 'private'

        return replay.get('playlist_id') == game_type
    except (KeyError, TypeError) as e:
        logger.warning(f"Error checking game type: {e}")
        return False

def nameToId(name: str) -> Optional[str]:
    """Convert player name to ID.
    
    Args:
        name: Player name to convert
        
    Returns:
        Player ID string or None if not found
    """
    for player in PLAYERS['data']:
        if player['name'] == name:
            return str(player['id'])
    logger.error(f'Player "{name}" not found')
    return None

def filterGames(args: argparse.Namespace, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter games based on command line arguments.
    
    Args:
        args: Command line arguments
        games: List of replay data to filter
        
    Returns:
        Filtered list of replays
    """
    filtered_games = []
    past = None

    if args.date:
        today = datetime.now(timezone.utc)
        past = today - relativedelta.relativedelta(months=args.date)

    for replay in games:
        try:
            # Date filter
            if past and datetime.strptime(replay['date'], "%Y-%m-%dT%H:%M:%S%z") < past:
                continue

            # Game type filter
            if args.type and not isGameType(replay, args.type):
                continue

            # Private game filter
            if args.remove_priv and isGameType(replay, 'p'):
                continue

            # Player filters
            if args.player1 and not hasPlayer(replay, args.player1):
                continue
            if args.player2 and not hasPlayer(replay, args.player2):
                continue
            
            # Stacked lobby filter
            if args.stacked_lobby and countNotables(replay) < int(args.stacked_lobby):
                continue

            filtered_games.append(replay)
            
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Error filtering replay {replay.get('id', 'unknown')}: {e}")
            continue

    return filtered_games

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
                    r = requests.get(url = url, headers = HEADERS)
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
    r = requests.get(url = PING, headers = HEADERS)
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

