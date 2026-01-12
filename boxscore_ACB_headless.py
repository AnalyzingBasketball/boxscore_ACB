import requests
import pandas as pd
import time
from bs4 import BeautifulSoup
import os
import sys

# ==============================================================================
# 1. CONFIGURACIÓN HEADLESS
# ==============================================================================
# Configuración fija para la automatización
TEMPORADA = '2025'  # 2025/2026
COMPETICION = '1'   # Liga Endesa
NOMBRE_ARCHIVO = f"BoxScore_ACB_{TEMPORADA}_Cumulative.csv"
CARPETA_SALIDA = "data"  # Carpeta relativa para GitHub

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
# 2. FUNCIONES DE AYUDA (Mantenidas igual)
# ==============================================================================

def safe_div(x, y): return x / y if y != 0 else 0.0

def str_time_to_float(time_str):
    try:
        if not time_str or ':' not in time_str: return 0.0
        m, s = map(int, time_str.split(':'))
        return m + (s / 60.0)
    except: return 0.0

def str_time_to_seconds(time_str):
    try:
        if not time_str or ':' not in time_str: return 0
        m, s = map(int, time_str.split(':'))
        return (m * 60) + s
    except: return 0

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
# 3. LÓGICA DE EXTRACCIÓN
# ==============================================================================

def get_game_ids(temp_id, comp_id, jornada_id):
    """Extrae IDs. Si devuelve lista vacía, asumimos que la jornada no existe o no se ha jugado."""
    url = f"https://www.acb.com/resultados-clasificacion/ver/temporada_id/{temp_id}/competicion_id/{comp_id}/jornada_numero/{jornada_id}"
    ids = []
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # Buscar enlaces a estadísticas
        for a in soup.find_all('a', href=True):
            if "/partido/estadisticas/id/" in a['href']:
                try:
                    pid = int(a['href'].split("/id/")[1].split("/")[0])
                    ids.append(pid)
                except: pass
        return list(set(ids))
    except Exception as e:
        print(f"Error accediendo a calendario: {e}")
        return []

def get_team_totals(team_data):
    t = {'PTS':0, 'FGA':0, 'FGM':0, 'FTA':0, 'ORB':0, 'DRB':0, 'TRB':0, 'TOV':0, 'MIN':200.0, 'T2A': 0, 'T3A': 0} 
    src = team_data.get('totalStats')
    if src:
        t['PTS'] = src.get('points', 0)
        t['T2A'] = src.get('twoPointersAttempted', 0); t['T3A'] = src.get('threePointersAttempted', 0)
        t['FGM'] = src.get('twoPointersMade', 0) + src.get('threePointersMade', 0)
        t['FGA'] = t['T2A'] + t['T3A']
        t['FTA'] = src.get('freeThrowsAttempted', 0)
        t['ORB'] = src.get('offRebounds', 0); t['DRB'] = src.get('defRebounds', 0); t['TRB'] = src.get('totalRebounds', 0)
        t['TOV'] = src.get('turnovers', 0)
    
    if team_data.get('statsByPeriods'):
        players = team_data['statsByPeriods'][0].get('stats', {}).get('players', [])
        min_sum = sum([str_time_to_float(p.get('playTime', '00:00')) for p in players])
        t['MIN'] = min_sum / 5.0
        if not src:
            for p in players:
                t['PTS'] += p.get('points', 0)
                t['T2A'] += p.get('twoPointersAttempted', 0); t['T3A'] += p.get('threePointersAttempted', 0)
                t['FGM'] += (p.get('twoPointersMade', 0) + p.get('threePointersMade', 0))
                t['FTA'] += p.get('freeThrowsAttempted', 0)
                t['ORB'] += p.get('offRebounds', 0); t['DRB'] += p.get('defRebounds', 0); t['TRB'] += p.get('totalRebounds', 0)
                t['TOV'] += p.get('turnovers', 0)
            t['FGA'] = t['T2A'] + t['T3A']
    return t

