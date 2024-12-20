import aiosqlite

class Database:
    def __init__(self, db_name='roulette.db'):
        self.db_name = db_name

    async def init(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance INTEGER DEFAULT 500
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    password TEXT PRIMARY KEY,
                    is_active BOOLEAN DEFAULT FALSE
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS room_players (
                    room_password TEXT,
                    player_id INTEGER,
                    ready BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (room_password) REFERENCES rooms(password)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bets (
                    room_password TEXT,
                    player_id INTEGER,
                    number INTEGER,
                    amount INTEGER,
                    FOREIGN KEY (room_password) REFERENCES rooms(password)
                )
            ''')
            await db.commit()

    async def add_user(self, user_id: int, username: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                (user_id, username)
            )
            await db.commit()

    async def create_room(self, password: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('INSERT INTO rooms (password) VALUES (?)', (password,))
            await db.commit()

    async def add_player_to_room(self, password: str, player_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                'INSERT INTO room_players (room_password, player_id) VALUES (?, ?)',
                (password, player_id)
            )
            await db.commit()

    async def get_room_players(self, password: str):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT player_id FROM room_players WHERE room_password = ?',
                (password,)
            )
            return [row[0] for row in await cursor.fetchall()]

    async def place_bet(self, password: str, player_id: int, number: int, amount: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                'INSERT INTO bets (room_password, player_id, number, amount) VALUES (?, ?, ?, ?)',
                (password, player_id, number, amount)
            )
            await db.commit()

    async def get_player_bets_sum(self, password: str, player_id: int) -> int:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT SUM(amount) FROM bets WHERE room_password = ? AND player_id = ?',
                (password, player_id)
            )
            result = await cursor.fetchone()
            return result[0] or 0

    async def get_room_bets(self, password: str):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT player_id, number, amount FROM bets WHERE room_password = ?',
                (password,)
            )
            return await cursor.fetchall()

    async def close_room(self, password: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('DELETE FROM rooms WHERE password = ?', (password,))
            await db.execute('DELETE FROM room_players WHERE room_password = ?', (password,))
            await db.execute('DELETE FROM bets WHERE room_password = ?', (password,))
            await db.commit()

    async def get_all_rooms(self):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('''
                SELECT r.password, COUNT(rp.player_id) as player_count
                FROM rooms r
                LEFT JOIN room_players rp ON r.password = rp.room_password
                GROUP BY r.password
            ''')
            rooms = await cursor.fetchall()
            return [{'password': r[0], 'player_count': r[1]} for r in rooms]

    async def set_player_ready(self, password: str, player_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                UPDATE room_players 
                SET ready = TRUE 
                WHERE room_password = ? AND player_id = ?
            ''', (password, player_id))
            await db.commit()

    async def are_all_players_ready(self, password: str) -> bool:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM room_players 
                WHERE room_password = ? AND ready = FALSE
            ''', (password,))
            not_ready = (await cursor.fetchone())[0]
            return not_ready == 0

    async def update_player_balance(self, player_id: int, points: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                UPDATE users 
                SET balance = balance + ? 
                WHERE user_id = ?
            ''', (points, player_id))
            await db.commit()

    async def get_player_balance(self, player_id: int) -> int:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT balance FROM users WHERE user_id = ?',
                (player_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def reset_player_ready(self, password: str, player_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                UPDATE room_players 
                SET ready = FALSE 
                WHERE room_password = ? AND player_id = ?
            ''', (password, player_id))
            await db.commit()

    async def reset_room_bets(self, password: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('DELETE FROM bets WHERE room_password = ?', (password,))
            await db.commit()

    async def set_player_balance(self, player_id: int, balance: int):
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute('''
                    UPDATE users 
                    SET balance = ? 
                    WHERE user_id = ?
                ''', (balance, player_id))
                await db.commit()

    async def get_player_bet_count(self, password: str, player_id: int) -> int:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT COUNT(*) FROM bets WHERE room_password = ? AND player_id = ?',
                (password, player_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def check_number_bet(self, password: str, player_id: int, number: int) -> bool:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                'SELECT COUNT(*) FROM bets WHERE room_password = ? AND player_id = ? AND number = ?',
                (password, player_id, number)
            )
            result = await cursor.fetchone()
            return result[0] > 0
