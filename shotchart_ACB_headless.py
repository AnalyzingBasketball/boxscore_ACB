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
NOMBRE_ARCHIVO = f"ShotChart_ACB_{TEMPORADA}_Cumulative.csv"
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
    "BURGOS": "BUR", "SAN PABLO": "BUR"
}

MISSED_CODES = {
    '533': '2PT Dunk Missed', 
    '98': '3PT Missed',
    '97': '2PT Missed', 
    '96': 'FT Missed'
}
FORCED_MADE_CODES = ['93', '94', '92']

# ==============================================================================
# 2. FUNCIONES DE AYUDA
# ==============================================================================

def get_codigo_inteligente(nombre_api):
    if not nombre_api: return "UNK"
    nombre_limpio = nombre_api.upper()
    for palabra_clave, sigla in MAPPING_ACB.items():
        if palabra_clave in nombre_limpio: return sigla
    return nombre_limpio[:3]

def format_player_name(full_name):
    if not full_name: return ""
    s = str(full_name).strip()
    if ',' in s:
        parts = s.split(',')
        if len(parts) >= 2: return f"{parts[1].strip()[0].upper()}. {parts[0].strip()}"
    parts = s.split()
    if len(parts) >= 2: return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"
    return s

def get_game_ids(temp_id, comp_id, jornada_id):
    """Obtiene IDs de partidos."""
    url = f"https://www.acb.com/resultados-clasificacion/ver/temporada_id/{temp_id}/competicion_id/{comp_id}/jornada_numero/{jornada_id}"
    ids = []
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=True):
            if "/partido/estadisticas/id/" in a['href']:
                try:
                    pid = int(a['href'].split("/id/")[1].split("/")[0])
                    ids.append(pid)
                except: pass
        return list(set(ids))
    except: return []

# ==============================================================================
# 3. LÓGICA DE EXTRACCIÓN SHOTCHART
# ==============================================================================

def get_shots_api(game_id, season_lbl, week_lbl):
    url = "https://api2.acb.com/api/matchdata/MatchShots/match-shots"
    rows = []
    
    try:
        r = requests.get(url, params={'matchId': game_id}, headers=HEADERS_API, timeout=5)
        if r.status_code != 200: return [], "Err"
        
        data = r.json()
        if 'shotPoints' not in data: return [], "NoShots"
        
        # --- EXTRACCIÓN DE EQUIPOS ---
        raw_home = data.get('homeTeam', {}).get('fullName', '')
        raw_away = data.get('awayTeam', {}).get('fullName', '')
        if not raw_home: raw_home = data.get('homeTeam', {}).get('shortName', 'UNK')
        if not raw_away: raw_away = data.get('awayTeam', {}).get('shortName', 'UNK')
        
        home_code = get_codigo_inteligente(raw_home)
        away_code = get_codigo_inteligente(raw_away)
        match_label = f"{home_code} vs {away_code}"
        
        # --- MAPEO DE JUGADORES ---
        player_map = {}
        all_players = data.get('homePlayerStats', []) + data.get('awayPlayerStats', [])
        for p in all_players:
            pid = p.get('playerLicenseId')
            pname = p.get('nickName') or p.get('playerName') or "Unknown"
            player_map[pid] = format_player_name(pname)
            
        shots = data['shotPoints']
        # Ordenar tiros cronológicamente para el marcador
        shots.sort(key=lambda x: (x.get('quarter', 0), -x.get('minute', 0), -x.get('second', 0), x.get('id', 0)))
        
        last_score = (0, 0)
        
        for s in shots:
            is_local = s.get('local', False)
            team_real = home_code if is_local else away_code
            location_str = "HOME" if is_local else "AWAY"
            
            curr_h = s.get('scoreHome', 0)
            curr_a = s.get('scoreAway', 0)
            play_type = str(s.get('playType'))
            x_coord = s.get('posX', 0)
            y_coord = s.get('posY', 0)
            
            # --- LÓGICA DE PUNTOS Y TIPO ---
            diff = (curr_h + curr_a) - sum(last_score)
            action_txt, points = "Unknown", 0
            
            # 1. Por diferencia de marcador (más fiable para Made)
            if diff == 3:
                action_txt, points = "3PT Made", 3
            elif diff == 2:
                if x_coord == 0 and y_coord == 0: action_txt = "2PT Dunk Made"
                else: action_txt = "2PT Made"
                points = 2
            elif diff == 1:
                action_txt, points = "FT Made", 1
                
            # 2. Por código (para Missed o Made sin cambio marcador inmediato)
            elif play_type in FORCED_MADE_CODES:
                dist = (x_coord**2 + y_coord**2)**0.5
                if play_type == '92' and dist < 100: action_txt, points = "FT Made", 1
                else:
                    if dist >= 6600: action_txt, points = "3PT Made", 3
                    else:
                        if x_coord == 0 and y_coord == 0: action_txt = "2PT Dunk Made"
                        else: action_txt = "2PT Made"
                        points = 2
                        
            elif play_type in MISSED_CODES:
                action_txt = MISSED_CODES[play_type]
                points = 0
            else:
                action_txt = f"Miss (Code {play_type})"
                points = 0
            
            # Actualizar marcador tracking
            if diff > 0: last_score = (curr_h, curr_a)
            elif points > 0:
                if is_local: last_score = (last_score[0] + points, last_score[1])
                else: last_score = (last_score[0], last_score[1] + points)
            else: last_score = (max(last_score[0], curr_h), max(last_score[1], curr_a))
            
            m = s.get('minute', 0); sec = s.get('second', 0)
            time_str = f"{m:02d}:{sec:02d}"; time_seconds = (m * 60) + sec
            
            # --- PLAYER ID LIMPIO ---
            raw_pid = str(s.get('playerLicenseId', ''))
            clean_pid = raw_pid
            if clean_pid.upper().startswith('P'): clean_pid = clean_pid[1:]
            
            row = {
                'Competition': 'ACB', 
                'Season': season_lbl, 
                'Week': week_lbl, 
                'Gamecode': game_id,
                'Period': s.get('quarter', 0), 
                'Time': time_str, 
                'Seconds': time_seconds,
                'Team': team_real, 
                'Location': location_str,
                'PlayerID': clean_pid,
                'Player': player_map.get(s.get('playerLicenseId'), "UNKNOWN"),
                'Action': action_txt, 'Points': points,
                'Coord_X': x_coord, 'Coord_Y': y_coord,
                'Score_Home': curr_h, 'Score_Away': curr_a
            }
            rows.append(row)
            
        return rows, match_label
    except Exception as e:
        return [], f"Err: {e}"

