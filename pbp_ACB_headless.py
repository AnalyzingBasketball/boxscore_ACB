import requests
import pandas as pd
import time
from bs4 import BeautifulSoup
import os
import sys

# ==============================================================================
# 1. CONFIGURACIÓN HEADLESS
# ==============================================================================
TEMPORADA = '2025'  # 2025/2026
COMPETICION = '1'   # Liga Endesa
NOMBRE_ARCHIVO = f"PlayByPlay_ACB_{TEMPORADA}_Cumulative.csv"
CARPETA_SALIDA = "data"

API_KEY = '0dd94928-6f57-4c08-a3bd-b1b2f092976e'
HEADERS_API = {
    'x-apikey': API_KEY,
    'origin': 'https://live.acb.com',
    'referer': 'https://live.acb.com/',
    'user-agent': 'Mozilla/5.0'
}

MAPPING_ACB = {
    "BILBAO": "SBB", "SURNE": "SBB", "MADRID": "RMB", "REAL MADRID": "RMB", 
    "BARÇA": "BAR", "BARCELONA": "BAR", "BASKONIA": "BKN", "MANRESA": "MAN", 
    "TENERIFE": "TEN", "LAGUNA": "TEN", "UNICAJA": "UNI", "VALENCIA": "VBC", 
    "MURCIA": "UCM", "GRAN CANARIA": "GCA", "DREAMLAND": "GCA", "JOVENTUT": "JOV", 
    "PENYA": "JOV", "BREOGÁN": "BRE", "BREOGAN": "BRE", "RÍO": "BRE", "RIO": "BRE",
    "GRANADA": "COV", "COVIRAN": "COV", "ZARAGOZA": "CAZ", "CASADEMONT": "CAZ",
    "ANDORRA": "MBA", "MORABANC": "MBA", "GIRONA": "GIR", "BÀSQUET GIRONA": "GIR",
    "CORUÑA": "COR", "LEYMA": "COR", "LLEIDA": "LLE", "HIOPOS": "LLE", 
    "BURGOS": "BUR", "SAN PABLO": "BUR", "RECOLETAS": "BUR"
}

ACTION_MAP = {
    '92': 'FT Made', '93': '2PT Made', '94': '3PT Made',
    '96': 'FT Missed', '97': '2PT Missed', '98': '3PT Missed',
    '100': '2PT Dunk Made', '533': '2PT Dunk Missed',
    '101': 'Offensive Rebound', '104': 'Defensive Rebound',
    '102': 'Block', '105': 'Block Received',
    '103': 'Steal', '106': 'Turnover',
    '107': 'Assist', '108': 'Assist', '119': 'FT Assist',
    '109': 'Offensive Foul', '110': 'Foul Drawn',
    '159': 'Personal Foul', '160': 'Personal Foul (1FT)', '161': 'Personal Foul', 
    '162': 'Personal Foul (3FT)',
    '165': 'Unsportsmanlike Foul', '166': 'Unsportsmanlike Foul', 
    '167': 'Unsportsmanlike Foul (3FT)', '168': 'Unsportsmanlike Foul (Offsetting)',
    '200': 'Disqualifying Foul',
    '173': 'Technical Foul (Offsetting)', '537': 'Technical Foul',
    '540': 'Coach Technical Foul', '544': 'Bench Technical Foul',
    '547': 'Bench Technical Foul (Offsetting)',
    '112': 'Substitution In', '115': 'Substitution Out', '599': 'Starting Five',
    '113': 'Timeout', '118': 'TV Timeout',
    '178': 'Jump Ball Won', '179': 'Jump Ball Lost',
    '600': 'Minute Tick', '122': 'Start of Match', '123': 'End of Match',
    '121': 'Start of Quarter', '116': 'End of Quarter',
    '406': 'IR - Check Shot Type', '407': 'IR - Check Basket Validity',
    '408': 'IR - Check Shot Clock', '409': 'IR - Check Game Clock',
    '410': 'IR - Fight Review', '411': 'IR - Foul Type Review',
    '412': 'IR - Violation Review', '413': 'IR - Last Touch Review',
    '414': 'IR - Player Action Review', '415': 'IR - Substitution Review',
    '416': 'IR - Coach Challenge', '417': 'IR - Coach Challenge', 
    '748': 'IR - Challenge Won', '749': 'IR - Challenge Lost'
}

# ==============================================================================
# 2. FUNCIONES DE AYUDA
# ==============================================================================

def get_val(dic, keys, default=None):
    for k in keys:
        if '.' in k:
            parts = k.split('.')
            val = dic
            for p in parts:
                if isinstance(val, dict): val = val.get(p)
                else: val = None
            if val is not None and val != "": return val
        elif k in dic and dic[k] is not None and dic[k] != "":
            return dic[k]
    return default

