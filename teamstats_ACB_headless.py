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
NOMBRE_ARCHIVO = f"TeamStats_ACB_{TEMPORADA}_Cumulative.csv"
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

# ==============================================================================
# 2. FUNCIONES DE AYUDA
# ==============================================================================

def safe_div(x, y): return x / y if y != 0 else 0.0

def str_time_to_float(time_str):
    try:
        if not time_str or ':' not in time_str: return 0.0
        m, s = map(int, time_str.split(':'))
        return m + (s / 60.0)
    except: return 0.0

def get_codigo_inteligente(nombre_api):
    if not nombre_api: return "UNK"
    nombre_limpio = nombre_api.upper()
    for palabra_clave, sigla in MAPPING_ACB.items():
        if palabra_clave in nombre_limpio: return sigla
    return nombre_limpio[:3]

def get_real_teams_from_api(game_id):
    url = "https://api2.acb.com/api/matchdata/Result/header"
    try:
        r = requests.get(url, params={'matchId': game_id}, headers=HEADERS_API, timeout=3)
        if r.status_code == 200:
            data = r.json()
            home_name = data.get('homeTeam', {}).get('fullName', 'UNK')
            away_name = data.get('awayTeam', {}).get('fullName', 'UNK')
            return get_codigo_inteligente(home_name), get_codigo_inteligente(away_name)
    except: pass
    return "UNK", "UNK"

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
# 3. LÓGICA DE EXTRACCIÓN TEAM STATS
# ==============================================================================

def get_full_team_totals(team_data):
    t = {
        'PTS':0, 'VAL':0, 
        'T2M':0, 'T2A':0, 'T3M':0, 'T3A':0, 'FTM':0, 'FTA':0,
        'ORB':0, 'DRB':0, 'TRB':0, 
        'AST':0, 'STL':0, 'TOV':0, 'BLK':0, 'PF':0, 'PF_R':0,
        'MIN': 200.0
    }
    
    src = team_data.get('totalStats')
    if src:
        t['PTS'] = src.get('points', 0); t['VAL'] = src.get('rating', 0)
        t['T2M'] = src.get('twoPointersMade', 0); t['T2A'] = src.get('twoPointersAttempted', 0)
        t['T3M'] = src.get('threePointersMade', 0); t['T3A'] = src.get('threePointersAttempted', 0)
        t['FTM'] = src.get('freeThrowsMade', 0); t['FTA'] = src.get('freeThrowsAttempted', 0)
        t['ORB'] = src.get('offRebounds', 0); t['DRB'] = src.get('defRebounds', 0); t['TRB'] = src.get('totalRebounds', 0)
        t['AST'] = src.get('assists', 0); t['STL'] = src.get('steals', 0)
        t['TOV'] = src.get('turnovers', 0); t['BLK'] = src.get('blocks', 0)
        t['PF']  = src.get('personalFouls', 0); t['PF_R'] = src.get('foulsDrawn', 0)

    if team_data.get('statsByPeriods'):
        players = team_data['statsByPeriods'][0].get('stats', {}).get('players', [])
        min_sum = sum([str_time_to_float(p.get('playTime', '00:00')) for p in players])
        t['MIN'] = min_sum / 5.0
        
        if not src: 
            for p in players:
                t['PTS'] += p.get('points', 0); t['VAL'] += p.get('rating', 0)
                t['T2M'] += p.get('twoPointersMade', 0); t['T2A'] += p.get('twoPointersAttempted', 0)
                t['T3M'] += p.get('threePointersMade', 0); t['T3A'] += p.get('threePointersAttempted', 0)
                t['FTM'] += p.get('freeThrowsMade', 0); t['FTA'] += p.get('freeThrowsAttempted', 0)
                t['ORB'] += p.get('offRebounds', 0); t['DRB'] += p.get('defRebounds', 0); t['TRB'] += p.get('totalRebounds', 0)
                t['AST'] += p.get('assists', 0); t['STL'] += p.get('steals', 0)
                t['TOV'] += p.get('turnovers', 0); t['BLK'] += p.get('blocks', 0)
                t['PF'] += p.get('personalFouls', 0); t['PF_R'] += p.get('foulsDrawn', 0)
    
    t['FGM'] = t['T2M'] + t['T3M']; t['FGA'] = t['T2A'] + t['T3A']
    return t