# ==============================================================================
# 4. MAIN - BUCLE AUTOMÁTICO
# ==============================================================================

def main():
    print(f"🚀 INICIANDO SCRAPER SHOTCHART HEADLESS: {TEMPORADA}")
    
    all_season_data = []
    jornada = 1
    
    if not os.path.exists(CARPETA_SALIDA):
        os.makedirs(CARPETA_SALIDA)

    while True:
        print(f"\n🔍 Buscando Jornada {jornada}...")
        
        ids = get_game_ids(TEMPORADA, COMPETICION, str(jornada))
        
        if not ids:
            print(f"⛔ Jornada {jornada} vacía o futura. Deteniendo.")
            break
        
        print(f"✅ {len(ids)} partidos encontrados.")
        
        jornada_data = []
        for gid in ids:
            lbl_jornada = f"Jornada {jornada}"
            data, label = get_shots_api(gid, TEMPORADA, lbl_jornada)
            
            if data:
                jornada_data.extend(data)
            else:
                print(f"   ⚠️ Partido {gid}: {label}")
            
            time.sleep(0.1) # Pausa ética
            
        if jornada_data:
            all_season_data.extend(jornada_data)
            print(f"   ---> Guardados {len(jornada_data)} tiros de Jornada {jornada}.")
        else:
            print(f"   ⚠️ Jornada {jornada} sin datos de tiro.")
        
        jornada += 1

    # ==============================================================================
    # 5. EXPORTACIÓN FINAL
    # ==============================================================================
    if all_season_data:
        print("\n💾 Generando archivo ShotChart Maestro...")
        df = pd.DataFrame(all_season_data)
        
        cols = ['Competition', 'Season', 'Week', 'Gamecode', 'Period', 'Time', 'Seconds', 
                'Team', 'Location', 'PlayerID', 'Player', 
                'Action', 'Points', 'Coord_X', 'Coord_Y', 
                'Score_Home', 'Score_Away']
        
        df = df[[c for c in cols if c in df.columns]]
        
        ruta_completa = os.path.join(CARPETA_SALIDA, NOMBRE_ARCHIVO)
        df.to_csv(ruta_completa, index=False, encoding='utf-8-sig')
        
        print(f"🎉 ÉXITO: Archivo guardado en: {ruta_completa}")
        print(f"📊 Total Filas: {len(df)}")
    else:
        print("❌ No se obtuvieron datos.")

if __name__ == "__main__":
    main()