def get_stats_api(game_id, season_lbl, week_lbl):
    url = "https://api2.acb.com/api/matchdata/Result/boxscores"
    rows = []
    try:
        r = requests.get(url, params={'matchId': game_id}, headers=HEADERS_API, timeout=5)
        if r.status_code != 200: return []
        data = r.json()
        if 'teamBoxscores' not in data: return []
        
        d_loc = data['teamBoxscores'][0]; d_vis = data['teamBoxscores'][1]
        
        h_name = d_loc.get('team', {}).get('fullName', 'UNK')
        a_name = d_vis.get('team', {}).get('fullName', 'UNK')
        real_home_code = get_codigo_inteligente(h_name)
        real_away_code = get_codigo_inteligente(a_name)

        tot_loc = get_team_totals(d_loc); tot_vis = get_team_totals(d_vis)
        
        def calc_poss(tm, opp): return tm['FGA'] + 0.44*tm['FTA'] - tm['ORB'] + tm['TOV']
        poss_loc = calc_poss(tot_loc, tot_vis); poss_vis = calc_poss(tot_vis, tot_loc)
        game_poss = (poss_loc + poss_vis) / 2
        tm_minutes = max(tot_loc['MIN'], tot_vis['MIN'], 200.0)

        p1 = tot_loc['PTS']; p2 = tot_vis['PTS']
        winner_code = "EMPATE"
        if p1 > p2: winner_code = real_home_code
        elif p2 > p1: winner_code = real_away_code

        for i, team_data in enumerate(data['teamBoxscores']):
            is_local = (i == 0)
            tm_stats = tot_loc if is_local else tot_vis
            opp_stats = tot_vis if is_local else tot_loc
            curr_code = real_home_code if is_local else real_away_code
            location_str = "HOME" if is_local else "AWAY"
            is_win = 1 if curr_code == winner_code else 0

            periodos = team_data.get('statsByPeriods', [])
            if not periodos: continue
            stats_totales = periodos[0].get('stats', {}).get('players', [])
            
            for p in stats_totales:
                p_info = p['player']
                pid = str(p_info.get('id', ''))
                if not pid: pid = str(p_info.get('license', '')) or "UNK"
                
                raw_name = p_info.get('firstInitialAndLastName') or p_info.get('nickName') or p_info.get('name')
                nombre = format_player_name(raw_name)

                min_str = p.get('playTime', '00:00')
                mp = str_time_to_float(min_str)
                seconds = str_time_to_seconds(min_str)
                
                pts = p.get('points', 0)
                t2a = p.get('twoPointersAttempted', 0); t2m = p.get('twoPointersMade', 0)
                t3a = p.get('threePointersAttempted', 0); t3m = p.get('threePointersMade', 0)
                fta = p.get('freeThrowsAttempted', 0); ftm = p.get('freeThrowsMade', 0)
                orb = p.get('offRebounds', 0); drb = p.get('defRebounds', 0); trb = p.get('totalRebounds', 0)
                ast = p.get('assists', 0); stl = p.get('steals', 0); blk = p.get('blocks', 0); tov = p.get('turnovers', 0)
                pf = p.get('personalFouls', 0)
                plus_minus = p.get('plusMinus', 0)
                
                fga = t2a + t3a; fgm = t2m + t3m
                player_poss_used = fga + 0.44 * fta + tov
                
                sh_2p_pct = safe_div(t2a * tm_minutes, mp * tm_stats['T2A']) * 100
                sh_3p_pct = safe_div(t3a * tm_minutes, mp * tm_stats['T3A']) * 100
                sh_fg_pct = safe_div(fga * tm_minutes, mp * tm_stats['FGA']) * 100
                
                team_poss_calc = tm_stats['FGA'] + 0.44 * tm_stats['FTA'] + tm_stats['TOV']
                usg_pct = safe_div(player_poss_used * tm_minutes, mp * team_poss_calc) * 100 if mp > 0 else 0
                pppos = safe_div(pts, player_poss_used)
                pm_40 = safe_div(plus_minus, mp) * 40
                
                ts_pct = safe_div(pts, 2 * (fga + 0.44 * fta)) * 100
                efg_pct = safe_div(fgm + 0.5 * t3m, fga) * 100
                t3ar = safe_div(t3a, fga) * 100
                ftr = safe_div(fta, fga) * 100
                
                orb_pct = safe_div(orb * tm_minutes, mp * (tm_stats['ORB'] + opp_stats['DRB'])) * 100
                drb_pct = safe_div(drb * tm_minutes, mp * (tm_stats['DRB'] + opp_stats['ORB'])) * 100
                trb_pct = safe_div(trb * tm_minutes, mp * (tm_stats['TRB'] + opp_stats['TRB'])) * 100
                
                ast_den = ((mp / tm_minutes) * tm_stats['FGM']) - fgm
                ast_pct = safe_div(ast, ast_den) * 100
                stl_pct = safe_div(stl * tm_minutes, mp * game_poss) * 100
                opp_2pa = opp_stats['FGA'] - opp_stats.get('T3A', 0) 
                if opp_2pa == 0: opp_2pa = opp_stats['FGA'] * 0.6 
                blk_pct = safe_div(blk * tm_minutes, mp * opp_2pa) * 100
                tov_pct = safe_div(tov, player_poss_used) * 100 
                gmsc = pts + 0.4*fgm - 0.7*fga - 0.4*(fta - ftm) + 0.7*orb + 0.3*drb + stl + 0.7*ast + 0.7*blk - 0.4*pf - tov

                ppm = safe_div(pts, mp)
                pp2p = safe_div(t2m * 2, t2a)
                pp3p = safe_div(t3m * 3, t3a)
                fg_pts = (t2m * 2) + (t3m * 3)
                ppfg = safe_div(fg_pts, fga)

                row = {
                    'GameID': game_id, 'Season': season_lbl, 'Week': week_lbl,
                    'Team': curr_code, 'Location': location_str,
                    'Winner': winner_code, 'Win': is_win,
                    'Dorsal': p_info.get('shirtNumber'), 
                    'PlayerID': pid, 
                    'Name': nombre,
                    'Min': min_str, 'Seconds': seconds, 
                    'Game_Poss': round(game_poss, 1), 
                    'PTS': pts, 'VAL': p.get('rating', 0), 
                    'T2_M': t2m, 'T2_A': t2a, 'T3_M': t3m, 'T3_A': t3a,
                    'FT_M': ftm, 'FT_A': fta,
                    'Reb_O': orb, 'Reb_D': drb, 'Reb_T': trb,
                    'AST': ast, 'STL': stl, 'TO': tov, 'BLK': blk, 'PF': pf, 'PF_R': p.get('foulsDrawn', 0),
                    '+/-': plus_minus, '+/-_40': round(pm_40, 1),
                    'GmSc': round(gmsc, 1),
                    'TS%': round(ts_pct, 1), 'eFG%': round(efg_pct, 1),
                    'USG%': round(usg_pct, 1), '3PAr': round(t3ar, 1), 'FTr': round(ftr, 1),
                    'ORB%': round(orb_pct, 1), 'DRB%': round(drb_pct, 1), 'TRB%': round(trb_pct, 1),
                    'AST%': round(ast_pct, 1), 'STL%': round(stl_pct, 1), 'BLK%': round(blk_pct, 1), 'TOV%': round(tov_pct, 1),
                    'PPM': round(ppm, 2), 'PP2P': round(pp2p, 2), 'PP3P': round(pp3p, 2), 'PPFG': round(ppfg, 2),
                    'PPPOS': round(pppos, 2),
                    'Sh%_2P': round(sh_2p_pct, 1), 'Sh%_3P': round(sh_3p_pct, 1), 'Sh%_FG': round(sh_fg_pct, 1)
                }
                rows.append(row)
        return rows
    except Exception as e:
        print(f"Error procesando GameID {game_id}: {e}")
        return []