def get_team_stats_api(game_id, home_code, away_code, season_lbl, week_lbl):
    url = "https://api2.acb.com/api/matchdata/Result/boxscores"
    rows = []
    
    try:
        r = requests.get(url, params={'matchId': game_id}, headers=HEADERS_API, timeout=5)
        if r.status_code != 200: return []
        
        data = r.json()
        if 'teamBoxscores' not in data: return []
        
        d_loc = data['teamBoxscores'][0]
        d_vis = data['teamBoxscores'][1]
        
        # Fallback de seguridad
        if home_code == "UNK": home_code = get_codigo_inteligente(d_loc.get('team', {}).get('fullName', 'UNK'))
        if away_code == "UNK": away_code = get_codigo_inteligente(d_vis.get('team', {}).get('fullName', 'UNK'))

        home_id_num = d_loc.get('team', {}).get('id', '')
        away_id_num = d_vis.get('team', {}).get('id', '')

        tot_loc = get_full_team_totals(d_loc)
        tot_vis = get_full_team_totals(d_vis)
        
        # Posesiones (Fórmula Dean Oliver)
        def calc_poss(tm, opp): return tm['FGA'] + 0.44*tm['FTA'] - tm['ORB'] + tm['TOV']
        poss_loc = calc_poss(tot_loc, tot_vis)
        poss_vis = calc_poss(tot_vis, tot_loc)
        game_poss = (poss_loc + poss_vis) / 2
        
        # Generar filas
        for i in range(2):
            is_local = (i == 0)
            
            if is_local:
                tm = tot_loc; opp = tot_vis
                code = home_code; opp_code = away_code
                curr_id = home_id_num; opp_id = away_id_num
                curr_poss = poss_loc 
                loc_str = "HOME"
            else:
                tm = tot_vis; opp = tot_loc
                code = away_code; opp_code = home_code
                curr_id = away_id_num; opp_id = home_id_num
                curr_poss = poss_vis
                loc_str = "AWAY"
                
            is_win = 1 if tm['PTS'] > opp['PTS'] else 0
            
            # --- MÉTRICAS AVANZADAS ---
            ortg = safe_div(tm['PTS'], game_poss) * 100
            drtg = safe_div(opp['PTS'], game_poss) * 100
            net_rtg = ortg - drtg
            
            ppp = safe_div(tm['PTS'], curr_poss)
            pps = safe_div(tm['PTS'], tm['FGA'])
            
            ast_ratio_poss = safe_div(tm['AST'], curr_poss) * 100
            pct_fgm_ast = safe_div(tm['AST'], tm['FGM']) * 100 

            ts_pct = safe_div(tm['PTS'], 2 * (tm['FGA'] + 0.44 * tm['FTA'])) * 100
            efg_pct = safe_div(tm['FGM'] + 0.5 * tm['T3M'], tm['FGA']) * 100
            
            orb_pct = safe_div(tm['ORB'], tm['ORB'] + opp['DRB']) * 100
            drb_pct = safe_div(tm['DRB'], tm['DRB'] + opp['ORB']) * 100
            trb_pct = safe_div(tm['TRB'], tm['TRB'] + opp['TRB']) * 100
            
            tov_pct = safe_div(tm['TOV'], tm['FGA'] + 0.44 * tm['FTA'] + tm['TOV']) * 100
            ast_to = safe_div(tm['AST'], tm['TOV'])
            
            t3ar = safe_div(tm['T3A'], tm['FGA']) * 100
            ftr = safe_div(tm['FTA'], tm['FGA']) * 100
            
            row = {
                'GameID': game_id, 'Season': season_lbl, 'Week': week_lbl,
                'Team': code, 'TeamID': curr_id,
                'Location': loc_str, 
                'Opponent': opp_code, 'OpponentID': opp_id,
                'Win': is_win,
                
                'Game_Poss': round(game_poss, 1), 
                'Team_Poss': round(curr_poss, 1),
                
                'PTS': tm['PTS'], 'PTS_Opp': opp['PTS'], 'Diff': tm['PTS'] - opp['PTS'],
                'VAL': tm['VAL'], 
                
                'T2M': tm['T2M'], 'T2A': tm['T2A'], 'T2%': round(safe_div(tm['T2M'], tm['T2A'])*100, 1),
                'T3M': tm['T3M'], 'T3A': tm['T3A'], 'T3%': round(safe_div(tm['T3M'], tm['T3A'])*100, 1),
                'FTM': tm['FTM'], 'FTA': tm['FTA'], 'FT%': round(safe_div(tm['FTM'], tm['FTA'])*100, 1),
                'FGM': tm['FGM'], 'FGA': tm['FGA'], 'FG%': round(safe_div(tm['FGM'], tm['FGA'])*100, 1),
                
                'ORB': tm['ORB'], 'DRB': tm['DRB'], 'TRB': tm['TRB'],
                'AST': tm['AST'], 'STL': tm['STL'], 'TOV': tm['TOV'], 'BLK': tm['BLK'], 
                'PF': tm['PF'], 'PF_R': tm['PF_R'],
                
                'ORTG': round(ortg, 1), 'DRTG': round(drtg, 1), 'NET_RTG': round(net_rtg, 1),
                'PPP': round(ppp, 2), 'PPS': round(pps, 2),
                
                'TS%': round(ts_pct, 1), 'eFG%': round(efg_pct, 1),
                '3PAr': round(t3ar, 1), 'FTr': round(ftr, 1),
                
                'ORB%': round(orb_pct, 1), 'DRB%': round(drb_pct, 1), 'TRB%': round(trb_pct, 1),
                
                '%FGM_Ast': round(pct_fgm_ast, 1), 
                'TOV%': round(tov_pct, 1), 'AST/TO': round(ast_to, 2),
                'AST_Ratio': round(ast_ratio_poss, 1)
            }
            rows.append(row)
            
        return rows
    except Exception as e: 
        print(f" (Err: {e})", end="")
        return []