def format_player_name(full_name):
    if not full_name: return ""
    s = str(full_name).strip()
    if ',' in s:
        parts = s.split(',')
        if len(parts) >= 2: return f"{parts[1].strip()[0].upper()}. {parts[0].strip()}"
    parts = s.split()
    if len(parts) >= 2: return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"
    return s

def get_codigo_inteligente(nombre_api):
    if not nombre_api: return "UNK"
    nombre_limpio = nombre_api.upper()
    for palabra_clave, sigla in MAPPING_ACB.items():
        if palabra_clave in nombre_limpio: return sigla
    return nombre_limpio[:3]

# ==============================================================================
# 3. SCRAPING Y EXTRACCIÓN
# ==============================================================================

def get_games_info(temp_id, comp_id, jornada_id):
    """Obtiene lista de partidos (IDs y Códigos de equipo) de una jornada."""
    url = f"https://www.acb.com/resultados-clasificacion/ver/temporada_id/{temp_id}/competicion_id/{comp_id}/jornada_numero/{jornada_id}"
    matches = []
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        links = soup.find_all('a', href=True)
        for a in links:
            if "/partido/estadisticas/id/" in a['href']:
                try:
                    pid = int(a['href'].split("/id/")[1].split("/")[0])
                    container = a.find_parent('div', class_='partido') 
                    if not container: container = a.find_parent('article')
                    home_code, away_code = "UNK", "UNK"
                    if container:
                        imgs = container.find_all('img', alt=True)
                        team_imgs = [img['alt'] for img in imgs if len(img['alt']) > 2 and 'ACB' not in img['alt']]
                        if len(team_imgs) >= 2:
                            home_code = get_codigo_inteligente(team_imgs[0])
                            away_code = get_codigo_inteligente(team_imgs[1])
                    matches.append({'id': pid, 'home': home_code, 'away': away_code})
                except: pass
        
        # Eliminar duplicados
        unique_matches = []
        seen = set()
        for m in matches:
            if m['id'] not in seen:
                unique_matches.append(m); seen.add(m['id'])
        return unique_matches
    except: return []

def get_pbp_api(game_data, season_lbl, week_lbl):
    game_id = game_data['id']
    code_home = game_data['home']
    code_away = game_data['away']
    
    url = "https://api2.acb.com/api/matchdata/PlayByPlay/play-by-play"
    rows = []
    
    # --- INICIALIZACIÓN DE LINEUPS ---
    home_on_court = set()
    away_on_court = set()
    
    try:
        r = requests.get(url, params={'matchId': game_id}, headers=HEADERS_API, timeout=5)
        if r.status_code != 200: return []
            
        data_json = r.json()
        events = []
        if isinstance(data_json, list): events = data_json
        elif isinstance(data_json, dict):
            for k, v in data_json.items():
                if isinstance(v, list): events.extend(v)
        
        for ev in events:
            if not isinstance(ev, dict): continue

            # --- EXTRACCIÓN DE DATOS BÁSICOS ---
            m = get_val(ev, ['minute'], 0)
            s = get_val(ev, ['second'], 0)
            time_str = f"{m:02d}:{s:02d}"
            if time_str == "00:00": time_str = get_val(ev, ['cronometer', 'time'], "00:00")
            try:
                if ':' in time_str:
                    mm, ss = map(int, time_str.split(':'))
                    time_seconds = (mm * 60) + ss
                else: time_seconds = (m * 60) + s
            except: time_seconds = 0

            period = get_val(ev, ['Period', 'period', 'idPeriod', 'quarter'], '')
            s_loc = get_val(ev, ['scoreHome', 'scoreLocal', 'homeScore'], 0)
            s_vis = get_val(ev, ['scoreAway', 'scoreVisitor', 'awayScore'], 0)
            diff = s_loc - s_vis
            
            is_loc = get_val(ev, ['local'])
            team_real, location_str = "", ""
            if is_loc is True: team_real, location_str = code_home, "HOME"
            elif is_loc is False: team_real, location_str = code_away, "AWAY"
            
            # --- DATOS DEL JUGADOR ---
            player_raw = get_val(ev, ['Player', 'player', 'playerName', 'nickName', 'player.nickName'])
            player_name = format_player_name(player_raw)
            dorsal = get_val(ev, ['playerNumber', 'dorsal', 'shirtNumber'], '')
            
            # --- EXTRACCIÓN DE PLAYER ID ---
            pid = str(get_val(ev, ['player.id', 'player.license', 'playerLicenseId', 'license', 'id'], ''))
            if pid and pid.upper().startswith('P'): pid = pid[1:]
            
            if not pid and player_name: pid = "UNK" 
            elif not player_name: pid = ""     
            
            # --- TIPO DE JUGADA ---
            play_type_id = str(get_val(ev, ['playType', 'type', 'actionId', 'idAction'], 'UNK'))
            description = ACTION_MAP.get(play_type_id, f"Unknown Code ({play_type_id})")
            description = str(description).replace("<b>", "").replace("</b>", "")

            # --- MOTOR DE LINEUPS (ACTUALIZACIÓN DE ESTADO) ---
            if player_name:
                if team_real == code_home: home_on_court.add(player_name)
                elif team_real == code_away: away_on_court.add(player_name)
            
            if play_type_id == '599': # Starting Five
                if team_real == code_home: home_on_court.add(player_name)
                elif team_real == code_away: away_on_court.add(player_name)
            
            elif play_type_id == '112': # Substitution In
                if team_real == code_home: home_on_court.add(player_name)
                elif team_real == code_away: away_on_court.add(player_name)
                
            elif play_type_id == '115': # Substitution Out
                if team_real == code_home: home_on_court.discard(player_name)
                elif team_real == code_away: away_on_court.discard(player_name)

            # --- PREPARAR COLUMNAS DE JUGADORES ---
            h_list = sorted(list(home_on_court))
            a_list = sorted(list(away_on_court))
            
            while len(h_list) < 5: h_list.append("")
            while len(a_list) < 5: a_list.append("")
            
            h_final = h_list[:5]
            a_final = a_list[:5]

            row = {
                'Competition': 'ACB', 'Season': season_lbl, 'Week': week_lbl,
                'Gamecode': game_id, 'Period': period,
                'Time': time_str, 'Seconds': time_seconds,
                'Score_Home': s_loc, 'Score_Away': s_vis, 'Diff': diff,
                'Team': team_real, 'Location': location_str,
                'Dorsal': dorsal, 
                'PlayerID': pid, 
                'Player': player_name,
                'Action_Type': description, 'Action_ID': play_type_id,
                'H1': h_final[0], 'H2': h_final[1], 'H3': h_final[2], 'H4': h_final[3], 'H5': h_final[4],
                'A1': a_final[0], 'A2': a_final[1], 'A3': a_final[2], 'A4': a_final[3], 'A5': a_final[4]
            }
            rows.append(row)
            
        return rows
    except Exception as e:
        print(f"Error procesando ID {game_id}: {e}")
        return []