# ==============================================================================
# 4. MAIN - BUCLE AUTOMÁTICO
# ==============================================================================

def main():
    print(f"🚀 INICIANDO SCRAPER AUTOMÁTICO: {TEMPORADA} | LIGA ENDESA")
    
    all_season_data = []
    jornada = 1
    sin_datos_consecutivos = 0
    
    # Creamos carpeta si no existe
    if not os.path.exists(CARPETA_SALIDA):
        os.makedirs(CARPETA_SALIDA)
        print(f"📁 Carpeta creada: {CARPETA_SALIDA}")

    while True:
        print(f"\n🔍 Analizando Jornada {jornada}...")
        
        # 1. Obtener IDs de la jornada
        ids = get_game_ids(TEMPORADA, COMPETICION, str(jornada))
        
        # 2. Verificar si es el 'futuro' (Lista vacía)
        if not ids:
            print(f"⛔ Jornada {jornada} vacía o futura. Deteniendo proceso.")
            break
        
        print(f"✅ Encontrados {len(ids)} partidos. Descargando datos...")
        
        # 3. Descargar Stats
        jornada_data = []
        for gid in ids:
            # Ponemos 'Jornada X' como etiqueta
            lbl_jornada = f"Jornada {jornada}"
            stats = get_stats_api(gid, TEMPORADA, lbl_jornada)
            
            if stats:
                jornada_data.extend(stats)
            else:
                print(f"   ⚠️ Partido {gid} sin estadísticas (¿No jugado?).")
            
            # Pausa ética para no saturar
            time.sleep(0.1)
            
        if jornada_data:
            all_season_data.extend(jornada_data)
            print(f"   ---> Guardados {len(jornada_data)} registros de Jornada {jornada}.")
        else:
            print(f"   ⚠️ Jornada {jornada} con IDs pero sin datos de BoxScore.")
        
        jornada += 1

    # ==============================================================================
    # 5. EXPORTACIÓN FINAL
    # ==============================================================================
    if all_season_data:
        print("\n💾 Generando archivo maestro...")
        df = pd.DataFrame(all_season_data)
        
        # Orden de columnas preferido
        cols = ['GameID', 'Season', 'Week', 'Team', 'Location', 'Winner', 'Win', 
                'Dorsal', 'PlayerID', 'Name', 'Min', 'Seconds', 'Game_Poss', 
                'PTS', 'VAL', 
                'T2_M', 'T2_A', 'T3_M', 'T3_A', 'FT_M', 'FT_A', 
                'Reb_O', 'Reb_D', 'Reb_T', 'AST', 'STL', 'TO', 'BLK', 'PF', 'PF_R',
                '+/-', '+/-_40', 'GmSc', 
                'TS%', 'eFG%', 'USG%', '3PAr', 'FTr', 'ORB%', 'DRB%', 'TRB%', 'AST%', 'STL%', 'BLK%', 'TOV%',
                'PPM', 'PP2P', 'PP3P', 'PPFG', 'PPPOS',
                'Sh%_2P', 'Sh%_3P', 'Sh%_FG'] 
        
        # Filtrar solo columnas existentes para evitar KeyErrors
        cols_final = [c for c in cols if c in df.columns]
        df = df[cols_final]
        
        ruta_completa = os.path.join(CARPETA_SALIDA, NOMBRE_ARCHIVO)
        df.to_csv(ruta_completa, index=False, encoding='utf-8-sig')
        
        print(f"🎉 ÉXITO: Archivo guardado en: {ruta_completa}")
        print(f"📊 Total Filas: {len(df)}")
    else:
        print("❌ No se obtuvieron datos en ninguna jornada.")

if __name__ == "__main__":
    main()