from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
DATABASE = 'bowling.db'

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializar la base de datos con el nuevo modelo"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla de jugadores (solo info básica y estadísticas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            total_games INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            average_score REAL DEFAULT 0.0
        )
    ''')
    
    # Tabla de salidas (cada salida es una partida)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            location TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Relación muchos a muchos: salida <-> jugadores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outing_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outing_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            final_score INTEGER,
            FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(outing_id, player_id)
        )
    ''')
    
    # Tabla de frames por salida y jugador
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outing_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            frame_number INTEGER NOT NULL CHECK(frame_number >= 1 AND frame_number <= 10),
            roll_1 INTEGER CHECK(roll_1 >= 0 AND roll_1 <= 10),
            roll_2 INTEGER CHECK(roll_2 >= 0 AND roll_2 <= 10),
            roll_3 INTEGER CHECK(roll_3 >= 0 AND roll_3 <= 10),
            FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(outing_id, player_id, frame_number)
        )
    ''')
    
    # Agregar columna final_position si no existe
    try:
        cursor.execute('ALTER TABLE outing_players ADD COLUMN final_position INTEGER')
    except:
        pass  # Ya existe
    
    conn.commit()
    conn.close()

# ============================================================================
# PARSING Y CONVERSIÓN
# ============================================================================

def symbol_to_number(symbol, previous_roll=None):
    """Convierte un símbolo de entrada a número"""
    symbol = symbol.upper().strip()
    
    if symbol == 'X':
        return 10
    
    if symbol == '/':
        if previous_roll is None:
            return None
        return 10 - previous_roll
    
    if symbol == '-':
        return 0
    
    if symbol.isdigit():
        num = int(symbol)
        if 0 <= num <= 9:
            return num
    
    return None

# En bolos/bowling_app.py

def number_to_symbol(number, previous_roll=None):
    """Convierte un número a símbolo para display"""
    if number is None:
        return ''
    
    # 1. MOVIDO ARRIBA: Primero verificamos Spare
    # Agregamos "previous_roll != 10" para proteger el frame 10
    if previous_roll is not None and previous_roll != 10 and (previous_roll + number == 10):
        return '/'
    
    # 2. LUEGO: Verificamos Strike
    if number == 10:
        return 'X'
    
    if number == 0:
        return '–'
    
    return str(number)

# ============================================================================
# VALIDACIONES
# ============================================================================

def validate_roll(symbol, frame_number, roll_number, previous_rolls):
    """Valida un tiro antes de guardarlo"""
    symbol = symbol.upper().strip()
    
    if not symbol or symbol not in ['X', '/', '-', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
        return False, "Símbolo inválido", None
    
    if symbol == '/' and roll_number == 1:
        return False, "/ solo puede ir en el segundo tiro", None
    
    prev = previous_rolls[-1] if previous_rolls else None
    number = symbol_to_number(symbol, prev)
    
    if number is None:
        return False, "Conversión inválida", None
    
    if symbol == '/' and prev == 10:
        return False, "No puede haber / después de strike", None
    
    # FRAMES 1-9
    if frame_number <= 9:
        if roll_number == 1:
            return True, None, number
        
        elif roll_number == 2:
            if previous_rolls[0] == 10:
                return False, "No hay segundo tiro después de strike", None
            
            if previous_rolls[0] + number > 10:
                return False, f"La suma excede 10 ({previous_rolls[0]} + {number})", None
            
            return True, None, number
        
        else:
            return False, "Frame 1-9 solo tiene 2 tiros", None
    
    # FRAME 10
    else:
        if roll_number == 1:
            return True, None, number
        
        elif roll_number == 2:
            if previous_rolls[0] != 10:
                if previous_rolls[0] + number > 10:
                    return False, f"La suma excede 10 ({previous_rolls[0]} + {number})", None
            
            return True, None, number
        
        elif roll_number == 3:
            if len(previous_rolls) < 2:
                return False, "No hay suficientes tiros previos", None
            
            roll1, roll2 = previous_rolls[0], previous_rolls[1]
            
            has_strike_first = roll1 == 10
            has_spare = roll1 + roll2 == 10
            
            if not has_strike_first and not has_spare:
                return False, "No hay tercer tiro (sin strike ni spare)", None
            
            if has_strike_first:
                if roll2 != 10 and roll2 + number > 10:
                    return False, f"La suma de tiros 2 y 3 excede 10 ({roll2} + {number})", None
            
            return True, None, number
        
        else:
            return False, "Frame 10 tiene máximo 3 tiros", None

# ============================================================================
# CÁLCULO DE SCORE
# ============================================================================

def get_all_rolls(frames_data):
    """Extrae todos los tiros en orden secuencial"""
    rolls = []
    for frame in frames_data:
        if frame['roll_1'] is not None:
            rolls.append(frame['roll_1'])
        if frame['roll_2'] is not None:
            rolls.append(frame['roll_2'])
        if frame['roll_3'] is not None:
            rolls.append(frame['roll_3'])
    return rolls

def calculate_scores(frames_data):
    """Calcula los scores frame por frame"""
    scores = [None] * 10
    all_rolls = get_all_rolls(frames_data)
    roll_idx = 0
    cumulative = 0
    
    for i in range(10):
        frame = frames_data[i]
        frame_num = frame['frame_number']
        
        if frame_num <= 9:
            if frame['roll_1'] is None:
                break
            
            # Strike
            if frame['roll_1'] == 10:
                if roll_idx + 2 >= len(all_rolls):
                    break
                
                frame_score = 10 + all_rolls[roll_idx + 1] + all_rolls[roll_idx + 2]
                cumulative += frame_score
                scores[i] = cumulative
                roll_idx += 1
            
            # Spare
            elif frame['roll_2'] is not None and frame['roll_1'] + frame['roll_2'] == 10:
                if roll_idx + 2 >= len(all_rolls):
                    break
                
                frame_score = 10 + all_rolls[roll_idx + 2]
                cumulative += frame_score
                scores[i] = cumulative
                roll_idx += 2
            
            # Normal
            elif frame['roll_2'] is not None:
                frame_score = frame['roll_1'] + frame['roll_2']
                cumulative += frame_score
                scores[i] = cumulative
                roll_idx += 2
            
            else:
                break
        
        # Frame 10
        else:
            roll1 = frame['roll_1']
            roll2 = frame['roll_2']
            roll3 = frame['roll_3']
            
            if roll1 is None:
                break
            
            if roll1 == 10:
                if roll2 is None or roll3 is None:
                    break
                frame_score = roll1 + roll2 + roll3
            
            elif roll2 is not None and roll1 + roll2 == 10:
                if roll3 is None:
                    break
                frame_score = roll1 + roll2 + roll3
            
            elif roll2 is not None:
                frame_score = roll1 + roll2
            
            else:
                break
            
            cumulative += frame_score
            scores[i] = cumulative
    
    return scores

def update_player_stats(player_id):
    """Actualiza las estadísticas del jugador basándose en sus partidas"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener todos los scores finales del jugador
    cursor.execute('''
        SELECT final_score 
        FROM outing_players 
        WHERE player_id = ? AND final_score IS NOT NULL
    ''', (player_id,))
    
    scores = [row['final_score'] for row in cursor.fetchall()]
    
    if scores:
        total_games = len(scores)
        total_score = sum(scores)
        average_score = total_score / total_games
        
        cursor.execute('''
            UPDATE players 
            SET total_games = ?, total_score = ?, average_score = ?
            WHERE id = ?
        ''', (total_games, total_score, average_score, player_id))
    
    conn.commit()
    conn.close()

def update_positions(outing_id):
    """Actualiza las posiciones finales de todos los jugadores en una salida"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener todos los jugadores con score completo, ordenados por score desc
    cursor.execute('''
        SELECT player_id, final_score
        FROM outing_players
        WHERE outing_id = ? AND final_score IS NOT NULL
        ORDER BY final_score DESC
    ''', (outing_id,))
    
    players_with_scores = cursor.fetchall()
    
    # Asignar posiciones (1, 2, 3, etc.)
    for position, player_row in enumerate(players_with_scores, start=1):
        cursor.execute('''
            UPDATE outing_players
            SET final_position = ?
            WHERE outing_id = ? AND player_id = ?
        ''', (position, outing_id, player_row['player_id']))
    
    conn.commit()
    conn.close()

# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/players', methods=['GET', 'POST'])
def players():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name:
            try:
                cursor.execute('INSERT INTO players (name) VALUES (?)', (name,))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return jsonify({'error': 'Jugador ya existe'}), 400
    
    cursor.execute('SELECT * FROM players ORDER BY average_score DESC, name')
    players_list = cursor.fetchall()
    conn.close()
    
    return render_template('players.html', players=players_list)

@app.route('/player/<int:player_id>')
def player_detail(player_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        return "Jugador no encontrado", 404
    
    # Obtener historial de partidas
    cursor.execute('''
        SELECT o.id, o.date, o.location, op.final_score
        FROM outing_players op
        JOIN outings o ON op.outing_id = o.id
        WHERE op.player_id = ?
        ORDER BY o.date DESC
    ''', (player_id,))
    
    games = cursor.fetchall()
    conn.close()
    
    return render_template('player_detail.html', player=player, games=games)

@app.route('/outings', methods=['GET', 'POST'])
def outings():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        location = request.form.get('location', '').strip()
        
        if date and location:
            cursor.execute('INSERT INTO outings (date, location) VALUES (?, ?)', (date, location))
            conn.commit()
    
    cursor.execute('SELECT * FROM outings ORDER BY date DESC')
    outings_list = cursor.fetchall()
    conn.close()
    
    return render_template('outings.html', outings=outings_list)

@app.route('/outing/<int:outing_id>')
def outing_detail(outing_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM outings WHERE id = ?', (outing_id,))
    outing = cursor.fetchone()
    
    if not outing:
        conn.close()
        return "Salida no encontrada", 404
    
    # Obtener jugadores de esta salida
    cursor.execute('''
        SELECT p.id, p.name, op.final_score, op.final_position
        FROM outing_players op
        JOIN players p ON op.player_id = p.id
        WHERE op.outing_id = ?
        ORDER BY 
            CASE 
                WHEN op.final_score IS NULL THEN 1 
                ELSE 0 
            END,
            op.final_score DESC,
            p.name
    ''', (outing_id,))
    
    outing_players = cursor.fetchall()
    
    # Si hay jugadores, construir la matriz de frames
    game_data = []
    if outing_players:
        for player in outing_players:
            cursor.execute('''
                SELECT * FROM frames
                WHERE outing_id = ? AND player_id = ?
                ORDER BY frame_number
            ''', (outing_id, player['id']))
            
            frames = cursor.fetchall()
            
            # Si no hay frames, crear vacíos
            if not frames:
                for frame_num in range(1, 11):
                    cursor.execute('''
                        INSERT INTO frames (outing_id, player_id, frame_number)
                        VALUES (?, ?, ?)
                    ''', (outing_id, player['id'], frame_num))
                conn.commit()
                
                cursor.execute('''
                    SELECT * FROM frames
                    WHERE outing_id = ? AND player_id = ?
                    ORDER BY frame_number
                ''', (outing_id, player['id']))
                
                frames = cursor.fetchall()
            
            # Calcular scores
            scores = calculate_scores(frames)
            
            # Preparar frames para display
            frames_display = []
            for i, frame in enumerate(frames):
                frame_dict = dict(frame)
                frame_dict['score'] = scores[i]
                
                if frame['frame_number'] <= 9:
                    frame_dict['display_1'] = number_to_symbol(frame['roll_1'])
                    frame_dict['display_2'] = number_to_symbol(frame['roll_2'], frame['roll_1'])
                    frame_dict['display_3'] = ''
                else:
                    frame_dict['display_1'] = number_to_symbol(frame['roll_1'])
                    frame_dict['display_2'] = number_to_symbol(frame['roll_2'], frame['roll_1'])
                    
                    if frame['roll_3'] is not None:
                        if frame['roll_2'] == 10:
                            frame_dict['display_3'] = number_to_symbol(frame['roll_3'])
                        else:
                            frame_dict['display_3'] = number_to_symbol(frame['roll_3'], frame['roll_2'])
                    else:
                        frame_dict['display_3'] = ''
                
                frames_display.append(frame_dict)
            
            game_data.append({
                'player': player,
                'frames': frames_display,
                'final_score': scores[9] if scores[9] is not None else None
            })
    
    # Obtener todos los jugadores disponibles para agregar
    cursor.execute('SELECT * FROM players ORDER BY name')
    all_players = cursor.fetchall()
    
    conn.close()
    
    return render_template('outing_detail.html', 
                         outing=outing, 
                         game_data=game_data,
                         all_players=all_players)

@app.route('/outing/<int:outing_id>/add_player', methods=['POST'])
def add_player_to_outing(outing_id):
    player_id = request.form.get('player_id')
    
    if not player_id:
        return redirect(url_for('outing_detail', outing_id=outing_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Agregar jugador a la salida
        cursor.execute('INSERT INTO outing_players (outing_id, player_id) VALUES (?, ?)', 
                      (outing_id, player_id))
        
        # Crear frames vacíos
        for frame_num in range(1, 11):
            cursor.execute('''
                INSERT INTO frames (outing_id, player_id, frame_number)
                VALUES (?, ?, ?)
            ''', (outing_id, player_id, frame_num))
        
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Jugador ya está en la salida
    
    conn.close()
    
    return redirect(url_for('outing_detail', outing_id=outing_id))

@app.route('/outing/<int:outing_id>/update_roll', methods=['POST'])
def update_roll(outing_id):
    data = request.json

    try:
        player_id = int(data.get('player_id'))
        frame_number = int(data.get('frame_number'))
        roll_number = int(data.get('roll_number'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Datos inválidos'}), 400

    symbol = data.get('symbol', '').strip()
    
    if not all([player_id, frame_number, roll_number, symbol]):
        return jsonify({'error': 'Datos incompletos'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener el frame actual
    cursor.execute('''
        SELECT * FROM frames
        WHERE outing_id = ? AND player_id = ? AND frame_number = ?
    ''', (outing_id, player_id, frame_number))
    
    frame = cursor.fetchone()
    
    if not frame:
        conn.close()
        return jsonify({'error': 'Frame no encontrado'}), 404
    
    # Obtener tiros previos en este frame
    previous_rolls = []
    if roll_number >= 2 and frame['roll_1'] is not None:
        previous_rolls.append(frame['roll_1'])
    if roll_number == 3 and frame['roll_2'] is not None:
        previous_rolls.append(frame['roll_2'])
    
    # Validar
    is_valid, error_msg, number = validate_roll(symbol, frame_number, roll_number, previous_rolls)
    
    if not is_valid:
        conn.close()
        return jsonify({'error': error_msg}), 400
    
    # Actualizar el tiro
    column = f'roll_{roll_number}'
    cursor.execute(f'''
        UPDATE frames
        SET {column} = ?
        WHERE outing_id = ? AND player_id = ? AND frame_number = ?
    ''', (number, outing_id, player_id, frame_number))
    
    conn.commit()
    
    # Recalcular scores para este jugador
    cursor.execute('''
        SELECT * FROM frames 
        WHERE outing_id = ? AND player_id = ?
        ORDER BY frame_number
    ''', (outing_id, player_id))
    
    all_frames = cursor.fetchall()
    scores = calculate_scores(all_frames)
    
    # Actualizar final_score si está completo
    if scores[9] is not None:
        cursor.execute('''
            UPDATE outing_players
            SET final_score = ?
            WHERE outing_id = ? AND player_id = ?
        ''', (scores[9], outing_id, player_id))
        
        conn.commit()
        
        # Actualizar posiciones de todos los jugadores en esta salida
        update_positions(outing_id)
        
        # Actualizar estadísticas del jugador
        update_player_stats(player_id)
    
    conn.close()
    
    return jsonify({
        'success': True,
        'number': number,
        'scores': scores
    })

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)