# ==============================================================================
# 4. MAIN - BUCLE AUTOMÁTICO
# ==============================================================================

def main():
    print(f"🚀 INICIANDO SCRAPER PbP HEADLESS: {TEMPORADA}")
    
    all_season_data = []
    jornada = 1
    
    if not os.path.exists(CARPETA_SALIDA):
        os.makedirs(CARPETA_SALIDA)

    while True:
        print(f"\n🔍 Buscando Jornada {jornada}...")
        matches_info = get_games_info(TEMPORADA, COMPETICION, str(jornada))
        
        if not matches_info:
            print(f"⛔ Jornada {jornada} vacía o futura. Deteniendo.")
            break
        
        print(f"✅ {len(matches_info)} partidos encontrados.")
        
        jornada_data = []
        for m in matches_info:
            lbl_jornada = f"Jornada {jornada}"
            data = get_pbp_api(m, TEMPORADA, lbl_jornada)
            if data:
                jornada_data.extend(data)
            else:
                print(f"   ⚠️ Partido {m['id']} sin datos PbP.")
            time.sleep(0.1) # Respeto a la API
            
        if jornada_data:
            all_season_data.extend(jornada_data)
            print(f"   ---> Guardados {len(jornada_data)} eventos de Jornada {jornada}.")
        
        jornada += 1

    # ==============================================================================
    # 5. EXPORTACIÓN FINAL
    # ==============================================================================
    if all_season_data:
        print("\n💾 Generando archivo PbP Maestro...")
        df = pd.DataFrame(all_season_data)
        
        cols = ['Competition', 'Season', 'Week', 'Gamecode', 'Period', 'Time', 'Seconds', 
                'Score_Home', 'Score_Away', 'Diff',
                'Team', 'Location', 'Dorsal', 'PlayerID', 'Player', 'Action_Type', 'Action_ID',
                'H1', 'H2', 'H3', 'H4', 'H5',
                'A1', 'A2', 'A3', 'A4', 'A5']
        
        df = df[[c for c in cols if c in df.columns]]
        
        ruta_completa = os.path.join(CARPETA_SALIDA, NOMBRE_ARCHIVO)
        df.to_csv(ruta_completa, index=False, encoding='utf-8-sig')
        
        print(f"🎉 ÉXITO: Archivo guardado en: {ruta_completa}")
        print(f"📊 Total Filas: {len(df)}")
    else:
        print("❌ No se obtuvieron datos.")

if __name__ == "__main__":
    main()