# ==============================================================================
# 4. MAIN - BUCLE AUTOMÁTICO
# ==============================================================================

def main():
    print(f"🚀 INICIANDO SCRAPER TEAM STATS HEADLESS: {TEMPORADA}")
    
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
            h_code, a_code = get_real_teams_from_api(gid)
            data = get_team_stats_api(gid, h_code, a_code, TEMPORADA, lbl_jornada)
            
            if data:
                try: 
                    match_lbl = f"{data[0]['Team']} vs {data[1]['Team']}"
                    jornada_data.extend(data)
                except: match_lbl = "Datos OK"
            else:
                match_lbl = "Sin datos"
                print(f"   ⚠️ Partido {gid}: {match_lbl}")
            
            time.sleep(0.1) # Pausa ética
            
        if jornada_data:
            all_season_data.extend(jornada_data)
            print(f"   ---> Guardados {len(jornada_data)//2} partidos de Jornada {jornada}.")
        else:
            print(f"   ⚠️ Jornada {jornada} sin datos de equipo.")
        
        jornada += 1

    # ==============================================================================
    # 5. EXPORTACIÓN FINAL
    # ==============================================================================
    if all_season_data:
        print("\n💾 Generando archivo TeamStats Maestro...")
        df = pd.DataFrame(all_season_data)
        
        cols = ['GameID', 'Season', 'Week', 
                'Team', 'TeamID', 'Location', 'Opponent', 'OpponentID', 'Win', 
                'PTS', 'PTS_Opp', 'Diff', 'VAL', 
                'T2M', 'T2A', 'T2%', 'T3M', 'T3A', 'T3%', 'FTM', 'FTA', 'FT%', 
                'FGM', 'FGA', 'FG%',
                'ORB', 'DRB', 'TRB',
                'AST', 'STL', 'TOV', 'BLK', 'PF', 'PF_R',
                'Game_Poss', 'Team_Poss', 
                'ORTG', 'DRTG', 'NET_RTG', 
                'PPP', 'PPS', 
                'TS%', 'eFG%', 
                '3PAr', 'FTr',
                'ORB%', 'DRB%', 'TRB%', 
                '%FGM_Ast', 'TOV%', 'AST/TO', 'AST_Ratio']
        
        df = df[[c for c in cols if c in df.columns]]
        
        ruta_completa = os.path.join(CARPETA_SALIDA, NOMBRE_ARCHIVO)
        df.to_csv(ruta_completa, index=False, encoding='utf-8-sig')
        
        print(f"🎉 ÉXITO: Archivo guardado en: {ruta_completa}")
        print(f"📊 Total Filas: {len(df)}")
    else:
        print("❌ No se obtuvieron datos.")

if __name__ == "__main__":
    main()